#!/usr/bin/env python3
"""
MarketDashboard 数据拉取脚本
一次性拉取所有行情+新闻+社区数据，输出结构化 JSON。
AI 只需要读取这个 JSON 来写分析文字，不需要自己调 API。

用法: python3 fetch_data.py > /tmp/market_data.json
"""

import json
import sys
import os
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher

# 历史新闻 cache 路径（与 send_email.py 共享）
NEWS_HISTORY_PATH = os.path.expanduser("~/Desktop/MarketDashboard/cache/sent_news_history.json")

# 时效性窗口（小时）— 不同类别使用不同窗口
TIME_WINDOWS = {
    '国际局势': 48,    # 突发类
    '宏观大宗': 48,    # 央行+大宗合并后
    '市场动态': 36,
    'AI动态': 168,     # 趋势类放宽到 7 天
    '科技消费': 168,
    '个股': 168,
}

# 主题相似度阈值（标题相似度高于此值视为同主题）
SIMILARITY_THRESHOLD = 0.7


def load_news_history() -> set:
    """加载历史已发送的 news_id 集合（最近 7 天）。"""
    if not os.path.exists(NEWS_HISTORY_PATH):
        return set()
    try:
        with open(NEWS_HISTORY_PATH) as f:
            history = json.load(f)
        all_ids = set()
        for date, ids in history.items():
            all_ids.update(ids)
        return all_ids
    except:
        return set()


def is_similar(title_a: str, title_b: str, threshold: float = SIMILARITY_THRESHOLD) -> bool:
    """判断两个标题是否同主题。"""
    if not title_a or not title_b:
        return False
    return SequenceMatcher(None, title_a, title_b).ratio() >= threshold

def fetch_futu_quotes():
    """通过 Futu OpenD 拉取自选股行情（从富途自选股列表动态获取）"""
    import logging
    logging.disable(logging.CRITICAL)

    results = {}
    watchlist_codes = []
    try:
        from futu import OpenQuoteContext
        ctx = OpenQuoteContext(host='127.0.0.1', port=11111)

        # 动态拉取自选股列表
        ret, data = ctx.get_user_security('全部')
        if ret == 0:
            watchlist_codes = data['code'].tolist()

        # 按市场分组，过滤掉期货主连（xxxmain）和不支持的类型
        hk_codes = [c for c in watchlist_codes if c.startswith('HK.')]
        us_codes = [c for c in watchlist_codes if c.startswith('US.') and 'main' not in c]
        sh_codes = [c for c in watchlist_codes if c.startswith('SH.')]
        sz_codes = [c for c in watchlist_codes if c.startswith('SZ.')]
        fx_codes = [c for c in watchlist_codes if c.startswith('FX.')]

        # 逐市场拉取行情快照
        # 重要：Futu snapshot 是"批次原子"的——只要批次里有一个不支持的代码
        # （比如 OTC 的 ATEYY），整批返回 ret=-1，所有数据都拿不到。
        # 所以批量失败时要降级为逐个查询，跳过失败的代码。
        failed_codes = []
        for group_name, codes in [('HK', hk_codes), ('US', us_codes), ('SH', sh_codes), ('SZ', sz_codes)]:
            if not codes:
                continue

            def _ingest_row(r):
                prev = r['prev_close_price']
                last = r['last_price']
                chg = ((last - prev) / prev * 100) if prev else 0
                results[r['code']] = {
                    'name': r['name'], 'last': round(last, 2),
                    'prev': round(prev, 2), 'chg': round(chg, 2)
                }

            try:
                ret, data = ctx.get_market_snapshot(codes)
                if ret == 0:
                    for _, r in data.iterrows():
                        _ingest_row(r)
                else:
                    # 批量失败 → 降级为逐个查询，跳过失败的
                    results[f'_batch_error_{group_name}'] = str(data)
                    for code in codes:
                        try:
                            r2, d2 = ctx.get_market_snapshot([code])
                            if r2 == 0 and len(d2) > 0:
                                _ingest_row(d2.iloc[0])
                            else:
                                failed_codes.append({'code': code, 'reason': str(d2)})
                        except Exception as e:
                            failed_codes.append({'code': code, 'reason': str(e)})
            except Exception as e:
                results[f'_exception_{group_name}'] = str(e)

        if failed_codes:
            results['_failed_codes'] = failed_codes

        # FX 类逐个查询（可能不支持批量）
        for code in fx_codes:
            try:
                ret, data = ctx.get_market_snapshot([code])
                if ret == 0 and len(data) > 0:
                    r = data.iloc[0]
                    prev = r['prev_close_price']
                    last = r['last_price']
                    chg = ((last - prev) / prev * 100) if prev else 0
                    results[r['code']] = {
                        'name': r['name'], 'last': round(last, 2),
                        'prev': round(prev, 2), 'chg': round(chg, 2)
                    }
            except:
                pass

        ctx.close()
    except Exception as e:
        results['_error'] = str(e)

    results['_watchlist_count'] = len(watchlist_codes)
    return results


def fetch_yfinance_quotes():
    """通过 yfinance 拉取 A股/商品/汇率/美10Y"""
    results = {}
    try:
        import yfinance as yf
        tickers = {
            '上证综指': '000001.SS', '沪深300': '000300.SS', '创业板指': '399006.SZ',
            '黄金': 'GC=F', '白银': 'SI=F', 'WTI原油': 'CL=F',
            '美元指数': 'DX-Y.NYB', '美10Y': '^TNX', '离岸人民币': 'CNH=X'
        }
        for label, sym in tickers.items():
            try:
                fi = yf.Ticker(sym).fast_info
                p, prev = fi.last_price, fi.previous_close
                chg = (p - prev) / prev * 100 if prev else 0
                results[label] = {'last': round(p, 2), 'prev': round(prev, 2), 'chg': round(chg, 2)}
            except:
                results[label] = {'last': 0, 'prev': 0, 'chg': 0, 'error': True}
    except Exception as e:
        results['_error'] = str(e)
    return results


def _fetch_raw_news(keyword: str, size: int = 15) -> list:
    """单次调用 Futu News API，返回原始结果（不过滤）。"""
    import urllib.request
    import urllib.parse

    params = urllib.parse.urlencode({
        'keyword': keyword, 'size': str(size), 'news_type': '1',
        'lang': 'zh-CN', 'sort_type': '2'
    })
    url = f'https://ai-news-search.futunn.com/news_search?{params}'
    req = urllib.request.Request(url, headers={'User-Agent': 'futunn-news-search/0.0.2 (Skill)'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return data.get('data', [])
    except Exception as e:
        return [{'_error': str(e)}]


def fetch_news(keywords_grouped, history_ids: set = None):
    """
    多阶段新闻 pipeline:
    keywords_grouped: list[(category, list[query])] - 每个板块用多个查询提高召回率

    流程：
    1. 每个板块多次调用 Futu News API
    2. 板块内 by news_id 去重，合并所有查询结果
    3. 历史去重 + 时效过滤
    4. 板块内主题相似度去重
    5. 跨板块严格 by news_id 去重（避免同一条新闻在两个板块）
    6. 按时间 × 权重排序，取 N 条
    """
    if history_ids is None:
        history_ids = set()

    all_news = {}
    used_news_ids_set = set()  # 跨板块严格去重
    now_ts = int(time.time())

    target_count = {
        '国际局势': 5,
        '宏观大宗': 5,
        '市场动态': 3,
        'AI动态': 4,
        '科技消费': 3,
    }

    for category, queries in keywords_grouped:
        category_key = '个股' if category.startswith('个股') else category
        time_window_hours = TIME_WINDOWS.get(category_key, 48)
        cutoff_ts = now_ts - time_window_hours * 3600

        # 1. 多次查询，合并 raw 结果（按 news_id 去重）
        raw_pool = {}
        for q in queries:
            items = _fetch_raw_news(q, size=15)
            if items and isinstance(items[0], dict) and '_error' in items[0]:
                continue
            for it in items:
                nid = it.get('news_id', '')
                if nid and nid not in raw_pool:
                    raw_pool[nid] = it

        # 2. 过滤+排序候选
        local_seen_titles = []
        filtered = []
        for news_id, item in raw_pool.items():
            # 历史去重
            if news_id in history_ids:
                continue
            # 跨板块去重
            if news_id in used_news_ids_set:
                continue
            # 时效性
            try:
                ts = int(item.get('publish_time', '0'))
            except:
                continue
            if ts < cutoff_ts:
                continue
            title = item.get('title', '').replace('<em>', '').replace('</em>', '')
            if not title:
                continue

            # 板块内主题相似度去重
            duplicate = False
            for prev_title in local_seen_titles:
                if is_similar(title, prev_title):
                    duplicate = True
                    break
            if duplicate:
                continue

            news_url = item.get('url', '') or f"https://news.futunn.com/post/{news_id.replace('post:', '')}"
            dt = datetime.fromtimestamp(ts).strftime('%m-%d')

            # 来源加权
            weight = 1.0
            authority_keywords = ['美联储', '央行', '高盛', '摩根', '巴克莱', 'Bloomberg', 'Reuters', '贝森特', '鲍威尔', '黄仁勋']
            if any(k in title for k in authority_keywords):
                weight = 1.5

            filtered.append({
                'title': title, 'date': dt, 'url': news_url,
                'news_id': news_id, 'ts': ts, 'weight': weight,
            })
            local_seen_titles.append(title)

        # 3. 排序取 N 条
        filtered.sort(key=lambda x: x['ts'] * x['weight'], reverse=True)
        n = target_count.get(category_key, 3)
        selected = filtered[:n]

        for it in selected:
            used_news_ids_set.add(it['news_id'])

        all_news[category] = selected

    return all_news


def fetch_community(keywords):
    """通过 Futu 社区 API 搜索帖子"""
    import urllib.request
    import urllib.parse

    all_posts = {}
    for keyword in keywords:
        params = urllib.parse.urlencode({'keyword': keyword, 'size': '5', 'lang': 'zh-CN'})
        url = f'https://ai-news-search.futunn.com/community_search?{params}'
        req = urllib.request.Request(url, headers={'User-Agent': 'futunn-news-search/0.0.2 (Skill)'})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                items = []
                for item in data.get('data', [])[:4]:
                    title = item.get('title', '').replace('<em>', '').replace('</em>', '')
                    ts = item.get('publish_time', '0')
                    dt = datetime.fromtimestamp(int(ts)).strftime('%m-%d')
                    items.append({'title': title, 'date': dt})
                all_posts[keyword] = items
        except:
            all_posts[keyword] = []
    return all_posts


def get_watchlist_names():
    """从 Futu 自选股列表提取中文名，用于新闻和社区搜索"""
    import logging
    logging.disable(logging.CRITICAL)
    names = []
    try:
        from futu import OpenQuoteContext
        ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        ret, data = ctx.get_user_security('全部')
        if ret == 0:
            names = data['name'].tolist()
        ctx.close()
    except:
        pass
    return names


def main():
    # 从自选股获取名称，用于个股新闻搜索
    stock_names = get_watchlist_names()
    # 筛选出适合搜新闻的核心标的名
    skip_words = {'ETF', '指数', '期货', '美元', '港元', '黄金', '白银', '人民币', '主连'}
    core_names = []
    for n in stock_names:
        if not n or any(s in n for s in skip_words):
            continue
        # 清理后缀
        clean = n.replace('-W','').replace('-S','').replace('集团','').replace('控股','')
        # 优先用中文名，英文名也保留
        core_names.append(clean)
    # 去重并取前 6 个
    seen = set()
    top_stocks = []
    for n in core_names:
        if n not in seen:
            seen.add(n)
            top_stocks.append(n)
        if len(top_stocks) >= 6:
            break
    if not top_stocks:
        top_stocks = ['腾讯', '英伟达', '苹果']

    # 新闻搜索关键词（每个板块用多个细分查询，提高召回率）
    # 格式：(板块名, [查询1, 查询2, ...])
    news_keywords_grouped = [
        ('国际局势', ['关税 贸易', '中东 地缘', '特朗普', '中美']),
        ('宏观大宗', ['美联储 利率', '黄金', '原油', '美元 汇率', '通胀 降息']),
        ('AI动态', ['AI 大模型', '芯片 算力', '半导体']),
        ('科技消费', ['科技 消费', '新能源车', '苹果']),
        ('市场动态', ['港股', 'A股']),
    ]
    # 个股板块每只一个关键词
    for name in top_stocks:
        news_keywords_grouped.append((f'个股_{name}', [name]))

    # 社区搜索关键词（前4个自选股名 + A股）
    community_keywords = (top_stocks[:3] if top_stocks else ['腾讯', '英伟达']) + ['A股']

    # 加载历史已发送 news_id（跨天去重）
    history_ids = load_news_history()

    # 并行拉取所有数据
    # 显式按时区计算，避免依赖系统本地时区（用户搬到 LA 后 PT 时区，原代码假设 ET 已失效）
    now_utc = datetime.now(tz=ZoneInfo("UTC"))
    pt_now = now_utc.astimezone(ZoneInfo("America/Los_Angeles"))
    et_now = now_utc.astimezone(ZoneInfo("America/New_York"))
    bj_now = now_utc.astimezone(ZoneInfo("Asia/Shanghai"))

    news_data = fetch_news(news_keywords_grouped, history_ids=history_ids)

    # 收集本次拉取的所有 news_id（供 send_email.py 写入历史）
    used_news_ids = []
    for items in news_data.values():
        for it in items:
            if 'news_id' in it:
                used_news_ids.append(it['news_id'])

    result = {
        'timestamp_pt': pt_now.strftime('%Y-%m-%d %H:%M PT'),
        'timestamp_et': et_now.strftime('%Y-%m-%d %H:%M ET'),
        'timestamp_bj': bj_now.strftime('%Y-%m-%d %H:%M 北京时间'),
        'date': pt_now.strftime('%Y-%m-%d'),
        '_pipeline_stats': {
            'history_ids_loaded': len(history_ids),
            'news_returned': sum(len(v) for v in news_data.values()),
            'used_news_ids_count': len(used_news_ids),
        },
        'used_news_ids': used_news_ids,
        'futu_quotes': fetch_futu_quotes(),
        'yfinance_quotes': fetch_yfinance_quotes(),
        'news': news_data,
        'community': fetch_community(community_keywords),
    }

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
