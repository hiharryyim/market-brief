# MarketDashboard - V10.1 Agent Instructions

二级市场投资辅助工具，运行于 Codex/Claude 桌面环境，每天 4 次生成并通过 Gmail SMTP 推送「哈利每日 Market Brief」。

## 当前版本

**V10.1：公开 RSS 基础摘要 + 订阅外媒 Chrome 条件深读 + Futu 兜底。**

行情、Futu 新闻和 Bloomberg/FT/WSJ 公开 RSS 候选由 `scripts/fetch_data.py` 生成结构化 JSON；agent 只对高价值文章通过已登录 Chrome 深读原站正文。

## 数据源

| 数据 | 主来源 | 降级 |
|---|---|---|
| 港股/美股行情与自选股 | Futu OpenD | yfinance |
| 美股全市场热点 | yfinance screeners + Futu `get_owner_plate` | 为空则省略 |
| A股指数、商品、汇率、利率 | yfinance | LSEG/省略 |
| 基础新闻与兜底 | Futu News API | 省略低质量条目 |
| 机构研报 | Futu `news_type=3`，覆盖自选股、Mag7、AI/半导体与美股热点 | 为空则用读者可见话术说明 |
| 外媒基础信息 | Bloomberg / FT / WSJ 公开 RSS（仅近期有效 feed 动态参与） | Futu News |
| 订阅外媒深读 | 已登录 Chrome 原站正文（条件升级） | RSS 摘要 / Futu News |
| 外媒候选发现 | JSON `external_rss` / 媒体首页 / Agent Reach Exa | 直接浏览媒体栏目 |
| 社区观点 | Futu Community API，覆盖更大自选股池 + 美股科技/半导体 fallback | 为空则省略或读者化说明 |

## Futu Pipeline

`scripts/fetch_data.py` 已实现：多查询召回、7 天历史去重、跨板块去重、48h/7d 时效窗口、标题相似度去重、个股短名陷阱过滤、来源加权、时间排序、研报过滤、研报关键词扩展、社区近 72h 过滤、社区关键词扩展和美股热点发现。

硬性规则：
- JSON 中没有的数据不得编造；缺失时只描述方向或省略。
- 最终 brief 不得暴露字段名、工具状态或降级过程；正文禁止出现 `JSON`、`research`、`community`、`Chrome`、`验证页`、`不可读`、`未提供`、`样本不足` 等内部过程词。
- 测试邮件不传历史文件参数；生产邮件必须传。
- 美股热点只进入 `brief-us-preopen` 和 `brief-us-close`；`hot_sectors` 为空则整节省略。
- 研报和社区按模板写实际可用内容；数量不足时不得暴露返回数量、字段名或补写空泛判断。

## V10.1 订阅外媒协议

### 获取与安全

1. 默认读取 JSON `external_rss` 的公开标题与最多 300 字符摘要；只写摘要明确支持的事实。某家 feed 无近期条目时视为空，不得使用过期内容凑数。
2. 媒体视角、复杂因果、精确数字/引语、摘要不完整或核心个股事件才升级到已登录 Chrome 原站深读；通常每封 1-3 篇。
3. Chrome 失败但 RSS 信息充分时降级为基础摘要；否则舍弃并由其他外媒或 Futu 补齐，不能中断整封 brief。
4. Agent Reach/Exa 只做候选发现，不作为订阅正文来源。不读取、导出或转发 cookie/localStorage。
5. 所有 schedule 均按无人值守运行。Bloomberg 验证页只正常刷新一次，仍失败则降级；不得自动操作 CAPTCHA、使用外部破解服务或规避付费墙。

### 四板块配额

1. **国际局势 / 地缘**：1 条外媒 + 至少 1 条 Futu。
2. **宏观 / 央行 / 大宗**：1-2 条外媒 + 至少 1 条 Futu。
3. **AI / 大模型 / 芯片**：1-2 条外媒 + 至少 1 条 Futu。
4. **个股 / 行业聚焦**：1-2 条外媒 + 至少 1 条 Futu。

正常使用 5-7 条外媒，至少覆盖三家中的 2 家；有合适内容时尽量覆盖三家，但不为凑数量牺牲相关性。国际/宏观优先 48h，AI/个股趋势类最多 7 天。

个股选择优先级：自选股/显著异动 > 业绩与指引 > 并购/资本开支 > 行业结构变化。

### 去重

- 同一事件跨媒体、跨板块只保留一条；可把外媒与 Futu 合并为双来源。
- 外媒 URL 与 `cache/sent_external_news_history.json` 比较时忽略 query string 和 fragment。
- 发送成功后，`send_email.py --external-urls-file` 将本次 URL 写入 7 天历史 cache。
- Futu `news_id` 继续通过 `--news-ids-file` 写入 `cache/sent_news_history.json`。

## Brief 结构

严格顺序：
1. 市场综述
2. 美股热点（仅两个美股 routine）
3. 国际局势 / 地缘
4. 宏观 / 央行 / 大宗
5. AI / 大模型 / 芯片
6. 个股 / 行业聚焦
7. 深度研报 / 机构观点
8. A股 / 港股市场
9. 社区观察
10. 宏观环境

「深度研报 / 机构观点」和「社区观察」不得写成执行日志；数据不足时只用读者可见话术或省略空内容。

「宏观环境」必须包含：美债收益率、美元/外汇、大宗商品、**媒体视角**、**核心观察**。媒体视角与 agent 判断要分开，核心观察必须用 JSON 行情交叉验证媒体观点。

## 排版

- 移动端优先，涨红跌绿。
- 市场综述按 `**子标题：**` + bullets 分块。
- 新闻格式：标题、2-3 句摘要、空行、来源独占一行。
- 单来源：`[FT](url) | MM-DD`
- 合并来源：`[WSJ](url) | MM-DD · [富途](url) | MM-DD`
- 邮件多人接收，禁止使用「你的自选股」等第二人称。

## 生产运行

四个 routine 源文件：
- `routines/brief-asia-preopen.md`：PT 18:00，周日到周四。
- `routines/brief-asia-midday.md`：PT 20:30，周日到周四。
- `routines/brief-us-preopen.md`：PT 06:00，周一到周五。
- `routines/brief-us-close.md`：PT 13:30，周一到周五。

生产收件人为 `config/recipients.txt`（13 人），测试收件人为 `config/recipients_test.txt`（2 人）。所有收件人 BCC；生产命令不带 `--test`。

`~/.claude/scheduled-tasks/` 下的 4 个本地 production schedule 为 ACTIVE，运行时 prompt 与仓库 `routines/` 保持同步。

## 关键文件

```text
scripts/fetch_data.py
scripts/send_email.py
routines/*.md
cache/sent_news_history.json
cache/sent_external_news_history.json
config/email.conf
config/recipients.txt
config/recipients_test.txt
```

凭证、收件人、cookie、cache 和 MCP 本地配置不得提交到仓库。
