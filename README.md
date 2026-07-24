# AI News Sniffer

Daily Chinese AI-news digest generated from free public sources.

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Export the required values from `.env` in your shell; the application does not
load `.env` automatically in production.

## Test

```bash
ruff check src tests
pytest
```

## Dry run

```bash
python -m ai_news_sniffer \
  --runtime-dir .local/runtime-data \
  --output-dir build/site \
  build --target-date 2026-07-23 --dry-run
```

Open `build/site/index.html` locally. A dry run does not update fingerprints,
publish Pages, or send notifications.

## Source configuration

`config/sources.yaml` contains the reviewed 35-source whitelist and all
source/group switches. `light`, `balanced`, and `full` resolve to 12, 25, and
35 sources with default AI candidate caps of 20, 30, and 40. Inspect effective
selection without network access:

```bash
ai-news-sniffer sources list --profile balanced
ai-news-sniffer sources candidates
```

For an intentional live check, use `ai-news-sniffer sources test SOURCE_ID` or
run the manual Source audit workflow. A successful audit clears runtime
auto-pause state but never changes `config/sources.yaml`.

## GitHub configuration

Create repository secrets `DEEPSEEK_API_KEY` and `MEOW_NICKNAME`. Add
`WECOM_WEBHOOK_URL` and `GENERIC_WEBHOOK_URL` only when those channels are
enabled. Create repository variable `PUBLIC_BASE_URL` without a trailing slash.
Enable GitHub Pages with GitHub Actions as its source.

The first successful non-dry run creates the `runtime-data` branch. Protect
`main`; allow the workflow token to write repository contents and Pages.

## Manual run

Open Actions → Daily AI Digest → Run workflow. Keep `dry_run=true` for preview.
For a real run set `dry_run=false`, `publish=true`, and set `notify=true` only
when notifications should be sent. `source_profile` defaults to `balanced`;
`include_sources` and `exclude_sources` accept comma-separated source IDs.
`max_ai_candidates=0` uses the selected profile's default budget.

## Custom domain

Verify the domain in GitHub, configure it in repository Pages settings, and use
a subdomain CNAME pointing to `<account>.github.io` or the documented apex
records. Do not use wildcard DNS. Set `PUBLIC_BASE_URL` to the final HTTPS URL.

## Templates

Copy `templates/default` to `templates/<new-name>`, edit the Jinja2/CSS files,
then set `template: <new-name>` in `config/app.yaml`. A later run rebuilds all
stored report JSON through the selected template.

## Provider extension

Add an entry to `config/providers.yaml`, put its key in a new GitHub Secret,
and add the provider ID to `fallback_order`. Use
`api_style: openai_chat_completions` for compatible DeepSeek, Kimi, MiniMax,
or other endpoints.

## Failure behavior

Source failures are logged and isolated. Provider failure uses the configured
fallback order, then creates a clearly labeled source-summary digest. Pages are
verified before notification. Channel failures are recorded independently in
`runtime-data/runs/`. A source is marked degraded after three consecutive
failures and auto-paused after seven; the next successful notification includes
a maintenance reminder. Use the manual Source audit workflow to test and clear
an auto-pause only after a real network audit succeeds.
