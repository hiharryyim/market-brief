# 哈利每日 Market Brief

**English** | [简体中文](README.zh-CN.md)

> An autonomous agent that compiles and emails a daily market brief, operated from a local agent desktop with scheduled jobs and a logged-in browser.

[![Not Investment Advice](https://img.shields.io/badge/⚠️-Not%20Investment%20Advice-orange)]() [![Built with Claude Code](https://img.shields.io/badge/built%20with-Claude%20Code-blue)]()

<p align="center">
  <img src="assets/brief-screenshot.jpg" alt="Market Brief email on mobile" width="320">
  <br>
  <em>A brief rendered as a mobile-first email — red = up, green = down (China convention).</em>
</p>

> **Note:** This repository is a design case study, not a clone-and-run application. The pipeline depends on a local Futu OpenD gateway, quote permissions, Gmail SMTP, scheduled local agent jobs, and an optional logged-in Chrome session for subscription media. What's documented here is the **architecture, data contract, and design decisions** — see [`docs/`](docs/).

## Overview

A tool that emails a team a concise, mobile-first **market brief four times a day**, aligned to the Asia and US trading sessions. It runs as an agent inside Claude Code, splitting cleanly into three responsibilities:

- **Collect** — a Python pipeline gathers data from multiple sources and emits one structured JSON.
- **Write** — the agent reads that JSON and composes an analyst-style brief, working strictly from the data.
- **Deliver** — the brief is rendered to a responsive HTML email and sent to the team.

Four scheduled tasks trigger this flow automatically around market opens and closes.

## Features

- **Scheduled delivery** — four briefs per day (Asia pre-open / Asia midday / US pre-open / US close), each tuned to its session.
- **Multi-stage news pipeline** — multi-query recall, history and cross-section dedupe, recency windows, title-similarity filtering, and source weighting.
- **Market-wide hotspot scan** — surfaces sectors moving across the entire US market, independent of the watchlist.
- **Analyst research digest** — recent rating and target-price changes (US & HK).
- **Community sentiment** — quotes real retail posts rather than generic summaries.
- **Subscription-media enrichment** — reads Bloomberg, FT, and WSJ through the user's logged-in Chrome session, while keeping Futu news in every target section as a non-blocking fallback.
- **Cross-routine external dedupe** — canonical article URLs are retained for seven days so the four daily briefs do not repeat the same subscription story.
- **Grounded writing** — the agent never fabricates figures; if data is missing, it describes direction only.
- **Mobile-first output** — responsive HTML email with China-convention coloring.

## Architecture

```
Market data ──► fetch_data.py ──► market_data.json ──► agent writes brief ──► send_email.py ──► email
(Futu · yfinance ·   (pipeline:        (structured        (JSON + verified         (Markdown →         (Gmail SMTP,
 Futu News/Community) dedupe/filter)    data contract)      subscription news)       responsive HTML)    BCC to team)
                                                        ▲
                                      logged-in Chrome: Bloomberg · FT · WSJ

           ▲
   Claude Code scheduled tasks (4×/day) trigger the flow
```

The Python pipeline emits one JSON document as the market-data contract. The writer may add subscription journalism only after reading the original article in Chrome; if Chrome or a publisher fails, it continues with Futu news. This separation keeps market figures grounded while allowing higher-quality context. Full data flow, pipeline stages, and the JSON schema are documented in [`docs/architecture.md`](docs/architecture.md).

## Inputs and outputs

| Inputs | Outputs |
|---|---|
| Watchlist (Futu), market data sources, and configuration | `market_data.json` → an agent-written Markdown brief → a responsive HTML email, four times per day |

## Tech stack & data sources

- **Quotes** — Futu OpenAPI (HK/US), yfinance (indices, commodities, FX, rates)
- **Hotspots** — yfinance predefined screeners + Futu `get_owner_plate`
- **News / research / community** — Futu News API (`news_type` 1/3) + Futu Community
- **Subscription media** — logged-in Chrome (Bloomberg, Financial Times, Wall Street Journal); Agent Reach/Exa is discovery-only
- **Delivery** — Gmail SMTP, mobile-first HTML
- **Orchestration** — Claude Code scheduled tasks (cron, local execution)

## Project structure

```
.
├── README.md / README.zh-CN.md   # this page (EN / 中文)
├── CLAUDE.md                      # internal project spec the agent follows
├── CHANGELOG.md                   # version history (V4 → V10)
├── docs/
│   ├── architecture.md            # data flow, pipeline stages, JSON schema
│   └── design-notes.md            # key design decisions and trade-offs
├── skill/SKILL.md                 # the brief generator packaged as a reusable skill
├── routines/                      # the four scheduled-task prompts
├── scripts/
│   ├── fetch_data.py              # data pipeline → structured JSON
│   └── send_email.py              # Markdown → responsive HTML → Gmail SMTP
└── config/                        # *.example templates only (real credentials gitignored)
```

## Development history

The project evolved across many iterations (V4 → V10), each driven by a concrete limitation encountered while running it live. The notable design decisions and trade-offs are written up in [`docs/design-notes.md`](docs/design-notes.md); the full version history is in [`CHANGELOG.md`](CHANGELOG.md).

## Disclaimer

This project and any output it generates are for informational purposes only and **do not constitute investment advice**.
