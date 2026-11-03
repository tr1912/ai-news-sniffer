# 失效新闻源修复与替换 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复/替换一批失效的新闻源，删除抓不到或停更的源，新增 7 个已验证 RSS 源，并修复 hacker-news 单条坏 URL 拖垮整源的 bug。

**Architecture:** 大部分改动是 `config/sources.yaml` 配置调整（改 kind、改 selector、删源、加源）。两处新增代码：HTML 适配器加 `changelog` 模式供 deepseek 用；新增 `hf_daily_papers` 适配器调 HF 官方 JSON 接口。hacker-news 加逐条容错。测试用保存的页面/接口 fixture，不访问线上。

**Tech Stack:** Python 3.12、httpx、feedparser、selectolax(lexbor)、pydantic v2、pytest、respx。

**Spec:** `docs/superpowers/specs/2026-11-02-source-repair-design.md`

**执行记录:** 本计划在 `fix/repair-dead-sources` 分支以 superpowers:executing-plans（Native 内联）方式执行。ledger 在 `.superpowers/sdd/source-repair/progress.md`。文档在首次执行后由用户要求补全，内容已反映执行中确定的 ruling（见下方「执行中的 ruling」）。

## Global Constraints

- 源 URL 必须 HTTPS（`SourceConfig.require_https`）。
- 常规 CI/单元测试不得访问线上站点；用本地 fixture + respx。
- 改完源总数 = 35，各档位：light=8、balanced=20、full=35。`tests/test_config.py` 与 `tests/test_source_registry.py` 的数量断言必须同步成这三个数。
- 新源 `kind: rss`，`group: media`，`independence_group` 省略（默认等于 id）。
- hf-daily-papers 必须用官方接口 `https://huggingface.co/api/daily_papers`，不用第三方 RSS。

## 执行中的 ruling（相对原 spec 的调整）

- **cohere-blog 由「改 selector」改为「删除」**：页面文章标题仅存在于 `a` 的 `aria-label`（如 "Read full article: Introducing Rerank 5…"），卡片内无文本标题、无 `h` 标签，现有 `HtmlSelectors` + `_extract_title` 无法提取。按 spec「HTML 拿不到标题则删除」的标准归入删除，不扩展 selector 机制（超出本次范围）。代价：失去 Cohere 官方源；若日后其页面结构改善可重新加回。
- **anthropic-news 用 `link: "a[href*='-']"`**：卡片第一个 `a` 是分类导航（`/news/announcements` 等，无路径连字符），文章链接含连字符（`/claude-opus-5-5`、`/news/s1-sec`）。该 selector 在保存页面上 6/6 卡片取到唯一正确文章链接，无需改适配器。
- **数量从 36 重算为 35**：因 cohere 从「新增净增」口径移到「删除」，删除数由 6 变 7。重算见下。

## 数量核算

原 35 源。

删除 7 个（原因见 spec「逐源处理清单」+ 上方 cohere ruling）：
qwen-blog(LBF)、minimax-news(LBF)、zhipu-research(LBF)、meta-ai-blog(LBF)、jiqizhixin(BF)、mistral-news(BF)、cohere-blog(BF)。
→ 删后 light=8、balanced=18、full=28。

新增 7 个 rss（group: media）：
mit-tech-review-ai(BF)、infoq-cn(BF)、latent-space(F)、simon-willison(F)、wired-ai(F)、leiphone(F)、ithome(F)。
→ 最终 light=8、balanced=20、full=35，总 35。

改 kind / 改 selector 的源不改档位。

## Review Focus

- hacker-news 返回含非法 IDN/emoji URL 的 story：应跳过该条、保留其余，而不是整源失败。（Task 1 覆盖）
- deepseek changelog 页日期在 `Date: YYYY-MM-DD` 标题里、正文在标题之后：changelog 模式应把标题当日期、后续 h3 当标题、其后 p 当摘要，且下一个日期标题是边界。（Task 2 覆盖）
- hf_daily_papers 接口返回空数组或缺字段的 paper：应跳过缺字段项、空数组时抛 SourceParseError 而非崩溃。（Task 3 覆盖）
- anthropic 卡片首个 `a` 是分类链接、文章链接为相对路径：selector 应取到文章链接并 urljoin 成绝对地址，窗口外日期被过滤。（Task 4 覆盖）
- 全部源变更后 profile 数量漂移：某源 profiles 写错会导致 light/balanced/full 计数不符。（Task 5 的数量断言覆盖）

---

## Task 1: 修复 hacker-news 单条坏 URL  ✅ 已完成 (cc7a20d)

**Files:**
- Modify: `src/ai_news_sniffer/sources/hacker_news.py`
- Test: `tests/test_source_adapters.py`
- Fixture: `tests/fixtures/hn_item_good.json`、`tests/fixtures/hn_item_bad_url.json`

- [x] **Step 1:** 写失败测试 `test_hacker_news_skips_invalid_url_item`（topstories=[42,43]，42 正常、43 URL 为非法 IDN+emoji，断言返回 1 条不抛异常）
- [x] **Step 2:** 运行确认 RED（移除 try/except 时因 ValidationError@41 失败）
- [x] **Step 3:** 每条 `RawArticle(...)` 外包 `try/except ValidationError: continue`，从 `pydantic` 导入 `ValidationError`
- [x] **Step 4:** 运行确认 GREEN
- [x] **Step 5:** commit `fix(hacker-news): 跳过非法 URL 单条而非整源失败`

---

## Task 2: HTML 适配器 changelog 模式（deepseek）  ✅ 已完成 (842940c)

**Files:**
- Modify: `src/ai_news_sniffer/sources/html.py`（新增 `_articles_from_changelog`，在 `fetch` 中按 `options.mode == "changelog"` 分派；`import re`）
- Test: `tests/test_source_adapters.py`
- Fixture: `tests/fixtures/html_changelog.html`

**Interface produced:** `_articles_from_changelog(tree, source) -> list[tuple[str, str, datetime, str]]`。日期取 `h2#id=date-YYYY-MM-DD` 文本中的 `Date: YYYY-MM-DD`，标题取该日期段内各 `h3`，摘要取标题后首个 `p`，链接 `url#anchor`。按 `headings` 列表区间切分（不依赖 DOM 兄弟遍历）。

- [x] **Step 1:** 写失败测试 `test_html_changelog_mode_splits_by_date_heading`（两个日期段，仅 07-23 段的 2 条在窗口内）
- [x] **Step 2:** 运行确认 RED
- [x] **Step 3:** 实现 `_articles_from_changelog` + `fetch` 分派
- [x] **Step 4:** 运行确认 GREEN（修正过一次：改用 headings 区间切分，避免把下个日期标题当普通标题）
- [x] **Step 5:** commit `feat(html): 新增 changelog 解析模式供 deepseek 更新日志使用`

---

## Task 3: 新增 hf_daily_papers 适配器  ✅ 已完成 (866d6a8)

**Files:**
- Modify: `src/ai_news_sniffer/models.py`（`SourceKind.HF_DAILY_PAPERS = "hf_daily_papers"`）
- Modify: `src/ai_news_sniffer/sources/base.py`（`build_source_adapter` 加分支）
- Create: `src/ai_news_sniffer/sources/hf_daily_papers.py`
- Test: `tests/test_source_adapters.py`
- Fixture: `tests/fixtures/hf_daily_papers.json`

**Interface produced:** `class HfDailyPapersAdapter: fetch(source, since, until) -> list[RawArticle]`。日期取顶层 `publishedAt`（回退 `paper.publishedAt`），链接 `https://huggingface.co/papers/{paper.id}`，缺 title/id/date 的条目跳过；空数组抛 `SourceParseError`，HTTPError 抛 `SourceFetchError`。

- [x] **Step 1:** 写失败测试 `test_hf_daily_papers_adapter_returns_papers`（2 条有效 + 1 条缺 title）+ `test_hf_daily_papers_empty_raises`
- [x] **Step 2:** 运行确认 RED（AttributeError: HF_DAILY_PAPERS 不存在）
- [x] **Step 3:** 加枚举、加适配器、加分派
- [x] **Step 4:** 运行确认 GREEN
- [x] **Step 5:** commit `feat(sources): 新增 hf_daily_papers 适配器调官方 JSON 接口`

---

## Task 4: anthropic selector fixture 回归  ⏳ 进行中

**Files:**
- Test: `tests/test_source_adapters.py`（`test_anthropic_selectors_extract_articles`）
- Fixture: `tests/fixtures/html_anthropic.html`

说明：cohere 已按 ruling 移出本任务（改删除，见 Task 5）。本任务只验证 anthropic 的 selector 能抓到文章，不改适配器代码。

**Interface produced:** anthropic 的最终 selector — `{item: "article", title: "h2, h3", link: "a[href*='-']", date: "time", excerpt: "p"}`（Task 5 原样写进 yaml）。

- [x] **Step 1:** 写失败测试 `test_anthropic_selectors_extract_articles`（3 个卡片，2 个在窗口内；断言首条 url 为 `/claude-opus-5-5` 绝对化、日期 07-23）
- [ ] **Step 2:** 运行确认 RED（fixture/selector 生效前）
- [ ] **Step 3:** 落地 fixture（已建）并确认 selector 抓到文章
- [ ] **Step 4:** 运行确认 GREEN
- [ ] **Step 5:** commit `test(sources): 固定 anthropic selector 的 fixture 回归`

---

## Task 5: 更新 config/sources.yaml 与数量断言  ⬜ 未开始

**Files:**
- Modify: `config/sources.yaml`
- Modify: `tests/test_config.py`（总数 35、profile 计数 8/20/35）
- Modify: `tests/test_source_registry.py`（light/balanced/full → 8/20/35）

**Consumes:** Task 2 的 `options.mode=changelog`（deepseek）、Task 3 的 `kind=hf_daily_papers`、Task 4 的 anthropic selector。

- [ ] **Step 1:** 先改测试断言为 35 / 8 / 20 / 35（观察 RED）
- [ ] **Step 2:** 运行确认 RED（yaml 未改）
- [ ] **Step 3:** 改 yaml：
  - 改 kind→rss 并换 url：openai-news、deepmind-news(`/blog/`)、google-research、microsoft-research、apple-ml（去 selectors/options）
  - hf-daily-papers：`kind: hf_daily_papers`，url `https://huggingface.co/api/daily_papers`
  - deepseek-updates：保留 html_whitelist，`options: {mode: changelog}`
  - anthropic-news：写入 Task 4 selector
  - 删除：zhipu-research、minimax-news、jiqizhixin、qwen-blog、meta-ai-blog、mistral-news、cohere-blog
  - 新增 7 rss（group: media）：mit-tech-review-ai(BF,w17)、latent-space(F,w15)、simon-willison(F,w14)、wired-ai(F,w15)、infoq-cn(BF,w16)、leiphone(F,w15)、ithome(F,w12)
- [ ] **Step 4:** 运行 `pytest tests/test_config.py tests/test_source_registry.py` 确认 GREEN
- [ ] **Step 5:** commit `chore(sources): 替换失效源、删除停更源、新增 7 个 RSS 源`

---

## Task 6: 全量回归与实跑抽查  ⬜ 未开始

- [ ] **Step 1:** `ruff check . && ruff format --check .`
- [ ] **Step 2:** `pytest`，全绿
- [ ] **Step 3:** 对本地可达的源各跑一次 `python -m ai_news_sniffer sources test <id>`（openai/deepmind/google-research/microsoft-research/apple-ml/hf-daily-papers/deepseek-updates/anthropic 及新增 7 源中可达者），记录结果
- [ ] **Step 4:** 非本地网络原因的失败回到对应 Task 修正
- [ ] **Step 5:** commit（如有修正）
