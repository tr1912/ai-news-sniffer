# AI News Sniffer · AI 新闻日报

无人值守 AI 新闻日报系统 — 每日自动从免费公开源采集资讯，经 AI 筛选、编辑后生成中文移动端日报，部署到 GitHub Pages 并推送通知。

## 本地搭建

```bash
python3.12 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
python -m pip install -e '.[dev]'
cp .env.example .env           # 填写 API Key 等环境变量
```

应用在运行时从环境变量读取密钥，生产环境不会自动加载 `.env` 文件。本地开发时请手动 `export` 或使用 `source .env`。

## 运行测试

```bash
ruff check src tests
pytest
```

## 本地试运行

```bash
python -m ai_news_sniffer \
  --runtime-dir .local/runtime-data \
  --output-dir build/site \
  build --target-date 2026-07-23 --dry-run
```

在浏览器中打开 `build/site/index.html` 即可预览。试运行不会写入指纹、不会部署 Pages、不会发送通知。

## 来源配置

`config/sources.yaml` 包含经过审查的 35 个全球中英文信息源白名单，以及所有来源 / 分组的开关。三档覆盖级别快速切换：

| 配置档 | 来源数 | AI 候选上限 |
|--------|--------|-------------|
| `light` | 12 | 20 |
| `balanced` | 25 | 30 |
| `full` | 35 | 40 |

在不联网的情况下查看当前生效的来源：

```bash
ai-news-sniffer sources list --profile balanced
ai-news-sniffer sources candidates
```

如需验证某个来源的连通性，使用 `ai-news-sniffer sources test SOURCE_ID`。测试成功后会自动清除运行时的自动暂停状态，但**不会**修改 `config/sources.yaml`。

## 模板自定义

将 `templates/default` 复制为 `templates/<新名称>`，编辑其中的 Jinja2 模板和 CSS 文件，然后在 `config/app.yaml` 中设置 `template: <新名称>`。后续运行会使用新模板重新渲染所有已存储的日报 JSON。

## 供应商扩展

在 `config/providers.yaml` 中添加新条目，将其 API Key 设置为 GitHub Secret，并将供应商 ID 加入 `fallback_order`。使用 `api_style: openai_chat_completions` 即可兼容 DeepSeek、Kimi、MiniMax 等 OpenAI 兼容接口。

## 故障行为

- **来源故障**：记录日志并隔离，不影响其他来源的采集
- **供应商故障**：自动按 `fallback_order` 切换到备用供应商；全部失败时生成标注来源的摘要日报
- **页面校验**：发布前会对生成的日报 URL 进行可达性校验，确保内容已正确部署
- **通知故障**：每个通道的发送结果独立记录在 `runtime-data/runs/` 中
- **来源降级**：同一来源连续 3 次失败标记为降级，连续 7 次自动暂停；暂停状态的来源在下一次成功的通知中会附带维护提醒
- **手动恢复**：使用来源审计工作流手动测试，仅在真实网络审计成功后自动解除暂停

---

详细部署说明请参阅 → [DEPLOY.md](docs/DEPLOY.md)
