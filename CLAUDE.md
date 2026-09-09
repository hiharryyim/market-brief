# MarketDashboard — 市场信息看板

二级市场投资辅助工具集，集成在 Claude/Codex 桌面环境中运行，自动化生成并通过 Gmail SMTP 推送 Market Brief。

## 当前版本：V10.2（外媒五源 + 板块条数下限 + 研报主题限额）

## 数据源优先级：Futu → yfinance/LSEG；外媒先 RSS，必要时升级 Chrome 原站

| 数据 | 优先 | 备选 |
|------|------|------|
| 港股+美股行情（含自选股） | **Futu**（需 OpenD） | yfinance |
| **美股全市场热点（异动发现）** | **yfinance 筛选器**（day_gainers/losers/most_actives） | — |
| **热点板块归纳（个股→中文板块）** | **Futu `get_owner_plate`**（需 OpenD） | — |
| A股**行情**：**项目已决定不需要**，不再查权限（cn_qot_right=N/A）；A股**指数**仅作参考 | **yfinance**（Futu A股无权限） | LSEG |
| 黄金/白银/原油/汇率 | **yfinance** | LSEG |
| 美10Y收益率 | **yfinance** ^TNX | — |
| 金融新闻（基础召回+兜底） | **Futu News API**（无需 OpenD） | — |
| **机构研报 / 评级** | **Futu News `news_type=3`**（限美股+港股；自选股 → Mag7 → 相关行业 → 市场热点股兜底） | — |
| **外媒基础信息** | **Bloomberg / FT / WSJ / NYT / Washington Post 公开 RSS（仅近期有效 feed）** | Futu News |
| **订阅外媒深读** | **已登录 Chrome 原站（条件升级）** | RSS 摘要 / Futu News |
| **外媒候选发现** | 媒体首页 / Agent Reach Exa | Futu News |
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

**📑 深度研报**（`fetch_research()`，独立于上面 pipeline）：`news_type=3` 多题材召回机构评级/深度点评 → 按自选股、Mag7、AI/半导体/新能源车等相关行业、市场热点股兜底排序 → 历史去重 → 近 72h → **剔除 A股（标题含 6 位代码）只留美股+港股** → 相似度去重 → **按优先级轮转取 5 条，同一公司最多 2 条**（`RESEARCH_PER_SUBJECT_CAP`，标题命中同名公司也算，防止单只票刷满整栏）。

**💬 社区**（`fetch_community()`）：接口每条只有标题（=股民观点原话），无正文/互动数。关键词扩展为更多自选股 + 美股科技/半导体 fallback，只取**近 72h**；brief 里只直接引用原话，不做空话概括。

## V9 🔥 全市场热点发现（仅美股，仅两个美股 routine）

`scripts/fetch_data.py` 的 `fetch_hotspots()` 输出到 JSON `hotspots` 字段。**完全不依赖 Futu 选股权限**（`get_stock_filter` 收盘失效/疑似无权限，已弃用）：

1. **发现**：yfinance 预设筛选器 `day_gainers` / `day_losers` / `most_actives` 拉全美股异动个股（免费，不碰富途权限）
2. **归纳**：把异动个股喂给 Futu `get_owner_plate` 批量映射到中文概念/行业板块，按"≥2 只异动股归同一板块"过滤 + 频次排序 → 今日热点板块
3. **重叠去重**：概念板块与行业板块常覆盖同一波异动（如"太空概念"vs"航空航天与国防"），成员重叠 ≥60% 则合并，别名进 `aka`（最多 2 个）
4. **噪音板块过滤**：剔除"持仓榜/定投/碎股/热门榜/明星股"等非主题板块（`_PLATE_NOISE_KW`）

输出结构：`hotspots = { hot_sectors:[{name, aka, count, leaders}], top_gainers, top_losers, most_actives, _errors }`

**只进 brief-us-preopen / brief-us-close 两个美股 routine**（数据是美股的）；亚盘两个 routine 不放。港股暂缓（yfinance 港股混入窝轮/牛熊证太脏）。**写时严禁编造**；`hot_sectors` 为空时只省略「热点板块」小段，领涨/领跌/最活跃照常写（OpenD 不可用时 yfinance 异动榜仍然有数），三者全空才整节省略。

## V10.2 Brief 结构（7 板块 + 四板块外媒增强）

> 美股 routine 在「一、市场综述」与「重点新闻」之间多一个 **二、🔥 今日热点**（全市场异动，见上）；综述里商品/利率只点结论，详数留「宏观环境」。

### 板块结构（严格顺序，7 板块）
1. **🌍 国际局势 / 地缘**（至少 3 条新闻信息；至少 1 条外媒 + 至少 1 条 Futu）
2. **🏛️ 宏观 / 央行 / 大宗**（至少 3 条新闻信息；至少 1 条外媒 + 至少 1 条 Futu）
3. **🤖 AI / 大模型 / 芯片**（至少 3 条新闻信息；至少 1 条外媒 + 至少 1 条 Futu）
4. **📊 个股 / 行业聚焦**（1-2 条外媒 + 至少 1 条 Futu）
5. **📑 深度研报 / 机构观点**（Futu News `news_type=3`，限美股+港股，剔除A股；选股优先级：自选股 > Mag7 > 相关行业 > 热点股兜底）
6. **📱 A股 / 港股市场**（Futu News）
7. **💬 社区观察**（Futu Community API，近72h，引用帖子原话）

研报和社区按实际可用内容写；数量不足时不得写“本次仅返回/样本不足/未补写”等过程说明。研报栏不得一上来写市场热点股，只有自选股、Mag7 和相关行业研报不足时，才用热点股补位。

### V10.2 两层外媒（Bloomberg / FT / WSJ / NYT / Washington Post）
- **基础路径**：`fetch_data.py` 获取公开 RSS 标题与最多 300 字符摘要，写入 `external_rss`；无近期条目的 feed 返回空，不使用过期内容。
- **深读路径**：媒体视角、复杂因果、精确数字/引语、摘要不完整或核心个股事件才通过已登录 Chrome 读取原文，通常每封 1-3 篇。
- **降级路径**：Chrome 失败但 RSS 信息充分则使用基础摘要；否则舍弃并由其他外媒或 Futu 补齐，整封 brief 继续发送。
- **反自动化边界**：所有 schedule 均按无人值守运行。Bloomberg 出现 `Are you a robot?` 时只正常刷新原文一次；若仍为验证页，立即跳过并降级。不得自动操作 CAPTCHA、使用外部破解服务、导出凭证或规避付费墙，也不得阻塞整封 brief。
- **配额**：正常 7-10 条外媒信息，至少覆盖 2 家；有合适内容时尽量覆盖更多来源，但不强凑。
- **时效**：国际/宏观优先 48h；AI/个股趋势类最多 7 天。
- **多来源合并**：同一事件跨媒体、跨板块只保留一条，优先写成“一个标题 + 2-3 句综合摘要 + 多来源并列来源行”；不得拆成多条凑数量。外媒 URL 写入 `cache/sent_external_news_history.json` 做 7 天跨 routine 去重。
- **写法风格**：延续最新测试邮件风格，标题短，摘要先交代事实，再把外媒、Futu 与行情交叉验证；国际/宏观/AI 三个板块各至少 3 个不同新闻条目。
- **个股优先级**：自选股/显著异动 > 业绩与指引 > 并购/资本开支 > 行业结构变化。
- **宏观环境**：新增「媒体视角」，随后用行情 JSON 对媒体判断做交叉验证，再写「核心观察」。

### 正文输出边界

最终邮件只写读者需要看到的市场事实与判断。不得暴露字段名、工具状态或降级过程；正文禁止出现 `JSON`、`research`、`community`、`Chrome`、`验证页`、`不可读`、`未提供`、`样本不足` 等内部过程词。数据缺失时直接省略该指标，外媒原文失败时用 RSS/Futu 替代或舍弃，不向读者解释失败过程。

## 排版规范

- **移动端优先**：viewport meta、响应式字号、卡片式列表
- **涨红跌绿**（中国市场惯例）：.pos=#c62828(红) .neg=#2e7d32(绿)
- **市场综述**：分点列表，每主题用 `**子标题：**` + bullet points 卡片
- **新闻格式**：`**标题**` → 摘要 → 空行 → `[来源](url) | MM-DD`（**独占一行**）
- **新闻分隔**：来源行用 `<div class="news-source">` 包裹 + 虚线 `border-bottom`
- **来源标签兼容**：富途/Bloomberg/Reuters/WSJ/FT/NYT/Washington Post/CNBC/The Economist/SCMP

## 邮件发送

- **脚本**：`scripts/send_email.py`
- **配置**：`config/email.conf`（Gmail SMTP App Password）
- **收件人**：
  - 生产：`config/recipients.txt`（团队 13 人）
  - **测试**：`config/recipients_test.txt`（仅你自己 2 邮箱）
- **BCC 密送**：所有收件人通过 SMTP envelope 发送，header 中只显示发件人
- **`--test` 标志**：使用测试收件人列表
- **`--news-ids-file`**：发送成功后写入 Futu `news_id` 历史 cache
- **`--external-urls-file`**：发送成功后写入规范化外媒 URL 历史 cache

## 定时任务（4 个，本地执行，时区 ET）

用户 2026-05-27 从纽约搬到洛杉矶（PT），2026-09-08 搬回纽约（ET）；4 个 routine cron 已按 ET 重新设定。
机器时区为 `America/New_York`，**cron 按本地时间解释**，因此下表就是实际触发时间。

| Task ID | 时间 (ET) | cron | 对应市场 | 内容侧重 |
|---------|----------|------|----------|----------|
| brief-asia-preopen | 9PM 周日-周四 | `0 21 * * 0-4` | 北京次日 9AM | 美股收盘 → 亚盘前瞻 |
| brief-asia-midday | 11:30PM 周日-周四 | `30 23 * * 0-4` | 北京次日 11:30AM | A股/港股上午盘 → 下午盘关注 |
| brief-us-preopen | 9AM 周一-周五 | `0 9 * * 1-5` | ET 9AM | 亚盘收盘 → 美盘前瞻 |
| brief-us-close | 4:30PM 周一-周五 | `30 16 * * 1-5` | ET 4:30PM | 美股全天 → 次日亚盘展望 |

> **夏令时提醒**：以上按 EDT（北京 = ET+12）设定。11 月切回 EST 后北京 = ET+13，两个亚盘 routine 对应的北京时间会顺延 1 小时（9AM→10AM、11:30AM→12:30PM）。届时若要维持北京时点，把亚盘两个 cron 各提前 1 小时改为 `0 20` 和 `30 22`。

**当前状态：V10.2 已提交。仓库 `routines/` 与 `~/.claude/scheduled-tasks/brief-*/SKILL.md` 四份运行时 prompt 已同步；4 个本地 schedule 当前为暂停（`enabled=false`），恢复前先确认 Futu OpenD 在 `127.0.0.1:11111` 监听。生产任务无 `--test`，发送给团队 13 人。**

## 时间戳实现（V8.2 修复后）

fetch_data.py 用 `zoneinfo` 显式按时区计算，**不依赖系统本地时区**。
JSON 提供 4 个时间字段：
- `timestamp_et` — 纽约时间（用户当前所在）
- `timestamp_pt` — 洛杉矶时间（保留字段）
- `timestamp_bj` — 北京时间（市场所在）
- `date` — ET 日期（用户所在时区，与邮件标题的 `date +%Y-%m-%d` 一致）

Routine 模板里时点显示 `[JSON.timestamp_bj] / [JSON.timestamp_et]`。

## 关键文件

```
~/Desktop/MarketDashboard/
├── CLAUDE.md                      # 本文档
├── config/
│   ├── email.conf                 # Gmail SMTP 配置（chmod 600）
│   ├── recipients.txt             # 生产收件人（团队 13 人）
│   └── recipients_test.txt        # 测试收件人（仅自己 2 邮箱）
├── scripts/
│   ├── fetch_data.py              # 数据拉取 + 多阶段过滤 pipeline
│   └── send_email.py              # Markdown→HTML，BCC 密送，历史 cache 写入
└── cache/
    ├── sent_news_history.json     # 最近 7 天已发送 Futu news_id
    └── sent_external_news_history.json # 最近 7 天已发送外媒 URL
```

## Futu 权限
- 港股行情 ✅ | 美股行情 ✅（需 OpenD 登录）| A股行情 ❌
- 交易：HK/US/SG/JP 实盘均可
- News/Community API：无需 OpenD，纯 HTTP 调用
- OpenD: `/Applications/Futu_OpenD.app` → `127.0.0.1:11111`

## V10.2 运行与回滚

1. 生产发送必须同时传 `--news-ids-file` 与 `--external-urls-file`；测试发送不传，避免污染历史。
2. Chrome 不可用不是发送阻断条件；RSS 摘要充分则继续使用，否则退回 Futu 兜底。
3. 如果订阅外媒质量或稳定性异常，可把 routine 的步骤 3 回退为 RSS/Futu 兜底模式，行情与邮件链路不受影响。
4. 仓库通过 git 记录 V10.2；回滚使用 `git revert`，不要删除历史 cache 以制造重复新闻。

## 已知问题与未来 Phase 2

- 个股新闻搜索的关键词命中可能不精准（搜"高通"会捞到"高通胀"）
- 报告类旧新闻（华尔街喊话）可能仍偶尔混入，可考虑增加"是否突发"分类器
- Chrome 必须保持运行且扩展连接，才能在自动任务中使用订阅外媒深读；否则会按设计降级为 RSS/Futu 兜底
- Bloomberg 仍可能偶发人工验证；schedule 正常刷新一次后自动降级，不等待人工处理
- Embedding 聚类替代 SequenceMatcher — Phase 2
- 多语言英文版 brief — Phase 2
