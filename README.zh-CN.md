# 哈利每日 Market Brief

[English](README.md) | **简体中文**

> 一个自动化的市场情报 agent：自动抓数据、写分析、四班次推送移动端邮件简报。完全在 [Claude Code](https://claude.com/claude-code) 里通过 "vibe coding" 搭建。

[![Not Investment Advice](https://img.shields.io/badge/⚠️-不构成投资建议-orange)]() [![Built with Claude Code](https://img.shields.io/badge/built%20with-Claude%20Code-blue)]()

<p align="center">
  <img src="assets/brief-screenshot.jpg" alt="移动端 Market Brief 邮件" width="320">
  <br>
  <em>渲染为移动端优先的邮件——涨红跌绿（中国市场惯例）。</em>
</p>

> ⚠️ **本仓库是设计案例，不是开箱即用的 app。** 整条 pipeline 依赖本地 Futu OpenD、带行情权限的券商账号、Gmail SMTP，以及 Claude Code 定时任务。这里的价值是**架构、prompt 工程和演进故事**，不是一个能直接跑的二进制。详见 [`docs/`](docs/)。

## 这是什么

一个个人工具，每天**四班次**（对齐亚盘/美盘开收）给团队推送移动端优先的市场简报。它作为 agent 跑在 Claude Code 里：

1. Python pipeline（`fetch_data.py`）抓行情、新闻、机构研报、社区情绪，外加一个**全市场"今日热点"扫描**，去重过滤后输出一份结构化 JSON。
2. AI 读 JSON 写 Markdown 简报——**严禁编造数字**，只描述数据里有的东西。
3. `send_email.py` 渲染成响应式 HTML 邮件，BCC 群发给团队。
4. 四个[定时任务](routines/)在开收盘前后自动触发整条流程。

## 最有意思的部分：全市场热点发现

大多数"自选股"工具只盯你已经关注的票。🔥 **今日热点** 模块能发现**整个美股市场**在异动的板块——哪怕我从没加过自选：

```
yfinance 筛选器（涨幅/跌幅/活跃榜）   →  发现异动个股（免费，不依赖券商选股权限）
        ↓ 喂给 Futu
Futu get_owner_plate  →  把异动股映射到中文板块名、按频次统计  →  今日热点板块
        ↓
重叠去重 + 噪音过滤  →  例如 "🚀 太空/航空航天（7 只 +15~22%）"
```

## 怎么运作（输入 → 输出）

| 输入 | 处理 | 输出 |
|---|---|---|
| 自选股(Futu)、数据源、配置 | 多阶段新闻 pipeline（召回→去重→时效→相似度→加权）、热点扫描、研报频道、社区情绪 | 一份 `market_data.json` → AI 撰写 Markdown → **响应式 HTML 邮件**，每天 4 封 |

完整数据流与 JSON schema 见 [`docs/architecture.md`](docs/architecture.md)。

## 技术与数据源

- **行情：** Futu OpenAPI（港/美），yfinance（指数/商品/汇率/利率）
- **热点：** yfinance 预设筛选器 + Futu `get_owner_plate`
- **新闻/研报/社区：** Futu News API（`news_type` 1/3）、受限 WebSearch（Bloomberg/CNBC）
- **推送：** Gmail SMTP，移动端优先 HTML
- **编排：** Claude Code 定时任务（cron，本地执行）

## 搭建故事

从一个一次性脚本起步，经过多轮迭代到 **V9**——每一步都由真实的踩坑或限制驱动。最有借鉴价值的几次复盘写在 [`docs/design-notes.md`](docs/design-notes.md)：发现某个 Futu 接口没权限、把整个热点设计推倒重来；一个静默的 OTC 批次 bug 让 AI 编造价格；时区迁移。完整版本史见 [`CHANGELOG.md`](CHANGELOG.md)。

## 项目结构

```
.
├── README.md / README.zh-CN.md   # 本页（英文 / 中文）
├── CLAUDE.md                      # agent 遵循的内部项目规格（中文）
├── CHANGELOG.md                   # V4 → V9 演进
├── docs/
│   ├── architecture.md            # 数据流、pipeline 阶段、JSON schema（输入输出）
│   └── design-notes.md            # 关键决策 & 踩坑复盘
├── skill/SKILL.md                 # 把简报生成打包成可复用 skill
├── routines/                      # 4 个定时任务 prompt（agent 设计样本）
├── scripts/
│   ├── fetch_data.py              # 数据 pipeline → 结构化 JSON
│   └── send_email.py              # Markdown → 响应式 HTML → Gmail SMTP
└── config/                        # 仅 *.example 模板（真实凭证已 gitignore）
```

## 免责声明

本项目及其产出仅供参考，**不构成投资建议**。
