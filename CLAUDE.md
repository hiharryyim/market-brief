# MarketDashboard — 市场信息看板

二级市场投资辅助工具集，集成在 Claude Code 中运行，自动化生成并通过 Gmail SMTP 推送 Market Brief。

## 当前版本：V9（V8 多阶段新闻 pipeline + 🔥 全市场热点发现 + 6 板块新闻结构）

## 数据源优先级：Futu → LSEG → yfinance/WebSearch

| 数据 | 优先 | 备选 |
|------|------|------|
| 港股+美股行情（含自选股） | **Futu**（需 OpenD） | yfinance |
| **美股全市场热点（异动发现）** | **yfinance 筛选器**（day_gainers/losers/most_actives） | — |
| **热点板块归纳（个股→中文板块）** | **Futu `get_owner_plate`**（需 OpenD） | — |
| A股**行情**：**项目已决定不需要**，不再查权限（cn_qot_right=N/A）；A股**指数**仅作参考 | **yfinance**（Futu A股无权限） | LSEG |
| 黄金/白银/原油/汇率 | **yfinance** | LSEG |
| 美10Y收益率 | **yfinance** ^TNX | — |
| 金融新闻（国内+部分外媒） | **Futu News API**（无需 OpenD） | WebSearch |
| **机构研报 / 评级** | **Futu News `news_type=3`**（限美股+港股） | — |
| **权威外媒新闻** | **WebSearch**（受限：≤2次≤3条，仅 BBG+CNBC） | — |
| 社区情绪 | **Futu 社区 API**（无需 OpenD） | — |

## V8 新闻 Pipeline（多阶段过滤）

`scripts/fetch_data.py` 自动完成：

1. **多查询召回**：每板块用多个细分关键词调用 Futu News API（提升召回率）
2. **历史去重**：与 `cache/sent_news_history.json` 比对，去掉过去 7 天发过的 news_id
3. **跨板块去重**：同一 news_id 不在两个板块出现
4. **时效性过滤**：
   - 突发类（国际局势/宏观大宗/市场动态）：48 小时内
   - 趋势类（AI/科技/个股）：7 天内
5. **板块内主题相似度去重**：标题相似度 ≥ 0.7 视为同主题
6. **个股关键词陷阱过滤**：短名是常见词前缀时剔除误命中（如搜"高通"剔除"推高通胀"，`_STOCK_NAME_TRAPS`）
7. **来源加权**：标题含权威机构（美联储/央行/高盛/Bloomberg/Reuters 等）权重 ×1.5
8. **时间×权重排序**：每板块取 N 条
9. **输出 used_news_ids**：`send_email.py --news-ids-file` 写入历史 cache（新闻+研报都参与跨天去重）

**📑 深度研报**（`fetch_research()`，独立于上面 pipeline）：`news_type=3` 多题材召回机构评级/深度点评 → 历史去重 → 近 72h → **剔除 A股（标题含 6 位代码）只留美股+港股** → 相似度去重 → 取 5 条，输出 JSON `research`。

**💬 社区**（`fetch_community()`）：接口每条只有标题（=股民观点原话），无正文/互动数。只取**近 72h**、聚焦美股自选股；brief 里**直接引用原话**，不做空话概括。

## V9 🔥 全市场热点发现（仅美股，仅两个美股 routine）

`scripts/fetch_data.py` 的 `fetch_hotspots()` 输出到 JSON `hotspots` 字段。**完全不依赖 Futu 选股权限**（`get_stock_filter` 收盘失效/疑似无权限，已弃用）：

1. **发现**：yfinance 预设筛选器 `day_gainers` / `day_losers` / `most_actives` 拉全美股异动个股（免费，不碰富途权限）
2. **归纳**：把异动个股喂给 Futu `get_owner_plate` 批量映射到中文概念/行业板块，按"≥2 只异动股归同一板块"过滤 + 频次排序 → 今日热点板块
3. **重叠去重**：概念板块与行业板块常覆盖同一波异动（如"太空概念"vs"航空航天与国防"），成员重叠 ≥60% 则合并，别名进 `aka`（最多 2 个）
4. **噪音板块过滤**：剔除"持仓榜/定投/碎股/热门榜/明星股"等非主题板块（`_PLATE_NOISE_KW`）

输出结构：`hotspots = { hot_sectors:[{name, aka, count, leaders}], top_gainers, top_losers, most_actives, _errors }`

**只进 brief-us-preopen / brief-us-close 两个美股 routine**（数据是美股的）；亚盘两个 routine 不放。港股暂缓（yfinance 港股混入窝轮/牛熊证太脏）。**写时严禁编造**，`hot_sectors` 为空则整节省略。

## V8 Brief 结构（6 板块 + 子标题分块市场综述）

> 美股 routine 在「一、市场综述」与「重点新闻」之间多一个 **二、🔥 今日热点**（全市场异动，见上）；综述里商品/利率只点结论，详数留「宏观环境」。

### 板块结构（严格顺序，7 板块）
1. **🌍 国际局势 / 地缘**（Futu News + WebSearch 外媒）
2. **🏛️ 宏观 / 央行 / 大宗**（Futu News + WebSearch 外媒）
3. **🤖 AI / 大模型 / 芯片**（Futu News）
4. **📊 个股聚焦**（Futu News，自选股动态生成）
5. **📑 深度研报 / 机构观点**（Futu News `news_type=3`，限美股+港股，剔除A股）
6. **📱 A股 / 港股市场**（Futu News）
7. **💬 社区观察**（Futu Community API，近72h，引用帖子原话）

### 受限 WebSearch（外媒补充）
- 最多调用 2 次
- **`allowed_domains` 只用 bloomberg.com + cnbc.com**（Reuters/WSJ/FT 被反爬，放进去整条请求 400）
- 总共最多挑 3 条加入 brief
- 仅近 24 小时内
- 标签：[Bloomberg]/[CNBC]
- 外媒没合适结果就不强凑，用 Futu 新闻兜底

## 排版规范

- **移动端优先**：viewport meta、响应式字号、卡片式列表
- **涨红跌绿**（中国市场惯例）：.pos=#c62828(红) .neg=#2e7d32(绿)
- **市场综述**：分点列表，每主题用 `**子标题：**` + bullet points 卡片
- **新闻格式**：`**标题**` → 摘要 → 空行 → `[来源](url) | MM-DD`（**独占一行**）
- **新闻分隔**：来源行用 `<div class="news-source">` 包裹 + 虚线 `border-bottom`
- **来源标签兼容**：富途/Bloomberg/Reuters/WSJ/FT/CNBC/The Economist/SCMP

## 邮件发送

- **脚本**：`scripts/send_email.py`
- **配置**：`config/email.conf`（Gmail SMTP App Password）
- **收件人**：
  - 生产：`config/recipients.txt`（团队 8 人）
  - **测试**：`config/recipients_test.txt`（仅你自己 2 邮箱）
- **BCC 密送**：所有收件人通过 SMTP envelope 发送，header 中只显示发件人
- **`--test` 标志**：使用测试收件人列表
- **`--news-ids-file`**：发送成功后写入历史 cache 用于去重

## 定时任务（4 个，本地执行，时区 PT）

用户 2026-05-27 从纽约 ET 搬到洛杉矶 PT，4 个 routine cron 已同步调整。

| Task ID | 时间 (PT) | 对应市场 | 内容侧重 |
|---------|----------|----------|----------|
| brief-asia-preopen | 6PM 周日-周四 | 北京次日 9AM | 美股收盘 → 亚盘前瞻 |
| brief-asia-midday | 8:30PM 周日-周四 | 北京次日 11:30AM | A股/港股上午盘 → 下午盘关注 |
| brief-us-preopen | 6AM 周一-周五 | ET 9AM | 亚盘收盘 → 美盘前瞻 |
| brief-us-close | 1:30PM 周一-周五 | ET 4:30PM | 美股全天 → 次日亚盘展望 |

**当前状态：V8.3 已生产，所有 4 routine 已转生产模式（无 --test，发送给团队 9 人）。会话切换时已暂停（enabled=false），新会话恢复方式：`update_scheduled_task` 把 enabled 设为 true**

## 时间戳实现（V8.2 修复后）

fetch_data.py 用 `zoneinfo` 显式按时区计算，**不依赖系统本地时区**。
JSON 提供 4 个时间字段：
- `timestamp_pt` — 洛杉矶时间（用户当前所在）
- `timestamp_et` — 纽约时间
- `timestamp_bj` — 北京时间（市场所在）
- `date` — PT 日期

Routine 模板里时点显示 `[JSON.timestamp_bj] / [JSON.timestamp_pt]`。

## 关键文件

```
~/Desktop/MarketDashboard/
├── CLAUDE.md                      # 本文档
├── config/
│   ├── email.conf                 # Gmail SMTP 配置（chmod 600）
│   ├── recipients.txt             # 生产收件人（团队 8 人）
│   └── recipients_test.txt        # 测试收件人（仅自己 2 邮箱）
├── scripts/
│   ├── fetch_data.py              # 数据拉取 + 多阶段过滤 pipeline
│   └── send_email.py              # Markdown→HTML，BCC 密送，历史 cache 写入
└── cache/
    └── sent_news_history.json     # 最近 7 天已发送 news_id（去重用）
```

## Futu 权限
- 港股行情 ✅ | 美股行情 ✅（需 OpenD 登录）| A股行情 ❌
- 交易：HK/US/SG/JP 实盘均可
- News/Community API：无需 OpenD，纯 HTTP 调用
- OpenD: `/Applications/Futu_OpenD.app` → `127.0.0.1:11111`

## 灰度发布流程

1. **当前**：4 个 routine 都带 `--test`，仅发给自己
2. **观察 1-2 天**：稳定性、内容质量、去重效果
3. **稳定后**：手动编辑 4 个 routine 的 prompt，移除 `--test` 标志
4. **回滚预案**：如果 V8 不稳定，可参考 git/历史 prompt 回退

## 已知问题与未来 Phase 2

- 个股新闻搜索的关键词命中可能不精准（搜"高通"会捞到"高通胀"）
- 报告类旧新闻（华尔街喊话）可能仍偶尔混入，可考虑增加"是否突发"分类器
- WSJ Chrome MCP 集成（利用已登录 session）— Phase 2
- Embedding 聚类替代 SequenceMatcher — Phase 2
- 多语言英文版 brief — Phase 2
