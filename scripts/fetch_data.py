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
import html
import re
import socket
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher

# 历史新闻 cache 路径（与 send_email.py 共享）
NEWS_HISTORY_PATH = os.path.expanduser("~/Desktop/MarketDashboard/cache/sent_news_history.json")
EXTERNAL_NEWS_HISTORY_PATH = os.path.expanduser(
    "~/Desktop/MarketDashboard/cache/sent_external_news_history.json"
)

# Public publisher feeds provide titles and short excerpts without touching
# subscriber sessions. Chrome is reserved for selected articles that need
# full-text context during the writing stage.
EXTERNAL_RSS_FEEDS = {
    'Bloomberg': ['https://feeds.bloomberg.com/markets/news.rss'],
    'WSJ': ['https://feeds.content.dowjones.io/public/rss/RSSMarketsMain'],
    'FT': ['https://www.ft.com/companies?format=rss'],
    'NYT': [
        'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
        'https://rss.nytimes.com/services/xml/rss/nyt/Business.xml',
        'https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml',
        'https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml',
    ],
    'Washington Post': [
        'https://feeds.washingtonpost.com/rss/world?itid=lk_inline_manual_11',
    ],
}


def _opend_available(host: str = '127.0.0.1', port: int = 11111,
                     timeout: float = 1.0) -> bool:
    """Fail fast when Futu OpenD is not listening."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

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

# 个股新闻关键词陷阱：短名是常见词前缀时，API 会把含该前缀的无关词也命中
# （如搜"高通"命中"推高通胀"）。命中以下陷阱词的标题直接剔除。可扩展。
_STOCK_NAME_TRAPS = {
    '高通': ['高通胀', '通胀', '通货膨胀'],
}

COMMUNITY_FALLBACK_KEYWORDS = [
    '美光科技', '英伟达', 'AMD', '特斯拉', '苹果', '微软',
    '谷歌', '亚马逊', 'Meta', '英特尔', '台积电',
]

RESEARCH_MAG7_QUERIES = [
    '英伟达', '微软', '苹果', '亚马逊', '谷歌', 'Meta', '特斯拉',
]

RESEARCH_INDUSTRY_QUERIES = [
    'AI 算力 评级', '半导体 评级', '芯片 目标价', '科技股 评级',
    '新能源车 评级', '互联网 科技',
]

_COMMUNITY_SIGNAL_WORDS = [
    '涨', '跌', '买', '卖', '做多', '做空', '看多', '看空',
    '换股', '财报', '业绩', '指引', '订单', 'AI', '估值',
    '突破', '回调', '加仓', '减仓',
]


def load_news_history(max_days: int = None) -> set:
    """加载历史已发送的 news_id 集合。

    max_days=None 时返回 cache 内全部（默认 7 天滚动窗口，由 send_email.py 维护）。
    max_days=N 时只返回最近 N 天发送过的 id —— 研报板块用更短的窗口去重，
    避免被新闻共享的 7 天历史拖累到长期为空（研报召回池本来就浅）。
    """
    if not os.path.exists(NEWS_HISTORY_PATH):
        return set()
    try:
        with open(NEWS_HISTORY_PATH) as f:
            history = json.load(f)
        cutoff = None
        if max_days is not None:
            from datetime import datetime, timedelta
            cutoff = (datetime.now() - timedelta(days=max_days)).strftime('%Y-%m-%d')
        all_ids = set()
        for date, ids in history.items():
            if cutoff is not None and date < cutoff:
                continue
            all_ids.update(ids)
        return all_ids
    except:
        return set()


def canonicalize_external_url(url: str) -> str:
    """Normalize an external URL for cross-routine history comparison."""
    if not isinstance(url, str):
        return ''
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme not in {'http', 'https'} or not parts.netloc:
        return ''
    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, '', '')
    )


def load_external_news_history(max_days: int = 7) -> set:
    """Load recently used canonical publisher URLs."""
    if not os.path.exists(EXTERNAL_NEWS_HISTORY_PATH):
        return set()
    try:
        with open(EXTERNAL_NEWS_HISTORY_PATH) as f:
            history = json.load(f)
        cutoff = (datetime.now() - timedelta(days=max_days)).strftime('%Y-%m-%d')
        urls = set()
        for date, entries in history.items():
            if date < cutoff:
                continue
            for url in entries:
                canonical = canonicalize_external_url(url)
                if canonical:
                    urls.add(canonical)
        return urls
    except Exception:
        return set()


def _strip_rss_html(value: str) -> str:
    """Turn a short RSS description into bounded plain text."""
    text = re.sub(r'<[^>]+>', ' ', value or '')
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def _parse_rss_timestamp(value: str) -> int:
    """Parse RFC 2822 or ISO-8601 feed timestamps."""
    if not value:
        return 0
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _parse_external_rss(xml_data: bytes, source: str, history_urls=None,
                        recency_hours: int = 168, limit: int = 15,
                        now_ts: int = None) -> list:
    """Parse one RSS feed into the public-summary contract."""
    history_urls = history_urls or set()
    now_ts = int(time.time()) if now_ts is None else now_ts
    cutoff_ts = now_ts - recency_hours * 3600
    root = ET.fromstring(xml_data)
    out = []
    seen_urls = set()

    for item in root.findall('.//item'):
        title = _strip_rss_html(item.findtext('title') or '')
        url = (item.findtext('link') or '').strip()
        canonical_url = canonicalize_external_url(url)
        if not title or not canonical_url or canonical_url in seen_urls:
            continue
        if canonical_url in history_urls:
            continue

        date_value = item.findtext('pubDate') or item.findtext(
            '{http://purl.org/dc/elements/1.1/}date'
        ) or ''
        ts = _parse_rss_timestamp(date_value)
        if not ts or ts < cutoff_ts:
            continue

        excerpt = _strip_rss_html(item.findtext('description') or '')[:300]
        out.append({
            'source': source,
            'title': title,
            'excerpt': excerpt,
            'url': url,
            'date': datetime.fromtimestamp(ts).strftime('%m-%d'),
            'ts': ts,
            'content_level': 'rss_summary',
        })
        seen_urls.add(canonical_url)

    out.sort(key=lambda item: item['ts'], reverse=True)
    return out[:limit]


def _merge_external_items(items: list, limit: int) -> list:
    """Merge multiple feeds for one publisher, deduping by canonical URL."""
    merged = {}
    for item in items:
        canonical_url = canonicalize_external_url(item.get('url', ''))
        if not canonical_url:
            continue
        current = merged.get(canonical_url)
        if current is None or item.get('ts', 0) > current.get('ts', 0):
            merged[canonical_url] = item
    out = list(merged.values())
    out.sort(key=lambda item: item.get('ts', 0), reverse=True)
    return out[:limit]


def fetch_external_rss(history_urls=None, recency_hours: int = 168,
                       per_source: int = 15) -> dict:
    """Fetch public publisher RSS candidates for the writer."""
    history_urls = history_urls or set()
    result = {'_errors': []}
    headers = {
        'User-Agent': 'MarketDashboard/10.1 RSS Reader',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    }
    for source, urls in EXTERNAL_RSS_FEEDS.items():
        if isinstance(urls, str):
            feed_urls = [urls]
        else:
            feed_urls = list(urls or [])

        all_items = []
        recent_items = []
        for url in feed_urls:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as response:
                    xml_data = response.read()
                recent_items.extend(
                    _parse_external_rss(
                        xml_data,
                        source,
                        history_urls=set(),
                        recency_hours=recency_hours,
                        limit=per_source,
                    )
                )
                all_items.extend(
                    _parse_external_rss(
                        xml_data,
                        source,
                        history_urls=history_urls,
                        recency_hours=recency_hours,
                        limit=per_source,
                    )
                )
            except Exception as exc:
                result['_errors'].append(f'{source}: {url}: {exc}')

        result[source] = _merge_external_items(all_items, per_source)
        if feed_urls and not _merge_external_items(recent_items, per_source):
            result['_errors'].append(
                f'{source}: no RSS items within {recency_hours}h'
            )
    return result


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
    if not _opend_available():
        return {'_opend_error': 'Futu OpenD not listening on 127.0.0.1:11111'}
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


def _fetch_raw_news(keyword: str, size: int = 15, news_type: int = 1) -> list:
    """单次调用 Futu News API，返回原始结果（不过滤）。

    news_type: 1=新闻 2=公告 3=研报（机构评级/深度点评）。
    """
    import urllib.request
    import urllib.parse

    params = urllib.parse.urlencode({
        'keyword': keyword, 'size': str(size), 'news_type': str(news_type),
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
        # 个股板块取出股票名对应的陷阱词（如"高通"→剔除含"高通胀"的标题）
        stock_name = category.split('_', 1)[1] if category.startswith('个股_') else None
        name_traps = _STOCK_NAME_TRAPS.get(stock_name, []) if stock_name else []

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

            # 个股关键词误命中过滤（高通胀/通胀等陷阱词）
            if name_traps and any(tp in title for tp in name_traps):
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


# 板块归纳时要剔除的噪音板块（非主题性：持仓榜/定投/热门榜等）
_PLATE_NOISE_KW = ['持仓', '定投', '碎股', '可交易', '明星', '热门', '成分', '成份',
                   '养老', '政府', 'Moomoo', 'FUTU', '券商']


def _is_noise_plate(name: str) -> bool:
    return any(k in name for k in _PLATE_NOISE_KW)


def fetch_hotspots():
    """全市场美股热点（不依赖自选股，也不依赖 Futu 选股权限）。

    两段式：
    1. 发现：yfinance 预设筛选器（day_gainers / day_losers / most_actives）
       拉全美股异动个股 —— 免费、不碰富途权限。
    2. 归纳：Futu get_owner_plate 批量把异动个股映射到中文概念/行业板块，
       按出现频次排序，得到"今日热点板块"。
    """
    result = {'hot_sectors': [], 'top_gainers': [], 'top_losers': [],
              'most_actives': [], '_errors': []}
    movers = {}  # symbol -> {sym, name, chg, vol, price}

    # --- 1. yfinance 发现 ---
    try:
        import yfinance as yf

        def pull(screen, n):
            out = []
            try:
                r = yf.screen(screen, count=n)
                quotes = r.get('quotes', []) if isinstance(r, dict) else (r or [])
                for q in quotes[:n]:
                    sym = q.get('symbol')
                    if not sym:
                        continue
                    out.append({
                        'sym': sym,
                        'name': q.get('shortName') or q.get('longName') or sym,
                        'chg': round(q.get('regularMarketChangePercent') or 0, 2),
                        'vol': int(q.get('regularMarketVolume') or 0),
                        'price': round(q.get('regularMarketPrice') or 0, 2),
                    })
            except Exception as e:
                result['_errors'].append(f'screen {screen}: {e}')
            return out

        result['top_gainers'] = pull('day_gainers', 8)
        result['top_losers'] = pull('day_losers', 6)
        result['most_actives'] = pull('most_actives', 8)
        for m in result['top_gainers'] + result['top_losers'] + result['most_actives']:
            movers.setdefault(m['sym'], m)
    except Exception as e:
        result['_errors'].append(f'yfinance: {e}')
        return result

    if not movers:
        return result

    # --- 2. Futu owner_plate 归纳板块 ---
    import logging
    logging.disable(logging.CRITICAL)
    try:
        if not _opend_available():
            result['_errors'].append('futu_owner_plate: OpenD not listening on 127.0.0.1:11111')
            return result
        from futu import OpenQuoteContext, RET_OK
        from collections import defaultdict
        ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        us_codes = [f"US.{s}" for s in movers.keys()]

        # 批量查；批次失败则降级逐个（避免单个未知代码拖垮整批，沿用 V8.3 思路）
        rows = []
        ret, pdata = ctx.get_owner_plate(us_codes)
        if ret == RET_OK:
            rows = [r for _, r in pdata.iterrows()]
        else:
            result['_errors'].append(f'owner_plate batch: {str(pdata)[:80]}')
            for c in us_codes:
                try:
                    r2, d2 = ctx.get_owner_plate([c])
                    if r2 == RET_OK:
                        rows.extend([r for _, r in d2.iterrows()])
                except Exception:
                    pass
        ctx.close()

        plate_members = defaultdict(set)
        for row in rows:
            if row.get('plate_type') in ('CONCEPT', 'INDUSTRY'):
                pname = row.get('plate_name', '')
                if pname and not _is_noise_plate(pname):
                    sym = str(row.get('code', '')).split('.')[-1]
                    if sym in movers:
                        plate_members[pname].add(sym)

        sectors = []
        for pname, syms in plate_members.items():
            if len(syms) < 2:  # 至少 2 只异动股归同一板块才算热点
                continue
            leaders = sorted(
                ({'sym': s, 'name': movers[s]['name'], 'chg': movers[s]['chg']} for s in syms),
                key=lambda x: abs(x['chg']), reverse=True
            )
            sectors.append({'name': pname, 'count': len(syms), 'leaders': leaders})
        sectors.sort(key=lambda x: x['count'], reverse=True)

        # 重叠去重：同一波异动常被概念板块+行业板块各算一遍（如"太空概念"vs"航空航天与国防"）。
        # 成员重叠 ≥60% 视为同一热点，保留 count 更高的，另一个名字挂到 aka。
        deduped = []
        for sec in sectors:
            sset = {l['sym'] for l in sec['leaders']}
            merged = False
            for kept in deduped:
                kset = {l['sym'] for l in kept['leaders']}
                inter = len(sset & kset)
                if inter and inter / min(len(sset), len(kset)) >= 0.6:
                    aka = kept.setdefault('aka', [])
                    if len(aka) < 2:  # 别名最多留 2 个，避免 mega-cap 串成长链
                        aka.append(sec['name'])
                    merged = True
                    break
            if not merged:
                deduped.append(sec)
        result['hot_sectors'] = deduped[:5]
    except Exception as e:
        result['_errors'].append(f'futu_owner_plate: {e}')

    return result


def fetch_community(keywords, recency_hours=72):
    """通过 Futu 社区 API 搜索帖子。

    社区接口每条只有 title（即帖子标题/首句，就是股民的真实观点），
    无正文/无互动数/url 为空。所以只保留**近 recency_hours 小时**的帖，多取一些，
    把帖子原话原样带出，交给 brief 引用（而不是概括成废话）。
    """
    import urllib.request
    import urllib.parse

    now_ts = int(time.time())
    cutoff_ts = now_ts - recency_hours * 3600
    all_posts = {}
    for keyword in keywords:
        params = urllib.parse.urlencode({'keyword': keyword, 'size': '12', 'lang': 'zh-CN'})
        url = f'https://ai-news-search.futunn.com/community_search?{params}'
        req = urllib.request.Request(url, headers={'User-Agent': 'futunn-news-search/0.0.2 (Skill)'})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            items = []
            for item in data.get('data', []):
                title = item.get('title', '').replace('<em>', '').replace('</em>', '').strip()
                if not title or not is_useful_community_title(title):
                    continue
                try:
                    ts = int(item.get('publish_time', '0'))
                except (TypeError, ValueError):
                    continue
                if ts < cutoff_ts:  # 只要近 72h 的最新帖
                    continue
                dt = datetime.fromtimestamp(ts).strftime('%m-%d')
                items.append({'title': title, 'date': dt, 'ts': ts})
            items.sort(key=lambda x: x['ts'], reverse=True)
            all_posts[keyword] = items[:6]
        except Exception:
            all_posts[keyword] = []
    return all_posts


def is_useful_community_title(title: str) -> bool:
    """Keep only titles that carry an actual retail view or market signal."""
    title = (title or '').strip()
    if not title:
        return False
    if len(title) > 6:
        return True
    return any(word in title for word in _COMMUNITY_SIGNAL_WORDS)


def _clean_search_name(name: str) -> str:
    return (name or '').replace('-W', '').replace('-S', '').replace(
        '集团', ''
    ).replace('控股', '').strip()


def _skip_market_keyword(name: str) -> bool:
    skip_words = {
        'ETF', '指数', '期货', '美元', '港元', '黄金', '白银', '人民币', '主连',
        '日经', '标普', '纳指', '道琼斯', '恒生', '沪深', '上证', '创业板',
    }
    return not name or any(word in name for word in skip_words)


def collect_hotspot_keywords(hotspots: dict, limit=8) -> list:
    """Extract searchable company names from yfinance/Futu hotspot data."""
    if not isinstance(hotspots, dict):
        return []
    out = []
    for key in ('top_gainers', 'top_losers', 'most_actives'):
        for item in hotspots.get(key, []) or []:
            out.append(item.get('name') or item.get('sym'))
    for sector in hotspots.get('hot_sectors', []) or []:
        for leader in sector.get('leaders', []) or []:
            out.append(leader.get('name') or leader.get('sym'))
    cleaned = []
    seen = set()
    for name in out:
        clean = _clean_search_name(str(name))
        if _skip_market_keyword(clean) or clean in seen:
            continue
        seen.add(clean)
        cleaned.append(clean)
        if len(cleaned) >= limit:
            break
    return cleaned


def build_research_queries(stock_names=None, hotspots=None, limit=24) -> list:
    """Build research queries by priority: watchlist, Mag7, industries, hotspots."""
    out = []
    seen = set()

    def add_group(group, cap):
        added = 0
        for name in group:
            clean = _clean_search_name(str(name))
            if _skip_market_keyword(clean) or clean in seen:
                continue
            seen.add(clean)
            out.append(clean)
            added += 1
            if len(out) >= limit or added >= cap:
                break

    add_group(list(stock_names or []), 10)
    add_group(RESEARCH_MAG7_QUERIES, 7)
    add_group(RESEARCH_INDUSTRY_QUERIES, 5)
    add_group(collect_hotspot_keywords(hotspots, limit=8), limit)
    return out


def build_community_keywords(stock_names, limit=20):
    """Build a wider but still focused community-search list.

    Futu community search is sparse and only returns titles. Searching only the
    first few watchlist names often leaves the brief with one usable symbol, so
    we combine cleaned watchlist names with a small US tech/semiconductor
    fallback basket and let recency filtering decide what is usable.
    """
    out = []
    seen = set()
    for name in list(stock_names or []) + COMMUNITY_FALLBACK_KEYWORDS:
        clean = _clean_search_name(str(name))
        if _skip_market_keyword(clean) or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= limit:
            break
    return out

# 研报独立去重窗口（天）：比新闻的 7 天短，研报召回浅、shelf-life 长，可跨天复现。
RESEARCH_DEDUP_DAYS = 2
# 研报至少凑够几条；不足时从新闻板块提升「机构评级」类条目补足
RESEARCH_MIN_ITEMS = 3
# 判定一条新闻其实是「机构研报/评级」的关键词（命中即可提升到研报板块）。
# 刻意不含裸的 "维持/上调/下调" —— 它们也出现在"维持/上调利率"等货币政策语境，
# 会把宏观新闻误判成研报；评级类标题基本都带 "评级/目标价"，由它们兜住。
_RESEARCH_KEYWORDS = ['评级', '目标价', '跑赢大市', '跑输大市', '重申', '首予',
                      '增持', '减持', '看至', '分析师', 'outperform', 'overweight',
                      'underweight', 'strong buy', 'price target']


def supplement_research_from_news(research_data, news_data, min_items=RESEARCH_MIN_ITEMS,
                                  history_ids=None):
    """研报不足 min_items 时，从已召回的新闻板块里把「机构评级/目标价」类条目提升到研报。

    被提升的条目会**从原新闻板块移除**，避免同一条在新闻和研报里各出现一次。
    候选板块优先级：个股（自选股）→ AI/科技消费 → 宏观大宗。
    """
    if len(research_data) >= min_items:
        return research_data
    import re
    if history_ids is None:
        history_ids = set()
    a_share_re = re.compile(r'[（(]\d{6}[)）]')
    seen_titles = [r.get('title', '') for r in research_data]
    seen_ids = {r.get('news_id') for r in research_data}

    cand_sections = [k for k in news_data if k.startswith('个股_')]
    cand_sections += [k for k in ('AI动态', '科技消费', '宏观大宗') if k in news_data]
    promoted = []
    for sec in cand_sections:
        kept = []
        for it in news_data[sec]:
            title = it.get('title', '')
            nid = it.get('news_id', '')
            if (len(research_data) + len(promoted) < min_items
                    and nid not in seen_ids
                    and nid not in history_ids
                    and not a_share_re.search(title)
                    and any(k in title for k in _RESEARCH_KEYWORDS)
                    and not any(is_similar(title, t) for t in seen_titles)):
                promoted.append({
                    'title': title, 'date': it.get('date'), 'url': it.get('url'),
                    'news_id': nid, 'ts': it.get('ts'), 'from_news': True,
                })
                seen_titles.append(title)
                seen_ids.add(nid)
                # 不放回 kept → 从原板块移除
            else:
                kept.append(it)
        news_data[sec] = kept

    return research_data + promoted


RESEARCH_PER_SUBJECT_CAP = 2  # 同一公司/题材最多几条研报，避免单只票刷满整栏


def _research_subject_keys(item, queries) -> set:
    """一条研报归属的主题键：召回它的查询 + 标题里命中的其他查询名。

    跨查询泄漏很常见（"科技股 评级" 也会捞到微软），所以标题命中的名字
    同样计入限额，否则同一家公司还是能换个查询绕过去。
    """
    keys = {item.get('_query', '')}
    title = item.get('title', '')
    keys.update(q for q in (queries or []) if q and q in title)
    return {k for k in keys if k}


def select_research_items(candidates, queries, limit,
                         per_subject_cap=RESEARCH_PER_SUBJECT_CAP) -> list:
    """按查询优先级轮转选条，并限制同一主题最多 per_subject_cap 条。

    只按 (query_rank, -ts) 排序会让靠前的关键词一口气占满整栏——实测出现过
    5 条研报里 4 条微软。这里改为按优先级分组后一轮一轮取每组最新的一条，
    同一主题取满限额后让位给后面的公司。
    """
    ranks = sorted({c.get('_query_rank', 9999) for c in candidates})
    grouped = {}
    for rank in ranks:
        grouped[rank] = sorted(
            [c for c in candidates if c.get('_query_rank', 9999) == rank],
            key=lambda x: x['ts'], reverse=True,
        )

    subject_counts = {}
    selected = []
    max_depth = max((len(g) for g in grouped.values()), default=0)
    for depth in range(max_depth):
        if len(selected) >= limit:
            break
        for rank in ranks:
            if len(selected) >= limit:
                break
            group = grouped[rank]
            if depth >= len(group):
                continue
            item = group[depth]
            keys = _research_subject_keys(item, queries)
            if any(subject_counts.get(k, 0) >= per_subject_cap for k in keys):
                continue
            for k in keys:
                subject_counts[k] = subject_counts.get(k, 0) + 1
            selected.append(item)

    # 轮转只用于"选哪几条"；最终展示顺序仍按优先级+时间，
    # 免得同一家公司的两条研报被别的公司隔开。
    selected.sort(key=lambda x: (x.get('_query_rank', 9999), -x['ts']))
    for item in selected:
        item.pop('_query_rank', None)
        item.pop('_query', None)
    return selected


def fetch_research(history_ids=None, recency_hours=72, limit=5, queries=None):
    """机构研报/评级（Futu news_type=3）。仅保留美股+港股，剔除 A股（标题含 6 位代码）。

    多题材召回 → 历史去重 → 近 72h → 剔除 A股 → 主题相似度去重
    → 按查询优先级轮转取 N 条，同一公司最多 RESEARCH_PER_SUBJECT_CAP 条。
    查询顺序由 build_research_queries() 控制：
    自选股 → Mag7 → 相关行业 → 市场热点股兜底。
    """
    import re
    if history_ids is None:
        history_ids = set()
    now_ts = int(time.time())
    cutoff_ts = now_ts - recency_hours * 3600
    a_share_re = re.compile(r'[（(]\d{6}[)）]')  # A股 6 位代码，如 (603713)/（002025）

    pool = {}
    query_list = list(queries or build_research_queries())
    for query_rank, q in enumerate(query_list):
        items = _fetch_raw_news(q, size=10, news_type=3)
        if items and isinstance(items[0], dict) and '_error' in items[0]:
            continue
        for it in items:
            nid = it.get('news_id', '')
            if nid and (nid not in pool or query_rank < pool[nid]['query_rank']):
                pool[nid] = {'item': it, 'query_rank': query_rank, 'query': q}

    seen_titles = []
    out = []
    for nid, record in pool.items():
        item = record['item']
        if nid in history_ids:
            continue
        try:
            ts = int(item.get('publish_time', '0'))
        except (TypeError, ValueError):
            continue
        if ts < cutoff_ts:
            continue
        title = item.get('title', '').replace('<em>', '').replace('</em>', '').strip()
        if not title:
            continue
        if a_share_re.search(title):  # 剔除 A股研报
            continue
        if any(is_similar(title, t) for t in seen_titles):
            continue
        url = item.get('url', '') or f"https://news.futunn.com/post/{nid.replace('post:', '')}"
        out.append({'title': title, 'date': datetime.fromtimestamp(ts).strftime('%m-%d'),
                    'url': url, 'news_id': nid, 'ts': ts,
                    '_query_rank': record['query_rank'],
                    '_query': record['query']})
        seen_titles.append(title)

    return select_research_items(out, query_list, limit)


def get_watchlist_names():
    """从 Futu 自选股列表提取中文名，用于新闻和社区搜索"""
    import logging
    logging.disable(logging.CRITICAL)
    names = []
    if not _opend_available():
        return names
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
    skip_words = {
        'ETF', '指数', '期货', '美元', '港元', '黄金', '白银', '人民币', '主连',
        '日经', '标普', '纳指', '道琼斯', '恒生', '沪深', '上证', '创业板',
    }
    core_names = []
    for n in stock_names:
        if not n or any(s in n for s in skip_words):
            continue
        # 清理后缀
        clean = _clean_search_name(n)
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

    # 社区搜索关键词：社区接口召回稀疏，扩大到更多自选股 + 美股科技 fallback。
    # 最终 brief 仍必须只引用有原话、有信息量的近 72h 帖子。
    community_keywords = build_community_keywords(core_names or top_stocks)

    # 加载历史已发送 news_id（跨天去重）
    history_ids = load_news_history()
    external_history_urls = load_external_news_history()

    # 并行拉取所有数据
    # 显式按时区计算，避免依赖系统本地时区（用户搬到 LA 后 PT 时区，原代码假设 ET 已失效）
    now_utc = datetime.now(tz=ZoneInfo("UTC"))
    pt_now = now_utc.astimezone(ZoneInfo("America/Los_Angeles"))
    et_now = now_utc.astimezone(ZoneInfo("America/New_York"))
    bj_now = now_utc.astimezone(ZoneInfo("Asia/Shanghai"))

    hotspots_data = fetch_hotspots()
    news_data = fetch_news(news_keywords_grouped, history_ids=history_ids)
    # 研报用更短的独立去重窗口（避免被新闻 7 天历史拖到长期空）
    research_history_ids = load_news_history(max_days=RESEARCH_DEDUP_DAYS)
    research_queries = build_research_queries(core_names, hotspots=hotspots_data)
    research_data = fetch_research(
        history_ids=research_history_ids,
        queries=research_queries,
    )
    # 仍不足时，从新闻板块提升「机构评级」类条目补足（并从原板块移除避免重复）
    research_data = supplement_research_from_news(
        research_data, news_data, history_ids=history_ids)
    external_rss = fetch_external_rss(history_urls=external_history_urls)
    community_data = fetch_community(community_keywords)

    # 收集本次拉取的所有 news_id（供 send_email.py 写入历史；研报也参与跨天去重）
    used_news_ids = []
    for items in news_data.values():
        for it in items:
            if 'news_id' in it:
                used_news_ids.append(it['news_id'])
    for it in research_data:
        if 'news_id' in it:
            used_news_ids.append(it['news_id'])

    result = {
        'timestamp_pt': pt_now.strftime('%Y-%m-%d %H:%M PT'),
        'timestamp_et': et_now.strftime('%Y-%m-%d %H:%M ET'),
        'timestamp_bj': bj_now.strftime('%Y-%m-%d %H:%M 北京时间'),
        'date': et_now.strftime('%Y-%m-%d'),  # 用户所在时区（纽约）的日期
        '_pipeline_stats': {
            'history_ids_loaded': len(history_ids),
            'research_history_window_days': RESEARCH_DEDUP_DAYS,
            'research_history_ids_loaded': len(research_history_ids),
            'research_queries_count': len(research_queries),
            'news_returned': sum(len(v) for v in news_data.values()),
            'research_returned': len(research_data),
            'research_supplemented': sum(1 for r in research_data if r.get('from_news')),
            'external_history_urls_loaded': len(external_history_urls),
            'external_rss_returned': sum(
                len(items) for source, items in external_rss.items()
                if source != '_errors'
            ),
            'community_keywords_count': len(community_keywords),
            'community_symbols_with_posts': sum(1 for items in community_data.values() if items),
            'community_posts_returned': sum(len(items) for items in community_data.values()),
            'used_news_ids_count': len(used_news_ids),
        },
        'used_news_ids': used_news_ids,
        'futu_quotes': fetch_futu_quotes(),
        'yfinance_quotes': fetch_yfinance_quotes(),
        'hotspots': hotspots_data,
        'news': news_data,
        'research': research_data,
        'community': community_data,
        'external_rss': external_rss,
    }

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
