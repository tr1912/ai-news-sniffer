# AI News Sniffer — 项目记忆

## 项目概述
无人值守 AI 新闻日报系统：每日采集 → AI 筛选 → 中文 HTML 日报 → GitHub Pages → 通知推送。

## 技术栈
Python 3.12+, Pydantic 2, httpx, feedparser, RapidFuzz, Jinja2, OpenAI SDK, pytest, respx, Ruff, GitHub Actions.

## 工作目录
Git worktree: `D:\aiProjects\ai-news-sniffer‌\.worktrees\ai-news-sniffer-v2`
分支: `feature/ai-news-sniffer-v2`

## 实现进度
- ✅ Source Tasks 1-7: 来源采集子系统（35 个源、5 种适配器、去重评分、健康度、CLI）
- ✅ Main Task 4: 运行状态持久化（prepared → published → notified）
- ✅ Main Task 5: 模型供应商链和语义编辑层（ProviderChain、OpenAI 兼容客户端、EditorialService）
- ✅ Main Task 6: 模板渲染和静态站点生成（选择器、Jinja2 沙盒、5 模板、移动优先紫色系）
- ✅ Main Task 7: 通知网关（MeoW/企微/Webhook、指数���避重试、通道隔离）
- ✅ Main Task 8: 管线编排和 CLI（Pipeline 7 步、build/verify/mark-published/notify/notify-failure）
- ✅ Main Task 10: GitHub Actions CI/CD（ci.yml + daily-digest.yml 4-job 流程、README 手册）
- 🎉 **全部完成** — 75/75 测试通过

## GitHub Pages 域名
- 自定义域名 `www.happyxiao1435.top` 绑在 `tr1912.github.io` 用户主页仓库
- 账号下所有项目 Pages 都走该域名，路径前缀为 `/<repo-name>/`
- `ai-news-sniffer` 正确访问地址：`https://www.happyxiao1435.top/ai-news-sniffer/`
- 仓库变量 `PUBLIC_BASE_URL` 应设为 `https://www.happyxiao1435.top/ai-news-sniffer`

## 关键约定
- TDD 先行：失败测试 → 最小实现 → 验证通过
- 配置驱动：35 源在 YAML，不在代码
- 安全：API Key 只走环境变量，不写 YAML
- 指纹去重：防止同一新闻重复发布
- AI 预算硬限制：候选数、单条字符、总提示字符
- 多样性约束：同源 ≤2、同类 ≤3、社区不能主源、unverified 不发布
