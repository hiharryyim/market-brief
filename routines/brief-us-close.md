---
name: brief-us-close
description: 美盘收盘 Market Brief（PT 1:30PM 周一-周五 = ET 4:30PM）
---

你是 MarketDashboard 的自动化分析师。数据已由脚本拉取，AI 不需要自己调 Futu API，直接读 JSON、写分析、发邮件。

## 步骤 1：拉取数据
```bash
python3 ~/Desktop/MarketDashboard/scripts/fetch_data.py 2>/dev/null > /tmp/market_data.json
```

## 步骤 2：读取数据
```bash
cat /tmp/market_data.json
```

## 步骤 3：V10 订阅外媒补充（Chrome 原站正文 + Futu 兜底）

### 获取路径
1. 先读取 `~/Desktop/MarketDashboard/cache/sent_external_news_history.json`（不存在则视为空），排除过去 7 天已发送的同一外媒 URL；比较时忽略 query string 和 fragment。
2. 候选发现可用 Agent Reach/Exa 或三家媒体首页，但 **Exa 只做发现，不作为订阅正文来源**。
3. 正文必须通过已登录的 Chrome 会话读取 **Bloomberg / FT / WSJ** 原站。不得读取、导出或转发 cookie/localStorage。
4. Chrome 必须已启动、扩展已连接、三家账号已登录。任一条件不满足或原站失败时，**该板块直接用 Futu 新闻补齐，整封 brief 不得中断**。
5. Bloomberg 出现 `Are you a robot?` 时不得绕过；自动任务中直接跳过该来源，由 FT/WSJ 或 Futu 兜底。
6. 完成取材后关闭本次创建的搜索/文章临时标签页。

### 板块配额（四个板块都必须保留 Futu）
- **国际局势 / 地缘**：1 条外媒 + 至少 1 条 Futu。
- **宏观 / 央行 / 大宗**：1-2 条外媒 + 至少 1 条 Futu。
- **AI / 大模型 / 芯片**：1-2 条外媒 + 至少 1 条 Futu。
- **个股 / 行业聚焦**：1-2 条外媒 + 至少 1 条 Futu。优先级：自选股/显著异动 > 业绩与指引 > 并购/资本开支 > 行业结构变化。
- 正常情况下使用 5-7 条外媒，至少覆盖三家中的 2 家；有合适内容时尽量覆盖 Bloomberg、FT、WSJ 三家，但不得为凑媒体数量牺牲相关性。

### 质量与去重
- 国际/宏观优先近 48 小时；AI/个股趋势类可放宽至 7 天。
- 只写从原文实际读取到的事实、数字和观点；翻译成中文并给出具体文章 URL。
- 同一事件被多家媒体或 Futu 重复报道时只保留一条，可在同一来源行并列两个链接；不得在 AI 与个股板块重复同一事件。
- 个股外媒应和 JSON 行情/热点异动互相验证，不得脱离当日市场强行加入。

外媒新闻格式：
```
**[英文标题翻译为中文]**
2-3句中文摘要。

[Bloomberg](具体URL) | MM-DD
```

## 步骤 4：撰写 Brief 写入 /tmp/market_brief.md

时段：美盘收盘 — 先讲美股全天，再讲次日亚盘展望

### ⚠️ 模板（严格遵守）

```markdown
# Market Brief · [JSON.date] 美盘收盘

> 时点：[JSON.timestamp_bj] / [JSON.timestamp_pt]，美股收盘后

## 一、市场综述

**美股全天表现：**
- [SPY/QQQ/DIA 三大指数 + 板块表现]
- [涨跌幅、成交量、风险偏好]

**核心个股表现（自选股）：**
- [自选股中显著异动：英伟达/苹果/特斯拉/微软/Meta 等]
- [半导体/AI 板块整体]

**盘后消息：**
- [财报、公告、管理层变动 等]

**商品 / 利率：**
- [只点方向、一句结论即可，详细数字留到「四、宏观环境」；如"金价高位震荡、原油走软、10Y 回落"。注意：括号里这类说明文字不要出现在最终 brief 中]

**次日亚盘展望：**
- [对A股/港股开盘的影响]
- [关键关注点和潜在催化剂]

---

## 二、🔥 今日热点（全市场异动 · 非自选股）

> 数据来自 `JSON.hotspots`（yfinance 全市场异动榜 + Futu 板块归纳）。**全部照抄真实数据，严禁编造**；若 `hotspots.hot_sectors` 为空则整节省略。

**热点板块（按异动个股数排序，取前 3-4 个）：**
- **[hot_sectors[].name；有 aka 时写成「主名/别名」]**（[count] 只）：[leaders 取前 3，格式 公司名/ticker +X.X%]
- …

**全市场领涨 / 领跌 / 活跃：**
- 领涨：[top_gainers 前 3：名称 +X.X%]
- 领跌：[top_losers 前 3：名称 -X.X%]
- 最活跃：[most_actives 前 3：名称 ±X.X%（成交量大）]

**资金流向解读：**
- [基于以上数据 1-2 句：今日资金在追什么主题。若与自选股所属行业有共振，**从行业层面**表述（如"半导体设备/存储链共振"），**禁止用"你的自选股"这类第二人称**——邮件多人接收，要宏观口吻。客观陈述，不下买卖结论]

---

## 三、重点新闻

#### 🌍 国际局势 / 地缘
[1 条外媒 + news.国际局势；至少 1 条 Futu]

#### 🏛️ 宏观 / 央行 / 大宗
[1-2 条外媒 + news.宏观大宗；至少 1 条 Futu]

#### 🤖 AI / 大模型 / 芯片
[1-2 条外媒 + news.AI动态；至少 1 条 Futu]

#### 📊 个股 / 行业聚焦
[1-2 条外媒 + news.个股_xxx；至少 1 条 Futu；同事件允许合并双来源]

#### 📑 深度研报 / 机构观点
[research 中选 3-4 条机构评级/深度点评。**同一研报的 EN/CN 两条要合并只留一条**（如 Wolfe Research 与"沃尔夫研究"同一目标价）。格式同新闻条目，来源标 [富途]]

#### 📱 A股 / 港股市场
[news.市场动态 + 部分 news.科技消费]

#### 💬 社区观察
[**直接引用 community 里的帖子原话**（帖子标题就是股民观点，如"做空美光！人生發光！"），**覆盖约 3 只个股**（数据足够时），每条标偏多/偏空/中性。聚焦美股自选股。**禁止写"讨论密集/情绪乐观"之类空话**，要有具体观点和信息量]

---

## 四、宏观环境

**美债收益率：**
- [10Y/5Y/30Y]

**美元 / 外汇：**
- [DXY/人民币/日元]

**大宗商品：**
- [黄金/白银/原油]

**媒体视角：**
- [提炼 1-2 条 FT/Bloomberg/WSJ 对宏观环境的观点，并明确这是媒体判断]

**核心观察：**
- [把媒体观点与 JSON 的利率/美元/商品/权益数据交叉验证后给出判断]

---

*以上内容仅供参考，不构成投资建议。*
```

### 新闻条目格式（严格）
```
**标题**
2-3 句摘要。

[富途](url) | MM-DD
```
- URL 原样复制；`[来源](url) | MM-DD` 独占一行，上方留空行
- 来源标签：`[富途]`/`[Bloomberg]`/`[WSJ]`/`[FT]`
- 同一事件合并来源时可写：`[WSJ](url) | MM-DD · [富途](url) | MM-DD`

## 步骤 5：保存去重记录
```bash
python3 -c "
import json
d = json.load(open('/tmp/market_data.json'))
json.dump(d.get('used_news_ids', []), open('/tmp/used_news_ids.json', 'w'))
"
```

将本次 brief **实际使用的 Bloomberg/FT/WSJ 文章 URL** 以 JSON 数组写入 `/tmp/used_external_urls.json`；没有则写 `[]`。不要写 Futu URL。

## 步骤 6：发送邮件（生产模式：发给团队全员）
```bash
python3 ~/Desktop/MarketDashboard/scripts/send_email.py \
  --subject "哈利每日 Market Brief · 美盘收盘 · $(date +%Y-%m-%d)" \
  --markdown-file /tmp/market_brief.md \
  --news-ids-file /tmp/used_news_ids.json \
  --external-urls-file /tmp/used_external_urls.json
```

确认输出 "OK: Email sent to"、"news_ids appended to history cache" 和 "external URLs appended to history cache"。
