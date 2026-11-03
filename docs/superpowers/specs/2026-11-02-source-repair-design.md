# 失效新闻源修复与替换设计

日期：2026-11-02
状态：待确认

## 意图与背景

系统已运行数月，`config/sources.yaml` 中 35 个源里，25 个启用源（balanced 档）仅 10 个成功。
线上 `source-health.json` 显示 13 个 HTML 源自上线起连续失败 96 次、从未成功，说明它们是一开始就没配好，并非近期失效。

本次目标：把这批失效源逐个修复或替换，访问不到 / 不更新的直接删除，并补充几个已验证可用的新源。
仅做本次修复，不新增“失效自动发现”机制（已与用户确认）。

## 目标

- 让 official / research 分组恢复足够的成功源，日报不再因候选过少进入降级空转。
- 失效源：能救则救（改 RSS 或改 selector），救不动则删除。
- 新增 7 个已验证 RSS 源。
- 修复 hacker-news 的单条坏 URL 拖垮整源的 bug。

## 非目标

- 不做失效源自动发现 / 自动修复机制。
- 不新增通用可配置适配器（已确认走方案 A，针对性实现）。
- 不处理 kimi / qbitai 被错误暂停的问题（保留现状，用户已确认丢弃该修复）。

## 反目标（即使技术上通过也算失败）

- 引入第三方非官方 RSS 作为官方源（如 hf-daily-papers 的 takara.ai）。
- 为仅一个源就设计一层通用配置抽象，增加后续维护成本。

## 约束

- 常规 CI 不得访问线上站点（`docs/...source-strategy` 第 292 行），新增逻辑用本地 fixture 测试。
- 源 URL 必须 HTTPS（`SourceConfig.require_https`）。
- `tests/test_config.py` 与 `tests/test_source_registry.py` 对源总数和各档位数量有精确断言，必须同步更新。

## 方案选择

**适配器实现方式**：已确认走方案 A（针对性实现），因为当前不存在可配置通用适配器，且本次每种特殊结构只有一个源使用，通用化没有第二个受益者。

- deepseek-updates：扩展现有 HTML 适配器，新增 `options.mode: changelog`。
- hf-daily-papers：新增独立 `hf_daily_papers` 适配器，调官方 JSON 接口。

## 逐源处理清单

### 改为 RSS（kind: html_whitelist → rss）

| id | 新 RSS URL | 最新一条（探测时） |
|---|---|---|
| openai-news | https://openai.com/news/rss.xml | 10-30 |
| deepmind-news | https://deepmind.google/blog/rss.xml | 10-28 |
| google-research | https://research.google/blog/rss/ | 10-27 |
| microsoft-research | https://www.microsoft.com/en-us/research/feed/ | 10-30 |
| apple-ml | https://machinelearning.apple.com/rss.xml | 10-26（原为 HTML，一并换 RSS） |

说明：openai 页面返回 403（反爬），但官方 RSS 正常。deepmind 博客已从 `/discover/blog/` 迁到 `/blog/`。

### 改 selector（保持 html_whitelist）

| id | selector 调整 |
|---|---|
| anthropic-news | item 用文章卡片容器，title 取 `h1,h2,h3`，date 取 `time`，link 取 `a` |
| cohere-blog | item 用 `a[href^="/blog/"]`，date 取卡片内含日期的 `p`（eyebrow 文本），title 取卡片内标题 |

具体 selector 在实现时用保存的页面 fixture 验证，确保能抓到带日期的文章并落入 48h 窗口。

### 新增专用适配器（方案 A）

- **deepseek-updates**：HTML 适配器加 `changelog` 模式。页面是 Docusaurus 更新日志，每条形如标题 `Date: 2026-10-17`，正文在标题后。模式逻辑：按 `Date: YYYY-MM-DD` 标题切分，标题作日期，紧随内容作标题+摘要，链接用页面锚点。
- **hf-daily-papers**：新增 `SourceKind.HF_DAILY_PAPERS` 与 `HfDailyPapersAdapter`，请求 `https://huggingface.co/api/daily_papers`，取 paper 的 title、发布日期、arxiv/HF 链接、summary。用官方接口，不用第三方 RSS。

### 删除（访问不到 / JS 渲染无链接 / 超 60 天未更新）

| id | 原因 |
|---|---|
| zhipu-research | 卡片靠 JS 跳转，HTML 无链接；最近一篇 08-26 |
| minimax-news | 纯 JS 渲染，HTML 无日期；域名已迁 minimax.cn |
| jiqizhixin | 首页仅 3KB，纯 JS 渲染 |
| qwen-blog | 旧博客 2025-09 起停更，新站 JS 渲染 |
| meta-ai-blog | Actions 上同样抓取失败 |
| mistral-news | Actions 上可访问但解析失败；本机连不上无法定位。若要保留需另跑 source-audit 排查 |

### 新增源（均已验证 RSS 可用，kind: rss）

| id | name | group | profiles | 权重 | 近 7 天条数 |
|---|---|---|---|---|---|
| mit-tech-review-ai | MIT Technology Review AI | media | balanced, full | 17 | 6 |
| latent-space | Latent Space | media | full | 15 | 11 |
| simon-willison | Simon Willison's Weblog | media | full | 14 | 16 |
| wired-ai | WIRED AI | media | full | 15 | 10 |
| infoq-cn | InfoQ 中文 | media | balanced, full | 16 | 20 |
| leiphone | 雷锋网 | media | full | 15 | 20 |
| ithome | IT 之家 | media | full | 12 | 60（内容较杂，低权重，仅 full） |

分组、档位、权重为设计方给出的默认值，待用户确认。

### bug 修复

- **hacker-news**：逐条构造 `RawArticle` 外包 try/except，`ValidationError` 时跳过该条并继续，不再让整个源失败。

## 数量核算（影响测试断言）

- 原 35 源 − 删 6 + 新增 7 = **36 源**。
- light 档：删除项中 qwen(L)、minimax(L)、jiqizhixin(B)、zhipu(L)、meta(L)... 需按实际 profiles 重算。实现时以 `config/sources.yaml` 最终值为准，同步更新 `test_config.py` 与 `test_source_registry.py` 的 12/25/35 三个数字。
- 最终三档数量在实现阶段确定后写死进测试，并在报告里说明。

## 验证

- 新增/修改逻辑：用保存的页面 fixture 和接口样本做单元测试（deepseek changelog、hf_daily_papers、hacker-news 跳过坏 URL、anthropic/cohere selector）。
- 全量 `pytest` 通过（含更新后的数量断言）。
- 用 `python -m ai_news_sniffer sources test <id>` 对可联网的源做一次实跑抽查（本地网络可达的那些）。
- 不在常规 CI 中访问线上站点。

## 留给实现者的开放项

- anthropic / cohere / deepseek 的最终 selector 字符串，以保存的 fixture 为准敲定。
- 三档最终数量，由最终配置决定。
- 新源的 `independence_group` 默认等于各自 id（沿用现有约定）。
