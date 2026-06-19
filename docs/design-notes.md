# Design Notes — War Stories / 设计复盘——踩坑实录

The decisions worth sharing aren't the code that worked; they're the failures that forced a redesign. Each entry: what broke, why, what changed.

值得分享的不是"能跑的代码"，而是那些逼着我重新设计的失败。每条：哪里坏了、为什么、改了什么。

---

## 1. The hotspot feature that had to be rebuilt mid-flight / 被迫推倒重来的热点功能

**Goal:** discover hot sectors across the *whole* market, not just my watchlist.
**First plan:** Futu's `get_stock_filter` (server-side market-wide screening). Clean, one call.
**What broke:** it returned the *entire* universe, filters ignored, value fields empty — on HK, US, and A-shares. Hours of probing showed the account had HK LV1 / US LV2 quote rights (so it *should* work), but the screener degraded silently. Couldn't prove entitlement vs. closed-market timing.
**The pivot:** stop betting on it. **yfinance predefined screeners** (`day_gainers` / `most_actives` / `day_losers`) discover movers for free, with zero brokerage entitlement — then feed those tickers to Futu `get_owner_plate` to *name* the sectors in Chinese and rank by frequency. Discovery and naming split across two providers; the fragile dependency is gone.

> 教训：当一个"理应可用"的接口沉默地降级，不要继续赌它。把"发现"和"命名"拆给两个数据源，反而更稳、还顺手降低了对单一供应商的依赖。

## 2. The silent bug that made the AI lie / 让 AI 撒谎的静默 bug

**Symptom:** for days, briefs reported confident US semiconductor prices that were **completely made up**.
**Root cause:** one OTC ticker (`US.ATEYY`) in the watchlist. Futu snapshots are *batch-atomic* — one unsupported code returns `ret=-1` for the **entire batch**, so all 21 US stocks vanished. The code only caught Python exceptions, not return codes, so the failure was swallowed. The AI saw no US data but was still asked to write "semis rallied" — so it invented numbers.
**The fix (two layers):** (1) on batch failure, **degrade to per-ticker** snapshots and record skips in `_failed_codes`; (2) a hard rule in the spec — **never fabricate; if the data isn't there, describe direction only.**

> 教训：批量原子接口要为"部分失败"设计降级；并且 agent 写作要有"无数据时只描述方向、绝不编数字"的硬约束。AI 不愿说"我没有数据"，所以系统必须替它兜底。

## 3. Timezone migration done wrong, then right / 时区迁移：先错后对

When I moved NYC→LA, timestamps drifted. The original code used `datetime.now()` and *assumed* the system was ET. The fix: compute every timestamp explicitly with `zoneinfo` (PT/ET/BJ all derived from UTC), never trusting the local system tz. The four cron schedules were re-derived for PT.

> 教训：任何跨市场/跨地区的时间，显式按时区算，别信 `datetime.now()` 的"本地"。

## 4. Searching "Qualcomm" returned "inflation" / 搜"高通"搜出"通胀"

The per-stock news search matched the company name as a substring. Searching **高通** (Qualcomm) kept pulling **推高通胀** ("pushing up inflation") — 高通 is a prefix of 高通胀. The news API exposes no related-ticker field to disambiguate, only titles. Fix: a small extensible **trap dictionary** (`_STOCK_NAME_TRAPS`) that drops titles containing known false-positive contexts.

> 教训：中文短名做关键词检索天然有歧义，且接口不给结构化关联字段时，只能在标题层面做针对性陷阱过滤。

## 5. Search could find paywalled journalism but could not read it / 搜索能找到付费新闻，却读不到正文

**V9 failure:** the brief tried to enrich with Bloomberg / Reuters / WSJ / FT / CNBC through WebSearch. Reuters/WSJ/FT could make the entire restricted-domain request fail; even when Exa found the right FT or WSJ title, it could not use the subscriber session and returned a paywall. Bloomberg also rejected automated retrieval.

**V10 pivot:** candidate discovery and article reading became separate stages. Agent Reach/Exa or publisher homepages may discover candidates, but the original Bloomberg / FT / WSJ text is read only through the user's logged-in local Chrome session. No subscription cookies are exported. If Chrome is closed, the extension is disconnected, a login has expired, or Bloomberg shows a robot check, the routine skips that source and keeps sending with Futu news.

The final content policy also changed: international, macro, AI, and stock/industry sections each retain Futu while adding relevant subscription journalism. Same-event stories are merged, and canonical external URLs enter a seven-day history cache so four daily routines do not repeat them.

> 教训：搜索、授权和正文读取是三件不同的事。付费内容要在用户本地登录态中读取，同时把浏览器路径设计成可降级增强，而不是新的单点故障。

## 6. Community gave only titles — so quote them / 社区只有标题——那就直接引用

The community API returns no body, no engagement counts, empty URLs — just the post title. Early briefs "summarized" this into useless filler like *"discussion is active."* The realization: the **title *is* the retail voice.** So: filter to recent (72h), focus on US names, and **quote the posts verbatim** with a bull/bear tag, instead of paraphrasing them into nothing.

> 教训：数据稀疏时，别用"正确的废话"概括——把原始信号（帖子原话）直接呈现，信息量反而更高。

---

### The meta-lesson / 元层面的教训

Almost every redesign came from **verifying assumptions against the live system** instead of trusting docs or the happy path: entitlements, reachability, batch semantics, field availability. The pipeline got more robust each time a "should work" turned out not to. The full sequence is in [`CHANGELOG.md`](../CHANGELOG.md).

几乎每次重构都源于**拿真实系统验证假设**，而不是相信文档或顺利路径——权限、可达性、批次语义、字段有无。每一次"理应可用"被证伪，pipeline 就更健壮一点。
