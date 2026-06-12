---
name: brief-asia-preopen
description: 亚盘开盘前 Market Brief（PT 6PM 周日-周四 = 北京 9AM 次日）
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

## 步骤 3：受限 WebSearch 补充权威外媒（严格遵守约束）

**约束规则：**
1. **最多调用 WebSearch 2 次**
2. **只用 `allowed_domains: ["bloomberg.com","cnbc.com"]`**（实测 Reuters/WSJ/FT 被反爬，放进 allowed_domains 会让整条请求 400 失败）
3. 每次结果最多取前 5 条
4. 总共最多挑 **3 条** 加入 brief
5. 只挑选 **近 24 小时内** 的报道
6. 翻译成中文，标签 [Bloomberg]/[CNBC]
7. **外媒没有合适结果就不强凑**，对应板块用 Futu 新闻兜底即可

搜索 1（美股盘后/亚盘前瞻）：query=`China Asia market US stocks 2026`，allowed_domains=["bloomberg.com","cnbc.com"]
搜索 2（宏观/大宗补充）：query=`Fed rate gold oil 2026`，allowed_domains=["bloomberg.com","cnbc.com"]

外媒新闻插入到对应板块，格式：
```
**[英文标题翻译为中文]**
2-3句中文摘要。

[Bloomberg](具体URL) | MM-DD
```

## 步骤 4：撰写 Brief 写入 /tmp/market_brief.md

时段：亚盘开盘前 — 先讲美股收盘 + 盘后消息，再讲亚盘前瞻

### ⚠️ 模板（严格遵守，子标题必须保留）

```markdown
# Market Brief · [JSON.date] 亚盘开盘前

> 时点：[JSON.timestamp_bj] / [JSON.timestamp_pt]，美股收盘后/亚盘开盘前

## 一、市场综述

**美股收盘：**
- [SPY/QQQ/DIA 三大指数 + 显著板块]
- [涨跌超2%的关键个股]

**美股核心个股异动：**
- [自选股中显著异动：英伟达/苹果/特斯拉/微软/Meta 等]
- [半导体板块/AI 板块整体表现]

**盘后消息：**
- [财报/重要公告/管理层变动 等，如有]

**商品/汇率：**
- [黄金、白银、WTI原油]
- [美元指数、美10Y、人民币]

**亚盘前瞻：**
- [对A股/港股开盘的影响]
- [关键关注点和潜在催化剂]

---

## 二、重点新闻

#### 🌍 国际局势 / 地缘
[news.国际局势 + WebSearch 外媒]

#### 🏛️ 宏观 / 央行 / 大宗
[news.宏观大宗 + WebSearch 外媒]

#### 🤖 AI / 大模型 / 芯片
[news.AI动态]

#### 📊 个股聚焦
[news.个股_xxx 中选 3-5 条]

#### 📑 深度研报 / 机构观点
[research 中选 3-4 条机构评级/深度点评。**同一研报的 EN/CN 两条要合并只留一条**（如 Wolfe Research 与"沃尔夫研究"同一目标价）。格式同新闻条目，来源标 [富途]]

#### 📱 A股 / 港股市场
[news.市场动态 + 部分 news.科技消费]

#### 💬 社区观察
[**直接引用 community 里的帖子原话**（帖子标题就是股民观点，如"做空美光！人生發光！"），**覆盖约 3 只个股**（数据足够时），每条标偏多/偏空/中性。聚焦美股自选股。**禁止写"讨论密集/情绪乐观"之类空话**，要有具体观点和信息量]

---

## 三、宏观环境

**美债收益率：**
- [10Y/5Y/30Y]

**美元 / 外汇：**
- [DXY/人民币/日元]

**大宗商品：**
- [黄金/白银/原油]

**核心观察：**
- [一句话总结]

---

*以上内容仅供参考，不构成投资建议。*
```

### 新闻条目格式（严格）
```
**标题**
2-3 句摘要。

[富途](url) | MM-DD
```
- URL 从 JSON 原样复制
- `[来源](url) | MM-DD` **独占一行，上方留空行**
- 来源标签：`[富途]`/`[Bloomberg]`/`[Reuters]`/`[CNBC]`/`[WSJ]`/`[FT]`

涨跌：`+`涨 `-`跌

## 步骤 5：保存 news_ids
```bash
python3 -c "
import json
d = json.load(open('/tmp/market_data.json'))
json.dump(d.get('used_news_ids', []), open('/tmp/used_news_ids.json', 'w'))
"
```

## 步骤 6：发送邮件（生产模式：发给团队全员）
```bash
python3 ~/Desktop/MarketDashboard/scripts/send_email.py \
  --subject "哈利每日 Market Brief · 亚盘前瞻 · $(date +%Y-%m-%d)" \
  --markdown-file /tmp/market_brief.md \
  --news-ids-file /tmp/used_news_ids.json
```

确认输出 "OK: Email sent to" 和 "news_ids appended to history cache"。