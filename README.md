# 哈利每日 Market Brief

> An autonomous, multi-session market-intelligence agent that writes and emails a polished daily market brief — built entirely inside [Claude Code](https://claude.com/claude-code) through "vibe coding."
>
> 一个自动化的市场情报 agent：自动抓数据、写分析、四班次推送移动端邮件简报。完全在 Claude Code 里通过 "vibe coding" 搭建。

[![Not Investment Advice](https://img.shields.io/badge/⚠️-Not%20Investment%20Advice-orange)]() [![Built with Claude Code](https://img.shields.io/badge/built%20with-Claude%20Code-blue)]()

> ⚠️ **This repo is a design case study, not a clone-and-run app.** The pipeline depends on a local Futu OpenD gateway, a brokerage account with quote permissions, Gmail SMTP, and Claude Code scheduled tasks. The value here is the **architecture, prompt engineering, and the evolution story** — not a turnkey binary. See [`docs/`](docs/).

---

## 🇺🇸 English

### What it is

A personal tool that emails my team a clean, mobile-first **market brief four times a day**, timed to the Asia and US trading sessions. It runs as an agent inside Claude Code:

1. A Python pipeline (`fetch_data.py`) pulls live quotes, news, analyst research, community sentiment, and a **whole-market "what's hot today" scan** — then dedupes, filters, and emits one structured JSON.
2. The AI reads that JSON and writes the brief as Markdown — **never fabricating numbers**, only describing what's in the data.
3. `send_email.py` renders it to a responsive HTML email and BCC-sends it to the team.
4. Four [scheduled tasks](routines/) fire this flow automatically around market opens/closes.

### The interesting part: market-wide hotspot discovery

Most "watchlist" tools only tell you about stocks you already track. The 🔥 **Today's Hotspots** module finds the sectors moving *across the entire US market* — even ones I've never added:

```
yfinance screeners (day_gainers / losers / most_actives)   →  discover movers (free, no brokerage entitlement)
        ↓ feed tickers to Futu
Futu get_owner_plate  →  map movers to Chinese sector names, count frequency  →  today's hot sectors
        ↓
overlap-dedupe + noise filtering  →  e.g. "🚀 Space / Aerospace (7 stocks +15~22%)"
```

### How it works (inputs → outputs)

| Input | Processing | Output |
|---|---|---|
| Watchlist (Futu), data sources, config | Multi-stage news pipeline (recall → dedupe → recency → similarity → weighting), hotspot scan, analyst-research channel, community sentiment | One `market_data.json` → AI-written Markdown → **responsive HTML email**, 4×/day |

See [`docs/architecture.md`](docs/architecture.md) for the full data flow and JSON schema.

### Tech & data sources

- **Quotes:** Futu OpenAPI (HK/US), yfinance (indices, commodities, FX, rates)
- **Hotspots:** yfinance predefined screeners + Futu `get_owner_plate`
- **News / research / community:** Futu News API (`news_type` 1/3), restricted WebSearch (Bloomberg/CNBC)
- **Delivery:** Gmail SMTP, mobile-first HTML
- **Orchestration:** Claude Code scheduled tasks (cron, local execution)

### The build story

This started as a one-off script and evolved to **V9** over many iterations — each driven by a real failure or limitation. The most instructive moments are written up in [`docs/design-notes.md`](docs/design-notes.md): discovering a Futu API wasn't entitled and pivoting the whole hotspot design; a silent OTC-batch bug that made the AI hallucinate prices; a timezone migration. The full version history is in [`CHANGELOG.md`](CHANGELOG.md).

---

## 🇨🇳 中文

### 这是什么

一个个人工具，每天**四班次**（对齐亚盘/美盘开收）给团队推送移动端优先的市场简报。它作为 agent 跑在 Claude Code 里：

1. Python pipeline（`fetch_data.py`）抓行情、新闻、机构研报、社区情绪，外加一个**全市场"今日热点"扫描**，去重过滤后输出一份结构化 JSON。
2. AI 读 JSON 写 Markdown 简报——**严禁编造数字**，只描述数据里有的东西。
3. `send_email.py` 渲染成响应式 HTML 邮件，BCC 群发给团队。
4. 四个[定时任务](routines/)在开收盘前后自动触发整条流程。

### 最有意思的部分：全市场热点发现

大多数"自选股"工具只盯你已经关注的票。🔥 **今日热点** 模块能发现**整个美股市场**在异动的板块——哪怕我从没加过自选：

```
yfinance 筛选器（涨幅/跌幅/活跃榜）   →  发现异动个股（免费，不依赖券商选股权限）
        ↓ 喂给 Futu
Futu get_owner_plate  →  把异动股映射到中文板块名、按频次统计  →  今日热点板块
        ↓
重叠去重 + 噪音过滤  →  例如 "🚀 太空/航空航天（7 只 +15~22%）"
```

### 怎么运作（输入 → 输出）

| 输入 | 处理 | 输出 |
|---|---|---|
| 自选股(Futu)、数据源、配置 | 多阶段新闻 pipeline（召回→去重→时效→相似度→加权）、热点扫描、研报频道、社区情绪 | 一份 `market_data.json` → AI 撰写 Markdown → **响应式 HTML 邮件**，每天 4 封 |

完整数据流与 JSON schema 见 [`docs/architecture.md`](docs/architecture.md)。

### 技术与数据源

- **行情：** Futu OpenAPI（港/美），yfinance（指数/商品/汇率/利率）
- **热点：** yfinance 预设筛选器 + Futu `get_owner_plate`
- **新闻/研报/社区：** Futu News API（`news_type` 1/3）、受限 WebSearch（Bloomberg/CNBC）
- **推送：** Gmail SMTP，移动端优先 HTML
- **编排：** Claude Code 定时任务（cron，本地执行）

### 搭建故事

从一个一次性脚本起步，经过多轮迭代到 **V9**——每一步都由真实的踩坑或限制驱动。最有借鉴价值的几次复盘写在 [`docs/design-notes.md`](docs/design-notes.md)：发现某个 Futu 接口没权限、把整个热点设计推倒重来；一个静默的 OTC 批次 bug 让 AI 编造价格；时区迁移。完整版本史见 [`CHANGELOG.md`](CHANGELOG.md)。

---

## Project structure / 项目结构

```
.
├── README.md              # this file
├── CLAUDE.md              # internal project spec the agent follows (中文)
├── CHANGELOG.md           # V4 → V9 evolution
├── docs/
│   ├── architecture.md    # data flow, pipeline stages, JSON schema (I/O)
│   └── design-notes.md    # key decisions & war stories
├── skill/
│   └── SKILL.md           # the brief generator packaged as a reusable skill
├── routines/              # the 4 scheduled-task prompts (agent design samples)
├── scripts/
│   ├── fetch_data.py      # data pipeline → structured JSON
│   └── send_email.py      # Markdown → responsive HTML → Gmail SMTP
└── config/                # *.example templates only (real creds gitignored)
```

## Disclaimer

This project and any output it generates are for informational purposes only and **do not constitute investment advice**. / 本项目及其产出仅供参考，**不构成投资建议**。
