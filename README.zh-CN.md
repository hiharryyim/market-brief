# 哈利每日 Market Brief

[English](README.md) | **简体中文**

> 一个本地自动化 agent：按交易时段编纂并推送每日市场简报，并通过已登录浏览器补充订阅外媒。

[![Not Investment Advice](https://img.shields.io/badge/⚠️-不构成投资建议-orange)]() [![Built with Claude Code](https://img.shields.io/badge/built%20with-Claude%20Code-blue)]()

<p align="center">
  <img src="assets/brief-screenshot.jpg" alt="移动端 Market Brief 邮件" width="320">
  <br>
  <em>渲染为移动端优先的邮件——涨红跌绿（中国市场惯例）。</em>
</p>

> **说明：** 本仓库是设计案例，而非开箱即用的应用。整条 pipeline 依赖本地 Futu OpenD、行情权限、Gmail SMTP、本地 agent 定时任务，以及用于订阅外媒增强的已登录 Chrome 会话。这里记录的是**架构、数据契约与设计决策**——详见 [`docs/`](docs/)。

## 概览

一个工具，每天**四次**给团队推送简洁的移动端优先市场简报，对齐亚盘与美盘交易时段。它作为 agent 跑在 Claude Code 里，职责清晰地分为三块：

- **采集** —— Python pipeline 从多个数据源抓取数据，输出一份结构化 JSON。
- **撰写** —— agent 读取该 JSON，以分析师口吻撰写简报，严格基于数据。
- **推送** —— 简报渲染为响应式 HTML 邮件并发送给团队。

四个定时任务在开收盘前后自动触发整条流程。

## 功能

- **定时推送** —— 每天 4 班（亚盘前瞻 / 亚盘午间 / 美盘前瞻 / 美盘收盘），各自针对所属时段。
- **多阶段新闻 pipeline** —— 多查询召回、历史与跨板块去重、时效窗口、标题相似度过滤、来源加权。
- **全市场热点扫描** —— 发现整个美股市场在异动的板块，不依赖自选股。
- **机构研报摘要** —— 近期评级与目标价变动（美股 & 港股）。
- **社区情绪** —— 引用股民帖子原话，而非泛泛概括。
- **订阅外媒增强** —— 通过用户已登录的 Chrome 读取 Bloomberg、FT、WSJ，同时在四个目标板块保留 Futu 兜底，外媒失败不影响发送。
- **外媒跨 routine 去重** —— 规范化文章 URL 保留 7 天，避免一天四封简报反复出现同一篇订阅报道。
- **有据可循的写作** —— agent 绝不编造数字；数据缺失时只描述方向。
- **移动端优先输出** —— 响应式 HTML 邮件，涨红跌绿。

## 架构

```
市场数据 ──► fetch_data.py ──► market_data.json ──► agent 撰写简报 ──► send_email.py ──► 邮件
(Futu · yfinance ·  (pipeline:        (结构化            (JSON + 已验证             (Markdown →         (Gmail SMTP,
 Futu 新闻/社区)     去重/过滤)         数据契约)          订阅外媒)                  响应式 HTML)        BCC 给团队)
                                                        ▲
                                      已登录 Chrome：Bloomberg · FT · WSJ

           ▲
   Claude Code 定时任务（每天 4 次）触发流程
```

Python pipeline 输出一份 JSON 作为行情数据契约；agent 只有在通过 Chrome 读取原站正文后，才补充订阅媒体内容。Chrome 或媒体失败时继续使用 Futu 新闻。这既保证市场数字有据可循，也提高了背景信息质量。完整数据流、pipeline 阶段与 JSON schema 见 [`docs/architecture.md`](docs/architecture.md)。

## 输入与输出

| 输入 | 输出 |
|---|---|
| 自选股（Futu）、行情数据源、配置 | `market_data.json` → agent 撰写的 Markdown 简报 → 响应式 HTML 邮件，每天 4 次 |

## 技术栈与数据源

- **行情** —— Futu OpenAPI（港/美），yfinance（指数、商品、汇率、利率）
- **热点** —— yfinance 预设筛选器 + Futu `get_owner_plate`
- **新闻 / 研报 / 社区** —— Futu News API（`news_type` 1/3）+ Futu Community
- **订阅外媒** —— 已登录 Chrome（Bloomberg、Financial Times、Wall Street Journal）；Agent Reach/Exa 只做候选发现
- **推送** —— Gmail SMTP，移动端优先 HTML
- **编排** —— Claude Code 定时任务（cron，本地执行）

## 项目结构

```
.
├── README.md / README.zh-CN.md   # 本页（英文 / 中文）
├── CLAUDE.md                      # agent 遵循的内部项目规格
├── CHANGELOG.md                   # 版本历史（V4 → V10）
├── docs/
│   ├── architecture.md            # 数据流、pipeline 阶段、JSON schema
│   └── design-notes.md            # 关键设计决策与取舍
├── skill/SKILL.md                 # 把简报生成打包成可复用 skill
├── routines/                      # 4 个定时任务 prompt
├── scripts/
│   ├── fetch_data.py              # 数据 pipeline → 结构化 JSON
│   └── send_email.py              # Markdown → 响应式 HTML → Gmail SMTP
└── config/                        # 仅 *.example 模板（真实凭证已 gitignore）
```

## 演进历史

项目经过多轮迭代（V4 → V10），每一步都由实际运行中遇到的具体限制驱动。值得一提的设计决策与取舍写在 [`docs/design-notes.md`](docs/design-notes.md)；完整版本历史见 [`CHANGELOG.md`](CHANGELOG.md)。

## 免责声明

本项目及其产出仅供参考，**不构成投资建议**。
