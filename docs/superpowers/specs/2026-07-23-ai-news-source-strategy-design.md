# AI 新闻嗅探器：新闻源子系统设计规格

日期：2026-07-23

状态：已通过对话评审，等待书面规格复核

关联规格：`docs/superpowers/specs/2026-07-23-ai-news-sniffer-design.md`

## 1. 目标与原则

新闻源子系统每天从一组明确配置的中英文公开来源采集候选新闻，为后续规则评分和 AI 编辑提供可追溯输入。它必须满足：

- 正式来源由白名单控制，AI 不得自行启用来源。
- RSS、Atom、公开 API 和 GitHub Releases 优先。
- 只对白名单中的少数重要官网使用 HTML 解析。
- 采集标题、日期、短摘要和原文链接，不复制完整文章或绕过付费墙。
- 单个来源失效不能阻断日报。
- 每个来源、来源组和运行模式均可通过配置开关。
- 模型输入有独立候选数量与字符预算；采集数量不等于模型输入数量。
- 新来源可以被发现，但必须经人工修改配置并提交后才能启用。

## 2. AI 与采集程序的职责边界

程序负责：

- 决定本次启用哪些来源。
- 从来源抓取候选条目。
- 规范化、时间过滤、确定性去重和规则评分。
- 验证来源身份与事实确认状态。
- 按候选数量和字符预算裁剪模型输入。
- 校验模型返回的事件和来源 ID。

AI 只接收已经规范化的候选条目，并负责：

- 语义事件聚类。
- 重要性复核和最终排序建议。
- 新闻分类。
- 中文标题、事实摘要和“为什么重要”。
- 当日总览和头条选择。

AI 不得联网补充候选池，不得返回未知来源 ID，不得把模型记忆中的消息加入日报。校验失败的输出必须重试或进入降级模式，不能直接发布。

## 3. 首版正式来源白名单

首版配置 35 个来源。`L`、`B`、`F` 分别表示属于 `light`、`balanced`、`full` 运行模式。来源比例用于白名单构成和采集预算，不是日报内容的固定比例。

### 3.1 官方一手来源：17 个

| ID | 来源 | 首选采集方式 | 模式 |
|---|---|---|---|
| `openai-news` | [OpenAI Newsroom](https://openai.com/news/) | HTML 白名单 | L/B/F |
| `anthropic-news` | [Anthropic Newsroom](https://www.anthropic.com/news) | HTML 白名单 | L/B/F |
| `deepmind-news` | [Google DeepMind News](https://deepmind.google/discover/blog/) | HTML 白名单 | L/B/F |
| `google-research` | [Google Research Blog](https://research.google/blog/) | RSS/Atom 优先 | B/F |
| `meta-ai-blog` | [Meta AI Blog](https://ai.meta.com/blog) | HTML 白名单 | L/B/F |
| `microsoft-research` | [Microsoft Research Blog](https://www.microsoft.com/en-us/research/blog/) | RSS/Atom 优先 | B/F |
| `nvidia-genai` | [NVIDIA Generative AI Blog](https://developer.nvidia.com/blog/blog/category/generative-ai/) | RSS/Atom 优先 | B/F |
| `aws-ai-blog` | [AWS AI/ML Blog](https://aws.amazon.com/blogs/machine-learning/) | RSS/Atom 优先 | F |
| `huggingface-blog` | [Hugging Face Blog](https://huggingface.co/blog) | RSS/Atom | L/B/F |
| `deepseek-updates` | [DeepSeek API 更新](https://api-docs.deepseek.com/updates/) | HTML 白名单 | L/B/F |
| `kimi-platform-blog` | [Kimi 开放平台 Blog](https://platform.kimi.com/blog) | HTML 白名单 | L/B/F |
| `qwen-blog` | [Qwen Blog](https://qwenlm.github.io/blog/) | RSS/Atom 优先 | L/B/F |
| `minimax-news` | [MiniMax 新闻](https://www.minimaxi.com/news) | HTML 白名单 | L/B/F |
| `zhipu-research` | [智谱 GLM Research](https://www.zhipuai.cn/zh/research) | HTML 白名单 | L/B/F |
| `mistral-news` | [Mistral News](https://mistral.ai/news/) | HTML 白名单 | B/F |
| `cohere-blog` | [Cohere Blog](https://cohere.com/blog) | HTML 白名单 | B/F |
| `apple-ml` | [Apple Machine Learning Research](https://machinelearning.apple.com/) | HTML 白名单 | F |

### 3.2 研究与开源来源：8 个

| ID | 来源 | 首选采集方式 | 模式 |
|---|---|---|---|
| `arxiv-ai` | [arXiv API](https://info.arxiv.org/help/api/)；查询 `cs.AI`、`cs.CL`、`cs.LG` | 公开 API | L/B/F |
| `hf-daily-papers` | [Hugging Face Daily Papers](https://huggingface.co/papers) | 公开接口/HTML | L/B/F |
| `vllm-releases` | [vLLM Releases](https://github.com/vllm-project/vllm/releases) | GitHub Releases API | B/F |
| `transformers-releases` | [Transformers Releases](https://github.com/huggingface/transformers/releases) | GitHub Releases API | B/F |
| `llama-cpp-releases` | [llama.cpp Releases](https://github.com/ggml-org/llama.cpp/releases) | GitHub Releases API | B/F |
| `ollama-releases` | [Ollama Releases](https://github.com/ollama/ollama/releases) | GitHub Releases API | F |
| `langchain-releases` | [LangChain Releases](https://github.com/langchain-ai/langchain/releases) | GitHub Releases API | F |
| `llama-index-releases` | [LlamaIndex Releases](https://github.com/run-llama/llama_index/releases) | GitHub Releases API | F |

### 3.3 可信媒体：7 个

| ID | 来源 | 首选采集方式 | 模式 |
|---|---|---|---|
| `36kr` | [36氪官方 RSS](https://www.36kr.com/rss-center) | RSS | B/F |
| `jiqizhixin` | [机器之心](https://www.jiqizhixin.com/) | HTML 白名单 | B/F |
| `qbitai` | [量子位](https://www.qbitai.com/) | HTML 白名单 | B/F |
| `techcrunch-ai` | [TechCrunch AI](https://techcrunch.com/category/artificial-intelligence/) | RSS/Atom 优先 | B/F |
| `venturebeat-ai` | [VentureBeat AI](https://venturebeat.com/category/ai/) | RSS/Atom 优先 | F |
| `the-verge-ai` | [The Verge AI](https://www.theverge.com/ai-artificial-intelligence) | RSS/Atom 优先 | F |
| `ars-ai` | [Ars Technica AI](https://arstechnica.com/ai/) | RSS/Atom 优先 | F |

### 3.4 社区发现来源：3 个

| ID | 来源 | 首选采集方式 | 模式 |
|---|---|---|---|
| `hacker-news` | [Hacker News API](https://github.com/HackerNews/API) | 公开 API | B/F |
| `github-trending` | [GitHub Trending](https://github.com/trending) | HTML 白名单 | F |
| `hf-trending-models` | [Hugging Face Trending Models](https://huggingface.co/models?sort=trending) | 公开接口/HTML | F |

社区来源只负责发现。其条目必须回溯到论文、仓库、官网或可信媒体原文，不能直接成为主要来源。

## 4. 配置与运行模式

### 4.1 单来源与来源组开关

`config/sources.yaml` 为每个来源声明：

```yaml
active_profile: balanced

source_groups:
  official:
    enabled: true
  research:
    enabled: true
  media:
    enabled: true
  community:
    enabled: true

sources:
  - id: openai-news
    name: OpenAI Newsroom
    kind: html_whitelist
    group: official
    enabled: true
    profiles: [light, balanced, full]
    url: https://openai.com/news/
    categories: [models, products, company]
    weight: 25
```

有效启用状态按以下顺序求值：

1. `sources[].enabled: false` 始终关闭该来源。
2. `source_groups.<group>.enabled: false` 关闭整个来源组。
3. 来源必须属于当前 `active_profile`。
4. 非空的手动 `include_sources` 只在前三步得到的来源中进一步缩小范围，不能重新启用已关闭或不属于当前模式的来源。
5. 手动 `exclude_sources` 最后执行并移除指定来源。

### 4.2 三种预设模式

| 模式 | 来源范围 | 默认 AI 候选上限 | 用途 |
|---|---:|---:|---|
| `light` | 12 个核心官方/研究来源 | 20 | 节省调用费用、快速检查 |
| `balanced` | 25 个官方、研究、媒体和 HN 来源 | 30 | 默认每日运行 |
| `full` | 全部 35 个来源 | 40 | 扩大覆盖或专题检查 |

具体模式成员由第 3 节表格中的 `模式` 列定义。用户可以修改任一来源的 `profiles`，不需要修改业务代码。

### 4.3 AI 输入预算

`config/app.yaml` 增加：

```yaml
editorial:
  max_candidates: 30
  max_excerpt_chars_per_item: 1200
  max_total_prompt_chars: 60000
```

采集 RSS、API 或网页不使用模型 Token。只有规则过滤后的高分候选才进入模型请求。系统必须在调用模型前同时执行候选数量、单条摘要长度和总字符数三项硬限制，并在运行记录中保存估算输入 Token。Token 估算只用于观察成本；不同供应商分词方式不同，因此不能替代字符数硬限制。

### 4.4 手动运行覆盖

GitHub Actions `workflow_dispatch` 增加：

- `source_profile`：`light`、`balanced` 或 `full`。
- `include_sources`：逗号分隔的来源 ID，只运行这些来源。
- `exclude_sources`：逗号分隔的来源 ID，排除这些来源。
- `max_ai_candidates`：本次运行的模型候选上限。

临时覆盖不修改仓库配置。

## 5. 采集与规范化

### 5.1 适配器

- `RssAdapter`：RSS 和 Atom。
- `ApiAdapter`：arXiv、Hacker News 等公开 API。
- `GitHubReleasesAdapter`：GitHub Releases API；不采集普通提交和 README 变更。
- `HtmlWhitelistAdapter`：只处理配置中的明确域名与页面。

HTML 解析优先读取 JSON-LD、Open Graph 和标准时间元数据，其次才使用来源专属 CSS 选择器。首版不引入 Playwright 等浏览器自动化。必须执行 JavaScript、禁止自动访问或无法稳定解析的来源应暂停，不绕过访问限制。

### 5.2 统一候选结构

每个适配器输出：

- 来源 ID、名称、组别和可信度。
- 标题、原始 URL、规范 URL。
- 发布时间和采集时间。
- 语言、作者、短摘要和类别。
- 发现的上游原文链接。
- 解析器版本和必要的非敏感原始元数据。

所有时间以带时区格式存储，展示时转换为北京时间。

## 6. 筛选、确认与 AI 编辑

### 6.1 候选池

每次运行最多回看 48 小时。程序先执行：

- 广告、赞助、招聘、活动预告和弱相关内容过滤。
- URL 规范化和历史指纹过滤。
- 相同 URL 与近似标题去重。
- 社区条目的上游原文解析。
- 100 分规则评分。

规则评分维度保持为：来源可信度 25、事件影响力 25、关注相关度 20、技术产品价值 15、多源佐证 10、时效性 5。

### 6.2 事实确认状态

每个事件必须具有以下状态之一：

- `primary_confirmed`：当事公司、论文或项目仓库直接确认。
- `cross_confirmed`：至少两家相互独立的可信媒体确认。
- `unverified`：只有单一媒体、匿名消息或社区讨论。

多家媒体转载同一通讯稿只算一个来源。`unverified` 事件保留在运行记录中，但不进入正式日报；首版不设置传闻专区。

### 6.3 最终确定性约束

AI 排序后，程序再次强制：

- 正常发布 8–15 条；质量不足时允许少于 8 条。
- 同一事件只能出现一次。
- 同一主要来源最多 2 条。
- 同一类别最多 3 条。
- 社区来源不能直接成为主要来源。
- `unverified` 事件不能发布。
- 达到质量门槛的重大商业或政策事件至少保留一个位置。
- 不用低分新闻填充数量。

## 7. 新来源发现与人工审批

正式媒体和社区条目中反复出现的新域名可以写入 `candidate-sources.json`。每个候选记录：

- 域名、样例 URL 和页面标题。
- 首次与最近发现时间。
- 引用它的正式来源。
- 建议来源组、采集方式和初始权重。
- 风险说明和发现理由。

候选来源默认禁用。日报可以显示候选数量，但首版只允许用户手动修改 `config/sources.yaml` 并提交来批准来源。自动任务不得修改主分支中的正式白名单。

## 8. 状态、健康度与故障

`runtime-data` 分支增加：

- `source-health.json`
- `candidate-sources.json`
- `source-runs/YYYY-MM-DD.json`

每日来源运行记录包含启用来源、配置模式、各来源数量和错误、规则过滤前后数量、模型候选数量、估算输入 Token、最终引用来源和未确认事件数量。

来源健康策略：

- 连续失败 1–2 次：记录错误并继续。
- 连续失败 3 次：标记降级并在运行信息中提示。
- 连续失败 7 次：在运行状态中自动暂停并发送维护提醒，不修改主分支配置。
- 手动执行真实网络审计成功后清除运行状态中的自动暂停标记；配置中的来源和来源组开关仍然优先。

单个来源失败不影响其他来源。来源不足时生成精简日报，并明确显示覆盖率和降级状态。

## 9. 管理命令

首版提供：

```bash
python -m ai_news_sniffer.cli sources list
python -m ai_news_sniffer.cli sources test openai-news
python -m ai_news_sniffer.cli sources audit
python -m ai_news_sniffer.cli sources candidates
```

`sources list` 和 `sources candidates` 为只读操作。`sources test` 测试指定来源。`sources audit` 执行真实网络健康检查，但不自动批准来源、不修改主分支。

## 10. 测试

- 使用固定 RSS、JSON、GitHub API 和 HTML 样本测试各适配器。
- 测试 HTML 结构变化、缺失日期、无效链接和禁止访问。
- 测试来源、来源组、运行模式和手动覆盖的优先级。
- 测试模型候选数量、单条字符数和总字符预算。
- 测试社区消息不能绕过上游原文验证。
- 测试转载稿不被误算为独立佐证。
- 测试未知来源 ID 的模型输出会被拒绝。
- 测试单来源失败时其余来源继续执行。
- 常规 CI 不访问实时网站；真实网络检查只由 `sources audit` 或手动 `dry-run` 执行。
- `dry-run` 页面必须显示来源覆盖率、降级来源、模型候选数量和估算 Token。

## 11. 验收条件

1. 35 个初始来源全部存在于配置中。
2. 任一来源和任一来源组均可关闭。
3. `light`、`balanced`、`full` 三种模式按定义启用正确来源。
4. 模型输入受到候选数量、单条字符数和总字符数硬限制。
5. AI 无法引入候选池外的新闻或来源。
6. 官方、媒体和社区内容按事实确认规则处理。
7. 新来源只能进入候选清单，不能自动启用。
8. 单个来源失效不会阻断日报。
9. 日报与运行记录说明本期实际来源覆盖和模型输入估算。
10. 固定样本测试不依赖实时网络，真实来源可通过手动审计检查。
