# MarketDashboard — 市场信息看板

二级市场投资辅助工具集，集成在 Claude Code 中运行，自动化生成并通过 Gmail SMTP 推送 Market Brief。

## 当前版本：V8（多阶段过滤 Pipeline + 受限 WebSearch + 6 板块新闻结构）

## 数据源优先级：Futu → LSEG → yfinance/WebSearch

| 数据 | 优先 | 备选 |
|------|------|------|
| 港股+美股行情（含自选股） | **Futu**（需 OpenD） | yfinance |
| A股指数 | **yfinance**（Futu A股无权限） | LSEG |
| 黄金/白银/原油/汇率 | **yfinance** | LSEG |
| 美10Y收益率 | **yfinance** ^TNX | — |
| 金融新闻（国内+部分外媒） | **Futu News API**（无需 OpenD） | WebSearch |
| **权威外媒新闻** | **WebSearch**（受限：≤2次，≤3条） | — |
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
6. **来源加权**：标题含权威机构（美联储/央行/高盛/Bloomberg/Reuters 等）权重 ×1.5
7. **时间×权重排序**：每板块取 N 条
8. **输出 used_news_ids**：`send_email.py --news-ids-file` 写入历史 cache

## V8 Brief 结构（6 板块 + 子标题分块市场综述）

### 板块结构（严格顺序）
1. **🌍 国际局势 / 地缘**（Futu News + WebSearch 外媒）
2. **🏛️ 宏观 / 央行 / 大宗**（Futu News + WebSearch 外媒）
3. **🤖 AI / 大模型 / 芯片**（Futu News）
4. **📊 个股聚焦**（Futu News，自选股动态生成）
5. **📱 A股 / 港股市场**（Futu News）
6. **💬 社区观察**（Futu Community API）

### 受限 WebSearch（外媒补充）
- 最多调用 2 次
- 限定 site:bloomberg.com / reuters.com / wsj.com / ft.com / cnbc.com
- 总共最多挑 3 条加入 brief
- 仅近 24 小时内
- 标签：[Bloomberg]/[Reuters]/[WSJ]/[FT]/[CNBC]

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

## 定时任务（4 个，本地执行）

| Task ID | 时间 (ET) | 内容侧重 |
|---------|----------|----------|
| brief-asia-preopen | 9PM 周日-周四 | 美股收盘 → 亚盘前瞻 |
| brief-asia-midday | 11:30PM 周日-周四 | A股/港股上午盘 → 下午盘关注 |
| brief-us-preopen | 9AM 周一-周五 | 亚盘收盘 → 美盘前瞻 |
| brief-us-close | 4:30PM 周一-周五 | 美股全天 → 次日亚盘展望 |

**当前状态：4 个 routine 已升级到 V8，处于灰度测试期（--test 标志），仅发给自己。稳定 1-2 天后手动移除 --test 切到生产模式。**

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
