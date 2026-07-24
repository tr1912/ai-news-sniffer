# AI News Sniffer · 部署指南

本文档详细说明如何将 AI News Sniffer 部署到 GitHub，配置定时日报生成与自动发布。

---

## 目录

1. [前置条件](#1-前置条件)
2. [仓库配置](#2-仓库配置)
3. [密钥与变量配置](#3-密钥与变量配置)
4. [GitHub Pages 配置](#4-github-pages-配置)
5. [工作流权限配置](#5-工作流权限配置)
6. [工作流说明](#6-工作流说明)
7. [手动运行](#7-手动运行)
8. [自定义域名](#8-自定义域名)
9. [故障排查](#9-故障排查)

---

## 1. 前置条件

- 一个 **GitHub 仓库**，代码已推送到 `main` 分支
- Python 3.12（已在 `ci.yml` 和 `daily-digest.yml` 中硬编码）
- DeepSeek API Key（或其他 OpenAI 兼容供应商的 Key）
- （可选）MeoW 通知的 Nickname
- （可选）企业微信机器人 Webhook 地址
- （可选）通用 Webhook 地址

---

## 2. 仓库配置

### 2.1 推送代码

```bash
git remote add origin git@github.com:<你的用户名>/ai-news-sniffer.git
git push -u origin main
```

### 2.2 分支保护（建议）

在仓库 Settings → Branches → Branch protection rules 中为 `main` 分支添加保护规则，至少勾选：
- **Require a pull request before merging**
- **Require status checks to pass before merging**（选择 `test` job）

---

## 3. 密钥与变量配置

进入仓库 **Settings → Secrets and variables → Actions**：

### 3.1 必需的 Secrets

| 名称 | 说明 | 获取方式 |
|------|------|----------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key | [platform.deepseek.com](https://platform.deepseek.com) → API Keys |

### 3.2 可选的 Secrets

| 名称 | 说明 | 何时需要 |
|------|------|----------|
| `MEOW_NICKNAME` | MeoW 通知昵称 | 使用 MeoW 通道推送通知时 |
| `WECOM_WEBHOOK_URL` | 企业微信机器人 Webhook | 使用企业微信通道时 |
| `GENERIC_WEBHOOK_URL` | 通用 Webhook 地址 | 使用通用 Webhook 通道时 |

### 3.3 必需的 Variables

| 名称 | 说明 | 示例 |
|------|------|------|
| `PUBLIC_BASE_URL` | 日报公开访问的根 URL，**不含尾部斜杠** | `https://你的用户名.github.io/ai-news-sniffer` |

> ⚠️ 如果在 Variables 页面看不到 "Variables" 标签，说明仓库是个人账户而非组织账户。个人账户同样支持 Variables，路径相同。

### 3.4 通道开关

通知通道的启用在 `config/channels.yaml` 中控制：

```yaml
channels:
  - id: meow
    kind: meow
    enabled: true          # 改为 false 则关闭 MeoW 通知
    nickname_env: MEOW_NICKNAME
  - id: wecom
    kind: wecom
    enabled: false         # 改为 true 则启用企微通知
    endpoint_env: WECOM_WEBHOOK_URL
  - id: webhook
    kind: webhook
    enabled: false         # 改为 true 则启用 Webhook 通知
    endpoint_env: GENERIC_WEBHOOK_URL
```

未启用的通道不需要配置对应的 Secret。

---

## 4. GitHub Pages 配置

### 4.1 启用 Pages

进入仓库 **Settings → Pages**：

1. **Source**：选择 **GitHub Actions**
2. 保存后，Pages 环境会自动创建

### 4.2 Pages 权限

工作流需要 `pages: write` 和 `id-token: write` 权限才能部署到 Pages。这些权限已经在 `daily-digest.yml` 的 `deploy` job 中声明，无需额外配置。

---

## 5. 工作流权限配置

进入仓库 **Settings → Actions → General**：

1. **Actions permissions**：选择 **Allow all actions and reusable workflows**
2. **Workflow permissions**：选择 **Read and write permissions**
3. 勾选 **Allow GitHub Actions to create and approve pull requests**

> 这些权限是工作流写入 `runtime-data` 分支和部署 Pages 所必需的。

---

## 6. 工作流说明

项目包含两个 GitHub Actions 工作流：

### 6.1 CI（`.github/workflows/ci.yml`）

- **触发时机**：`main` 分支 push、所有 Pull Request
- **执行内容**：ruff 代码检查 + pytest 测试 + 覆盖率报告
- **权限**：仅需 `contents: read`

### 6.2 Daily AI Digest（`.github/workflows/daily-digest.yml`）

这是核心工作流，包含 4 个 Job 分阶段执行：

```
build → deploy → finalize → failure-alert
```

#### 各 Job 职责

| Job | 职责 | 条件 |
|-----|------|------|
| **build** | 采集来源 → AI 编辑 → 多样性筛选 → 去重 → 渲染静态站点 → 写 `runtime-data` 分支 | 始终执行 |
| **deploy** | 将 `build/site` 部署到 GitHub Pages | `publish=true` 时 |
| **finalize** | 校验发布 URL → 标记 published → 发送通知 → 持久化状态 | `publish=true` 时 |
| **failure-alert** | 任意前置 Job 失败时，通过可用通道发送故障告警 | 仅失败时 |

#### 调度与触发

| 触发方式 | dry_run | publish | notify |
|----------|---------|---------|--------|
| 定时触发（每日 21:00 北京时间） | false | true | true |
| 手动触发（默认参数） | true | false | false |

#### 手动触发参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `dry_run` | boolean | true | true=仅预览不保存；false=真实运行 |
| `publish` | boolean | false | true=部署到 GitHub Pages |
| `notify` | boolean | false | true=发送通知（需 publish=true） |
| `target_date` | string | 当天 | 可选，格式 `YYYY-MM-DD` |
| `source_profile` | choice | balanced | light / balanced / full |
| `include_sources` | string | 空 | 逗号分隔的来源 ID 白名单 |
| `exclude_sources` | string | 空 | 逗号分隔的来源 ID 黑名单 |
| `max_ai_candidates` | string | "0" | 0=使用配置档默认值 |

#### runtime-data 分支

首次非试运行成功后，工作流会自动创建 `runtime-data` 分支，用于持久化：

- `reports/` — 每日日报 JSON
- `runs/` — 通知发送结果
- `seen_fingerprints.json` — 去重指纹
- `latest.json` — 最新日报元数据
- `source-health.json` — 来源健康状态

> 该分支完全由工作流自动管理，**不要手动编辑**。

#### 并发控制

```yaml
concurrency:
  group: daily-ai-digest
  cancel-in-progress: false
```

同一时间只允许一个 Digest 工作流运行，防止同时多次运行导致状态冲突。

---

## 7. 手动运行

### 7.1 试运行（预览）

进入仓库 **Actions → Daily AI Digest → Run workflow**，保持默认参数直接运行。工作流会在 build 阶段完成后上传一个名为 `ai-digest-preview-<run_id>` 的 Artifact，保存 7 天。

### 7.2 真实运行

1. 进入 **Actions → Daily AI Digest → Run workflow**
2. 设置参数：

   ```
   dry_run:          false
   publish:          true
   notify:           true（需要通知时）
   source_profile:   balanced
   ```

3. 点击 **Run workflow**

4. 等待 build → deploy → finalize 全部完成

5. 访问 `https://你的用户名.github.io/ai-news-sniffer/` 查看日报

### 7.3 补录历史日期

将 `target_date` 设为过去日期（如 `2026-07-20`），可以生成历史日报。注意来源的 `lookback_hours` 默认 48 小时，太早的日期可能采集不到足够内容。

---

## 8. 自定义域名

### 8.1 域名验证

在 GitHub Settings → Pages → Custom domain 中配置：

1. 输入你的域名（如 `ai-news.example.com`）
2. GitHub 会生成一条 TXT 记录用于验证域名所有权
3. 在你的 DNS 服务商添加这条 TXT 记录
4. 等待验证通过（通常几分钟）

### 8.2 DNS 配置

在 DNS 服务商添加 CNAME 记录：

```
类型:   CNAME
名称:   ai-news（子域名前缀）
值:     <你的用户名>.github.io
```

### 8.3 更新 Variables

将 `PUBLIC_BASE_URL` 更新为自定义域名：

```
https://ai-news.example.com
```

> ⚠️ 不要使用泛域名 DNS（`*.example.com`），GitHub Pages 不支持。

---

## 9. 故障排查

### 9.1 build 阶段失败

**症状**：build job 报错退出

**排查步骤**：
1. 检查 `DEEPSEEK_API_KEY` Secret 是否已配置
2. 查看 Actions 日志中 `Build digest` 步骤的错误信息
3. 本地运行 `pytest` 确认代码无问题
4. 使用 `source_profile: light` 减少采集数量重试

### 9.2 deploy 阶段失败

**症状**：deploy job 报错 `HttpError: Resource not accessible by integration`

**排查步骤**：
1. 确认 Settings → Pages → Source 选择了 **GitHub Actions**
2. 确认工作流权限为 **Read and write**（步骤 5）
3. 确认 `deploy` job 声明了 `pages: write` 和 `id-token: write`

### 9.3 通知未收到

**症状**：finalize job 成功但没收到通知

**排查步骤**：
1. 确认 `notify` 参数设为 `true`
2. 检查 `config/channels.yaml` 中对应通道 `enabled: true`
3. 确认对应 Secret 已配置
4. 查看 finalize job 的 `Send notifications` 步骤日志
5. 检查 `runtime-data` 分支 `runs/` 目录下的通知记录

### 9.4 日报内容为空或太少

**症状**：生成的日报几乎没有内容

**排查步骤**：
1. 检查来源是否被限流或屏蔽（查看 `source-health.json`）
2. 尝试切换到 `full` profile：`source_profile: full`
3. 检查 `target_date` 是否超出 48 小时回溯窗口
4. 手动运行来源审计：
   ```bash
   ai-news-sniffer sources candidates
   ```

### 9.5 runtime-data 分支冲突

**症状**：工作流提示 runtime-data 分支 push 冲突

**排查步骤**：
1. 确保并发控制生效（同一时间只有一个工作流运行）
2. 如果持续冲突，删除 `runtime-data` 分支让工作流重新创建：
   ```bash
   git push origin --delete runtime-data
   ```
   > ⚠️ 删除会丢失历史指纹和运行记录，可能导致重复发布

---

## 附录：项目文件结构

```
ai-news-sniffer/
├── .github/workflows/
│   ├── ci.yml                 # CI 工作流
│   └── daily-digest.yml       # 日报工作流
├── config/
│   ├── app.yaml               # 应用配置
│   ├── channels.yaml          # 通知通道配置
│   ├── interests.yaml         # 兴趣关键词
│   ├── providers.yaml         # AI 供应商配置
│   └── sources.yaml           # 35 个新闻来源配置
├── prompts/
│   └── editorial.md           # AI 编辑提示词
├── src/ai_news_sniffer/
│   ├── cli.py                 # 命令行入口
│   ├── pipeline.py            # 7 步管线编排
│   ├── providers/             # 模型供应商链
│   ├── rendering/             # 模板渲染引擎
│   ├── notifications/         # 通知网关
│   ├── selection.py           # 多样性筛选
│   ├── sources/               # 5 种来源适配器
│   └── ...
├── templates/default/
│   ├── report.html.j2         # 日报模板
│   ├── index.html.j2          # 首页重定向
│   ├── archive.html.j2        # 归档页
│   ├── notification.md.j2     # 通知模板
│   └── static/style.css       # 样式
└── tests/                     # 75 个测试用��
```
