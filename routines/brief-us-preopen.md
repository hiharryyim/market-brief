---
name: brief-us-preopen
description: 美盘开盘前 Market Brief（PT 6AM 周一-周五 = ET 9AM）
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

## 正文输出硬规则（读者可见）

最终 `/tmp/market_brief.md` 只能写面向读者的市场事实、交叉验证和投资观察，禁止暴露执行过程、字段名、工具状态或降级日志。

- 禁止在正文出现这些内部词或表达：`JSON`、`research`、`community`、`Chrome`、`验证页`、`CAPTCHA`、`不可读`、`未使用`、`未补写`、`样本不足`、`本次只写`、`返回 1 条`、`仅返回`、`未提供`。
- 数据缺失时直接省略该指标；若必需板块只有部分数据，只写可用数据，不解释“字段缺失/本次未返回”。
- 外媒原文失败时不向读者解释失败过程；RSS 信息足够就按 RSS 写基础事实，信息不足就舍弃。
- 「深度研报 / 机构观点」和「社区观察」按模板原规则写实际可用内容；数量不足时不要暴露返回数量、字段名或补写空泛判断。
- 不得把模板提示、括号中的写作说明、字段名或自检结果留在最终 brief。

## 步骤 3：V10.2 两层外媒补充（RSS 基础摘要 + Chrome 条件深读 + Futu 兜底）

### 获取路径
1. 优先读取 JSON.`external_rss`。这些候选来自 Bloomberg / FT / WSJ / NYT / Washington Post 公开 RSS，已过滤 7 天以前的旧条目，并按 `sent_external_news_history.json` 排除过去 7 天用过的 URL；某家 feed 为空时不得用旧内容凑数。`content_level=rss_summary` 表示只有标题和最多 300 字符公开摘要，**不是完整正文**。
2. RSS 摘要足以确认“谁、做了什么、何时发生”及摘要中明确给出的数字时，可以直接写 1-2 句基础事实；不得补写摘要未提供的原因、引语、数字或结论。
3. 只有满足以下任一条件时才通过已登录 Chrome 打开原文深读，正常每封升级 **1-3 篇**：
   - 文章将进入「媒体视角」或支撑「核心观察」；
   - 需要解释复杂因果、争议、政策机制、财报/指引细节；
   - 需要精确数字、原话，或 RSS 摘要过短、语义不完整；
   - 文章对应自选股/显著异动，是本封 brief 的核心事件。
4. Chrome 深读必须来自实际采用的外媒原站，不得读取、导出或转发 cookie/localStorage。若 Chrome 或原文失败：RSS 信息足够则降级为 RSS 基础摘要；信息不足则舍弃该条并由其他外媒或 Futu 补齐，整封 brief 不得中断。
5. 本 schedule 按无人值守运行。Bloomberg 出现 `Are you a robot?` 时，只正常刷新原文章页一次；若仍为验证页立即降级。不得自动操作 CAPTCHA、使用外部破解服务、导出凭证或规避付费墙。
6. Agent Reach/Exa 仅可补充候选发现，不作为订阅正文来源。完成后关闭本次创建的临时标签页。

### 板块配额（四个板块都必须保留 Futu）
- **国际局势 / 地缘**：至少 3 条新闻信息；至少 1 条外媒 + 至少 1 条 Futu。
- **宏观 / 央行 / 大宗**：至少 3 条新闻信息；至少 1 条外媒 + 至少 1 条 Futu。
- **AI / 大模型 / 芯片**：至少 3 条新闻信息；至少 1 条外媒 + 至少 1 条 Futu。
- **个股 / 行业聚焦**：1-2 条外媒 + 至少 1 条 Futu。优先级：自选股/显著异动 > 业绩与指引 > 并购/资本开支 > 行业结构变化。
- 正常使用 7-10 条外媒信息，至少覆盖 2 家；其中 Chrome 全文深读通常 1-3 条，其余可使用信息充分的 RSS 基础摘要，不为凑数量牺牲相关性。

### 质量与去重
- 国际/宏观优先近 48 小时；AI/个股趋势类最多 7 天。
- RSS 条目只能写 `title + excerpt` 明确支持的事实；Chrome 条目只能写实际读到的原文事实。翻译成中文并给出具体文章 URL。
- 同一事件跨媒体、Futu 和板块只保留一条，优先写成“一个标题 + 综合摘要 + 多来源并列来源行”；不得拆成多条凑数量，也不得在 AI 与个股板块重复。
- 个股外媒必须和 JSON 行情/热点异动互相验证，不得脱离当日市场强行加入。
- 写法固定采用本轮测试邮件风格：标题短、摘要 2-3 句，第一句交代事实，后续句把外媒事实、Futu 事实和行情交叉验证；避免堆砌列表、避免泛泛宏观空话。
- 国际/宏观/AI 三个板块各至少 3 个不同新闻条目；若同一事件有 NYT/Washington Post/WSJ/FT/Bloomberg/富途等多来源，合并到同一条新闻中，这是优先写法而不是重复。

外媒新闻格式：
```
**[英文标题翻译为中文]**
2-3句中文摘要。

[Bloomberg](具体URL) | MM-DD
```
多来源合并格式：
```
[Washington Post](具体URL) | MM-DD · [NYT](具体URL) | MM-DD · [富途](具体URL) | MM-DD
```

## 步骤 4：撰写 Brief 写入 /tmp/market_brief.md

时段：美盘开盘前 — 先讲亚盘收盘，再讲美盘前瞻

### ⚠️ 模板（严格遵守）

```markdown
# Market Brief · [JSON.date] 美盘开盘前

> 时点：[JSON.timestamp_bj] / [JSON.timestamp_pt]，亚盘收盘/美盘开盘前

## 一、市场综述

**A股全天收盘：**
- [上证综指、沪深300、创业板指 全天表现]
- [板块异动、涨跌超2%的标的]

**港股全天收盘：**
- [恒指、恒生科技 全天表现]
- [自选股显著异动]

**互联网/新势力：**
- [腾讯/阿里/美团 + 小鹏/理想/蔚来 表现]

**商品 / 利率：**
- [只点方向、一句结论即可，详细数字留到「四、宏观环境」。注意：括号里这类说明文字不要出现在最终 brief 中]

**美股盘前数据：**
- [SPY/QQQ/DIA 期货走势 + 关注个股]

**美盘前瞻：**
- [今日开盘关注点：财报、经济数据、事件]

---

## 二、🔥 隔夜美股热点（全市场异动 · 非自选股）

> 数据来自 `JSON.hotspots`（yfinance 全市场异动榜 + Futu 板块归纳），反映**上一交易日美股**异动。**全部照抄真实数据，严禁编造**；若 `hotspots.hot_sectors` 为空则整节省略。

**隔夜热点板块（按异动个股数排序，取前 3-4 个）：**
- **[hot_sectors[].name；有 aka 时写成「主名/别名」]**（[count] 只）：[leaders 取前 3，格式 公司名/ticker +X.X%]
- …

**全市场领涨 / 领跌 / 活跃：**
- 领涨：[top_gainers 前 3：名称 +X.X%]
- 领跌：[top_losers 前 3：名称 -X.X%]
- 最活跃：[most_actives 前 3：名称 ±X.X%]

**资金流向解读：**
- [1-2 句：隔夜资金在追什么主题，对今日美盘开盘的潜在影响。若与自选股所属行业有共振，**从行业层面**表述，**禁止用"你的自选股"这类第二人称**——邮件多人接收，要宏观口吻。客观陈述，不下买卖结论]

---

## 三、重点新闻

#### 🌍 国际局势 / 地缘
[至少 3 条新闻信息；至少 1 条外媒 + news.国际局势 中至少 1 条 Futu；同一事件多来源必须合并为一条]

#### 🏛️ 宏观 / 央行 / 大宗
[至少 3 条新闻信息；至少 1 条外媒 + news.宏观大宗 中至少 1 条 Futu；优先写利率、美元、商品、央行和能源]

#### 🤖 AI / 大模型 / 芯片
[至少 3 条新闻信息；至少 1 条外媒 + news.AI动态 中至少 1 条 Futu；优先写 AI 商业化、算力、半导体设备/材料]

#### 📊 个股 / 行业聚焦
[1-2 条外媒 + news.个股_xxx；至少 1 条 Futu；同事件允许合并双来源]

#### 📑 深度研报 / 机构观点
[research 中按优先级选 3-4 条机构评级/深度点评：自选股优先，其次 Mag7，再其次 AI/半导体/新能源车等相关行业，最后才用市场热点股补位；不要把本节写成热点股信息大杂烩。不足 3-4 条时只写实际可用条目，空则用读者可见话术说明近期暂无可用机构评级更新。**同一研报的 EN/CN 两条要合并只留一条**（如 Wolfe Research 与"沃尔夫研究"同一目标价）。格式同新闻条目，来源标 [富途]]

#### 📱 A股 / 港股市场
[news.市场动态 + 部分 news.科技消费]

#### 💬 社区观察
[直接引用社区帖子原话（帖子标题就是股民观点，如"做空美光！人生發光！"），覆盖约 3 只个股（数据足够时）；不足时只写实际可用原话，空则省略本节或用读者可见话术说明近 72h 暂无高信息量社区原话。每条标偏多/偏空/中性。禁止写"讨论密集/情绪乐观"之类空话]

---

## 四、宏观环境

**美债收益率：**
- [10Y/5Y/30Y；缺失项直接省略]

**美元 / 外汇：**
- [DXY/人民币/日元；缺失项直接省略]

**大宗商品：**
- [黄金/白银/原油]

**媒体视角：**
- [提炼 1-2 条外媒对宏观环境的观点，并明确这是媒体判断]

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
- 来源标签：`[富途]`/`[Bloomberg]`/`[WSJ]`/`[FT]`/`[NYT]`/`[Washington Post]`
- 同一事件合并来源时可写：`[WSJ](url) | MM-DD · [富途](url) | MM-DD`

涨跌：所有行情涨跌幅统一写成 `+1.23%` / `-1.23%`，必须保留正负号；脚本自动着色为涨红跌绿。

## 步骤 5：正文自检

```bash
python3 - <<'PY'
import re
from pathlib import Path
text = Path('/tmp/market_brief.md').read_text(encoding='utf-8')
forbidden = [
    'JSON', 'research', 'community', 'Chrome', '验证页', 'CAPTCHA',
    '不可读', '未使用', '未补写', '样本不足', '本次只写',
    '返回 1 条', '仅返回', '未提供',
]
hits = [word for word in forbidden if word in text]
if hits:
    raise SystemExit('正文仍包含内部过程词，需要先重写: ' + ', '.join(hits))
required_sections = [
    '🌍 国际局势 / 地缘',
    '🏛️ 宏观 / 央行 / 大宗',
    '🤖 AI / 大模型 / 芯片',
]
for section in required_sections:
    m = re.search(r'^####\s+' + re.escape(section) + r'\s*\n(.*?)(?=^####\s+|\Z)', text, re.S | re.M)
    if not m:
        raise SystemExit(f'缺少重点新闻板块: {section}')
    count = len(re.findall(r'^\*\*[^*\n].*\*\*\s*$', m.group(1), re.M))
    if count < 3:
        raise SystemExit(f'{section} 至少需要 3 条新闻信息，当前 {count} 条')
PY
```

若自检失败，立即重写命中句并重新运行自检；未通过不得发送邮件。

## 步骤 6：保存去重记录
```bash
python3 -c "
import json
d = json.load(open('/tmp/market_data.json'))
json.dump(d.get('used_news_ids', []), open('/tmp/used_news_ids.json', 'w'))
"
```

将本次 brief **实际使用的外媒 URL**（无论只用 RSS 摘要还是已用 Chrome 深读）以 JSON 数组写入 `/tmp/used_external_urls.json`；没有则写 `[]`。不要写 Futu URL。

## 步骤 7：发送邮件（生产模式：发给团队全员）
```bash
python3 ~/Desktop/MarketDashboard/scripts/send_email.py \
  --subject "哈利每日 Market Brief · 美盘前瞻 · $(date +%Y-%m-%d)" \
  --markdown-file /tmp/market_brief.md \
  --news-ids-file /tmp/used_news_ids.json \
  --external-urls-file /tmp/used_external_urls.json
```

确认输出 "OK: Email sent to"、"news_ids appended to history cache" 和 "external URLs appended to history cache"。
