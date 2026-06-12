---
name: market-brief
description: >-
  Generate and email a daily market brief. Pulls live quotes, news, analyst
  research, community sentiment, and a whole-market hotspot scan into one
  structured JSON, writes an analyst-style brief from it (never fabricating
  numbers), and sends it as a mobile-first HTML email. Use for scheduled
  pre-open / midday / close market briefings.
metadata:
  version: "9"
  author: Harry
---

# Market Brief Skill

A reusable recipe for an autonomous daily market brief. This documents the
**inputs, outputs, and contract** so the design can be adapted to another
broker API, market, or delivery channel.

可复用的"每日市场简报"配方。本文档说明**输入、输出、契约**，方便迁移到别的券商 API、市场或推送渠道。

---

## Inputs / 输入

| Input | Source | Notes |
|---|---|---|
| Watchlist / 自选股 | Futu `get_user_security` | Drives per-stock news + quotes; no manual list |
| Market data / 行情 | Futu OpenD + yfinance | HK/US via Futu; indices·commodities·FX·rates via yfinance |
| News / 新闻 | Futu News API `news_type=1` | Multi-query recall per section |
| Research / 研报 | Futu News API `news_type=3` | Analyst ratings; US+HK only |
| Community / 社区 | Futu Community API | Recent posts; titles = retail voices |
| Foreign media / 外媒 | WebSearch (Bloomberg, CNBC) | Restricted: ≤2 calls, ≤3 items, ≤24h |
| Config / 配置 | `config/email.conf`, `config/recipients.txt` | Gmail SMTP + recipients (gitignored) |

**Requires / 依赖:** Futu OpenD running on `127.0.0.1:11111` with HK/US quote
permission; `futu-api` + `yfinance`; a Gmail App Password.

## Processing / 处理

`scripts/fetch_data.py` runs the full pipeline (see
[`../docs/architecture.md`](../docs/architecture.md)) and emits **one JSON**:
multi-stage news filtering (recall → dedupe → recency → similarity → weighting),
a market-wide hotspot scan, an analyst-research channel, and community sentiment.

## Output / 输出

1. **`market_data.json`** — the structured contract (schema in `docs/architecture.md`).
2. **The brief** — Claude reads the JSON and writes Markdown into a fixed
   skeleton (Overview → 🔥 Hotspots → Key News (7 sections) → Macro). **Hard rule:
   never invent a number; if a field is absent, describe direction only.**
3. **The email** — `scripts/send_email.py` renders Markdown → mobile-first HTML
   (red=up / green=down) and BCC-sends via Gmail SMTP.

## Usage / 用法

```bash
# 1. pull data
python3 scripts/fetch_data.py > /tmp/market_data.json

# 2. (agent step) read the JSON, optionally add ≤3 foreign-media items via
#    WebSearch, write /tmp/market_brief.md following the routine prompt.

# 3. send (use --test for yourself; --news-ids-file feeds 7-day dedupe)
python3 scripts/send_email.py \
  --subject "哈利每日 Market Brief · 美盘收盘 · $(date +%Y-%m-%d)" \
  --markdown-file /tmp/market_brief.md \
  --news-ids-file /tmp/used_news_ids.json
```

To run it automatically, wire steps 1–3 into a scheduled task. The four reference
prompts are in [`../routines/`](../routines/) — they differ only in session focus.

## Design principles worth copying / 值得借鉴的设计原则

- **Split discovery from naming.** Free screeners find movers; the broker API
  only names the sectors — no fragile entitlement dependency. / 发现与命名分离。
- **The pipeline emits data; the AI only writes.** A clean JSON contract keeps
  the writer from touching APIs and makes "never fabricate" enforceable. /
  pipeline 只产数据，AI 只写作；契约清晰才能强制"不编造"。
- **Design for partial failure.** Batch-atomic APIs degrade to per-item. /
  为部分失败设计降级。
- **Dedupe across the day.** A rolling 7-day `news_id` cache stops the same story
  appearing in all four briefs. / 跨天滚动去重。
