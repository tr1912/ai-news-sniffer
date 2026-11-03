# Repair and replace dead news sources (RSS swaps, changelog + HF adapters, HN crash fix)

This branch repairs the chronically-failing source set in `config/sources.yaml`: five official/research sources move from HTML scraping to official RSS feeds, `hf-daily-papers` moves to a new adapter hitting Hugging Face's official JSON API, `deepseek-updates` gains a `changelog` HTML parsing mode, `anthropic-news` gets a new link selector, seven dead sources are deleted, and seven verified RSS sources are added. Two production bugs are also fixed: hacker-news no longer lets a single bad URL fail the whole source, and the HTML adapter stops advertising `br` encoding it cannot decode. The net source count stays at 35 (light=8, balanced=20, full=35) and the test-count assertions are updated to match.

Watch for: the changelog mode assigns every entry on a page the *same* URL (the page's date anchor), and canonicalization strips the fragment — so downstream dedup collapses a multi-entry DeepSeek update day down to a single article (**confirmed**). The `hf_daily_papers` adapter fails *open*: if the API renames its fields, every item is silently skipped and the run is recorded as a success, masking the outage the exact way the 13 dead HTML sources were masked (**confirmed**). The `anthropic` link selector `a[href*='-']` is a positional heuristic that breaks if a hyphenated category link ever precedes the article link in a card (**likely**).

**Verdict**: NEEDS_CHANGES

## High-level view

Most of the change is configuration: swapping `kind` and `url`, deleting stale entries, and adding feeds. The profile-count arithmetic (8/20/35) was reconciled against the final yaml and the registry/config/service/cli assertions were all updated in lockstep; the full suite is green. No code outside the diff still references the deleted source ids — the only lingering mentions are in design docs and the interests entity list, which are unrelated to source resolution.

The changelog mode is the riskiest new code. It correctly splits a Docusaurus-style update log by `Date: YYYY-MM-DD` headings and attributes each sub-heading to the right day. But it has no per-entry URL: every entry inherits the date-section's anchor link, and because `canonicalize_url` discards the fragment, all entries on a page share one canonical URL. The dedup stage keys on canonical URL, so only the highest-scored entry per page survives. The adapter-level test asserts two articles come back and never runs dedup, so the collapse is invisible in CI.

The HF adapter's empty-vs-missing-field branching is the other gap. An empty array raises `SourceParseError` (correct, trips health tracking), but a non-empty payload whose items all lack `title`/`id`/`date` returns an empty list, which the collection service records as a *success*. That is fail-open in a change whose whole purpose is to stop silently-failing sources.

The hacker-news try/except is scoped to `ValidationError` around `RawArticle` construction, so a bad URL skips one story without swallowing unrelated `KeyError`/`httpx` errors. Dropping `br` from `Accept-Encoding` is correct for an environment with no brotli decoder installed — the old code advertised an encoding httpx couldn't decode.

The anthropic selector works on the saved fixture but is fragile: it selects the first `<a>` whose href contains a hyphen, which skips the category-nav link today only because those paths lack hyphens.

<details>
<summary>Issues (5)</summary>

1. **Changelog entries collapse in dedup** — every entry on a DeepSeek update page gets the same canonical URL (fragment stripped), so dedup keeps only one per page. Give each entry a distinct identity (e.g. append a slug of the title to the fragment and preserve it through canonicalization, or dedup changelog entries by fingerprint only).
2. **HF adapter fails open on field rename** — a non-empty payload with all items missing required fields returns `[]` and is recorded as success. Raise `SourceParseError` when the payload is non-empty but zero valid records were parsed, matching the HTML adapter's fail-closed contract.
3. **Anthropic link selector is positional** — `a[href*='-']` picks the first hyphenated href and breaks if a hyphenated category link ever precedes the article link. Prefer a structural selector (e.g. the card's title-wrapping anchor) if one exists on the saved page.
4. **Changelog dedup collapse is untested** — the test checks adapter output but never runs `deduplicate_articles`, so the collapse passes CI. Add a test that normalizes + dedups changelog output and asserts multiple entries survive.
5. **`Accept-Encoding` hardcode diverges from httpx** — the HTML adapter pins `gzip, deflate` while every other adapter lets httpx negotiate; if brotli is later added to deps the HTML adapter alone won't use it. Consider dropping the manual header so httpx manages it.

</details>

<details>
<summary>Details</summary>

### Changelog mode shares one URL across all entries on a page

`_articles_from_changelog` (`src/ai_news_sniffer/sources/html.py:338-385`) splits the page by `Date: YYYY-MM-DD` headings and emits one tuple per sub-heading in each date section. The date section's link is the only link produced:

```python
anchor = node.attributes.get("id") or ""
link = urljoin(str(source.url), f"#{anchor}") if anchor else str(source.url)
...
parsed.append((title, link, published, excerpt))   # same `link` for every entry in the section
```

So the two entries under `Date: 2026-07-23` both get `https://api-docs.deepseek.com/updates/#date-2026-07-23`. The adapter test (`tests/test_source_adapters.py:test_html_changelog_mode_splits_by_date_heading`) asserts two articles come back with that URL — and they do, at the adapter boundary.

The problem is downstream. `canonicalize_url` (`src/ai_news_sniffer/normalization.py`) builds the canonical URL with an empty fragment component, so the `#date-...` anchor is discarded — both entries canonicalize to `https://api-docs.deepseek.com/updates`. `deduplicate_articles` (`src/ai_news_sniffer/dedup.py:20-22`) rejects any candidate whose canonical URL is already in `seen_urls`:

```python
if str(candidate.canonical_url) in seen_urls:
    continue
```

Result: for any DeepSeek update day with more than one entry, only the highest-scored entry survives; the rest are dropped before they ever reach the editorial budget. A user reading the daily digest sees one DeepSeek item on a day that shipped three, with no indication the others existed. The fix needs a distinct identity per entry — a per-entry slug in the fragment that survives canonicalization, or deduping changelog output by fingerprint (title-aware) rather than canonical URL.

### HF adapter fails open when the payload shape changes

`HfDailyPapersAdapter.fetch` (`src/ai_news_sniffer/sources/hf_daily_papers.py:60-76`) skips any item missing `title`, `paper.id`, or a parseable date, then:

```python
if not articles and not payload:
    raise SourceParseError(f"{source.id}: no dated article records found")
return articles
```

The raise only fires when `payload` itself is empty. Consider the realistic failure this PR exists to prevent: Hugging Face renames `paper` to `data`, or `publishedAt` to `published_at`. Now `payload` is a full list, every item is skipped for missing fields, `articles` is empty, and the adapter returns `[]`. `source_service.collect` treats an empty-but-non-raising return as a success (`health_store.record_success`, `src/ai_news_sniffer/source_service.py:66`), so the health counter resets and the source never auto-pauses. This is the same silent-failure mode as the 13 HTML sources that "never succeeded but never alerted." The HTML adapter already handles this correctly — it raises `SourceParseError` when a non-empty page yields zero parseable records. The HF adapter should match: raise when `payload` is non-empty but no valid records were extracted.

### `Accept-Encoding` hardcode diverges from httpx

The HTML adapter (`src/ai_news_sniffer/sources/html.py:450`) previously advertised `Accept-Encoding: gzip, deflate, br` while no brotli decoder is installed (confirmed: `import brotli` and `import brotlicffi` both fail in the venv). A server honoring `br` returns a body httpx can't decode, failing the parse — a plausible contributor to the dead HTML sources. The remaining concern: this adapter now hardcodes `gzip, deflate` while every other adapter lets httpx set the header (httpx advertises `br` automatically only when brotli is importable), so if brotli is later added to the project the HTML adapter alone won't benefit. Letting httpx manage the header keeps all adapters consistent.

### anthropic selector `a[href*='-']`

The new selector (`config/sources.yaml`, anthropic-news) relies on `css_first(selectors.link)` returning the first `<a>` in the card whose href contains a hyphen. On the saved fixture this skips the category-nav anchor (`/news/announcements`, `/news/policy` — no hyphen) and lands on the article link. It works because today's category paths happen to be single words. The selector encodes "the article link is the first hyphenated href," which is positional, not semantic: if Anthropic adds a category like `/news/product-updates` as the leading card link, the selector grabs the category page and the real article title/date pairing breaks. The spec explicitly accepted this trade-off, so it's not a blocker, but it's the most likely source of a future silent regression for this source. A structural selector tied to the title-wrapping anchor would be sturdier if the page offers one.

### Source-count reconciliation and no dangling references

The deletions (qwen/minimax/zhipu/meta/jiqizhixin/mistral/cohere) and seven RSS additions net to 35 sources. The profile counts (light=8, balanced=20, full=35) are asserted consistently across `tests/test_config.py`, `tests/test_source_registry.py`, `tests/test_source_cli.py`, and `tests/test_source_service.py`, and the full suite passes (99 passed). A repo-wide search for the deleted ids turns up only design docs, ledger/memory files, and the `interests.yaml` entity list (MiniMax/Meta AI as topic keywords, unrelated to source resolution) — no pipeline, notification, or registry code still points at a removed source.

</details>

<details>
<summary>File map</summary>

- `config/sources.yaml` — 5 sources → RSS, hf-daily-papers → `hf_daily_papers`, deepseek → `options.mode=changelog`, anthropic selector, delete 7 / add 7.
- `src/ai_news_sniffer/models.py` — add `SourceKind.HF_DAILY_PAPERS`.
- `src/ai_news_sniffer/sources/base.py` — dispatch `HF_DAILY_PAPERS` to the new adapter.
- `src/ai_news_sniffer/sources/hacker_news.py` — wrap `RawArticle` construction in `try/except ValidationError`.
- `src/ai_news_sniffer/sources/hf_daily_papers.py` — new adapter for the HF daily-papers JSON API.
- `src/ai_news_sniffer/sources/html.py` — new `_articles_from_changelog` + dispatch; drop `br` from `Accept-Encoding`.
- `tests/test_source_adapters.py` — adapter tests for anthropic, hf_daily_papers, changelog, hacker-news skip.
- `tests/fixtures/*` — html_anthropic.html, html_changelog.html, hf_daily_papers.json, hn_item_good/bad_url.json.
- `tests/test_config.py`, `tests/test_source_registry.py`, `tests/test_source_cli.py`, `tests/test_source_service.py` — updated count assertions.
- `docs/superpowers/specs/2026-11-02-source-repair-design.md`, `docs/superpowers/plans/2026-11-02-source-repair.md` — spec and plan.

Full diff: `git diff d4304b4 fix/repair-dead-sources`

</details>
