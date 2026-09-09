import unittest
from unittest.mock import patch

from scripts.fetch_data import (
    EXTERNAL_RSS_FEEDS,
    _parse_external_rss,
    build_community_keywords,
    build_research_queries,
    canonicalize_external_url,
    fetch_research,
    fetch_external_rss,
    is_useful_community_title,
)


SAMPLE_RSS = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Markets &amp; AI</title>
    <link>https://example.com/article?id=tracking#section</link>
    <description><![CDATA[<p>Stocks rose <b>2%</b> after the update.</p>]]></description>
    <pubDate>Mon, 22 Jun 2026 12:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Old item</title>
    <link>https://example.com/old</link>
    <description>Too old</description>
    <pubDate>Mon, 01 Jun 2026 12:00:00 GMT</pubDate>
  </item>
</channel></rss>'''


class ExternalRssTests(unittest.TestCase):
    def test_wsj_feed_uses_current_official_endpoint(self):
        self.assertIn(
            'https://feeds.content.dowjones.io/public/rss/RSSMarketsMain',
            EXTERNAL_RSS_FEEDS['WSJ'],
        )

    def test_nyt_and_washington_post_feeds_are_configured(self):
        self.assertNotIn('https://www.nytimes.com/rss', EXTERNAL_RSS_FEEDS['NYT'])
        self.assertIn(
            'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
            EXTERNAL_RSS_FEEDS['NYT'],
        )
        self.assertIn(
            'https://rss.nytimes.com/services/xml/rss/nyt/Business.xml',
            EXTERNAL_RSS_FEEDS['NYT'],
        )
        self.assertIn(
            'https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml',
            EXTERNAL_RSS_FEEDS['NYT'],
        )
        self.assertIn(
            'https://feeds.washingtonpost.com/rss/world?itid=lk_inline_manual_11',
            EXTERNAL_RSS_FEEDS['Washington Post'],
        )

    def test_canonical_url_drops_query_and_fragment(self):
        self.assertEqual(
            canonicalize_external_url('HTTPS://Example.COM/a?x=1#part'),
            'https://example.com/a',
        )

    def test_parser_emits_bounded_public_summary_contract(self):
        items = _parse_external_rss(
            SAMPLE_RSS,
            'Example',
            recency_hours=168,
            now_ts=1782158400,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], 'Markets & AI')
        self.assertEqual(items[0]['excerpt'], 'Stocks rose 2% after the update.')
        self.assertEqual(items[0]['content_level'], 'rss_summary')

    def test_parser_filters_canonical_history_url(self):
        items = _parse_external_rss(
            SAMPLE_RSS,
            'Example',
            history_urls={'https://example.com/article'},
            recency_hours=168,
            now_ts=1782158400,
        )

        self.assertEqual(items, [])

    def test_fetch_external_rss_merges_multiple_feeds_per_source(self):
        rss_one = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Older duplicate</title>
    <link>https://example.com/a?utm=one</link>
    <description>older</description>
    <pubDate>Mon, 22 Jun 2026 10:00:00 GMT</pubDate>
  </item>
</channel></rss>'''
        rss_two = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Newer duplicate</title>
    <link>https://example.com/a?utm=two</link>
    <description>newer</description>
    <pubDate>Mon, 22 Jun 2026 12:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Unique item</title>
    <link>https://example.com/b</link>
    <description>unique</description>
    <pubDate>Mon, 22 Jun 2026 11:00:00 GMT</pubDate>
  </item>
</channel></rss>'''

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def read(self):
                return self.payload

        def fake_urlopen(req, timeout=15):
            payloads = {
                'https://feed.example.com/one': rss_one,
                'https://feed.example.com/two': rss_two,
            }
            return FakeResponse(payloads[req.full_url])

        with patch('scripts.fetch_data.EXTERNAL_RSS_FEEDS', {
            'NYT': ['https://feed.example.com/one', 'https://feed.example.com/two'],
        }):
            with patch('scripts.fetch_data.urllib.request.urlopen', side_effect=fake_urlopen):
                with patch('scripts.fetch_data.time.time', return_value=1782158400):
                    result = fetch_external_rss(history_urls=set(), per_source=5)

        self.assertEqual(result['_errors'], [])
        self.assertEqual([item['title'] for item in result['NYT']], [
            'Newer duplicate',
            'Unique item',
        ])
        self.assertTrue(all(item['source'] == 'NYT' for item in result['NYT']))

    def test_build_community_keywords_expands_sparse_watchlist(self):
        keywords = build_community_keywords(['黄金', '腾讯控股', '美光科技'], limit=6)

        self.assertNotIn('黄金', keywords)
        self.assertIn('腾讯', keywords)
        self.assertIn('美光科技', keywords)
        self.assertIn('英伟达', keywords)
        self.assertLessEqual(len(keywords), 6)

    def test_build_research_queries_prioritizes_watchlist_mag7_industry_hotspots(self):
        queries = build_research_queries(
            ['腾讯控股', '黄金'],
            hotspots={
                'top_gainers': [{'name': 'Rocket Lab USA'}],
                'top_losers': [],
                'most_actives': [],
                'hot_sectors': [],
            },
            limit=24,
        )

        self.assertIn('腾讯', queries)
        self.assertIn('微软', queries)
        self.assertIn('半导体 评级', queries)
        self.assertIn('Rocket Lab USA', queries)
        self.assertNotIn('黄金', queries)
        self.assertLess(queries.index('腾讯'), queries.index('微软'))
        self.assertLess(queries.index('微软'), queries.index('半导体 评级'))
        self.assertLess(queries.index('半导体 评级'), queries.index('Rocket Lab USA'))

    def test_fetch_research_keeps_query_priority_ahead_of_recency(self):
        now_ts = 1782250000

        def fake_fetch(query, size=10, news_type=None):
            if query == '腾讯':
                return [{
                    'news_id': 'watchlist:1',
                    'publish_time': str(now_ts - 48 * 3600),
                    'title': '腾讯控股获机构上调目标价',
                    'url': 'https://news.example.com/tencent',
                }]
            if query == 'Rocket Lab USA':
                return [{
                    'news_id': 'hotspot:1',
                    'publish_time': str(now_ts - 60),
                    'title': 'Rocket Lab USA获机构上调目标价',
                    'url': 'https://news.example.com/rklb',
                }]
            return []

        with patch('scripts.fetch_data.time.time', return_value=now_ts):
            with patch('scripts.fetch_data._fetch_raw_news', side_effect=fake_fetch):
                items = fetch_research(
                    history_ids=set(),
                    recency_hours=72,
                    limit=2,
                    queries=['腾讯', 'Rocket Lab USA'],
                )

        self.assertEqual([item['news_id'] for item in items], ['watchlist:1', 'hotspot:1'])
        self.assertNotIn('_query_rank', items[0])
        self.assertNotIn('_query', items[0])

    def test_fetch_research_caps_repeats_of_one_company(self):
        now_ts = 1782250000

        def fake_fetch(query, size=10, news_type=None):
            if query == '微软':
                titles = [
                    '联博集团维持微软(MSFT.US)买入评级，维持目标价660美元',
                    '摩根士丹利：微软为AI时代重塑业务架构，重申增持评级',
                    '微软（MSFT）：对该科技巨头的新买入评级',
                    '分析师就科技公司提供见解：Samsung Electronics和微软',
                ]
                return [{
                    'news_id': f'msft:{i}',
                    'publish_time': str(now_ts - i * 3600),
                    'title': title,
                    'url': f'https://news.example.com/msft{i}',
                } for i, title in enumerate(titles)]
            if query == '苹果':
                return [{
                    'news_id': 'aapl:1',
                    'publish_time': str(now_ts - 10 * 3600),
                    'title': '汇丰重申对苹果的买入评级',
                    'url': 'https://news.example.com/aapl',
                }]
            return []

        with patch('scripts.fetch_data.time.time', return_value=now_ts):
            with patch('scripts.fetch_data._fetch_raw_news', side_effect=fake_fetch):
                items = fetch_research(
                    history_ids=set(),
                    recency_hours=72,
                    limit=5,
                    queries=['英伟达', '微软', '苹果'],
                )

        ids = [item['news_id'] for item in items]
        self.assertEqual(len(ids), 3)
        self.assertEqual(sum(1 for i in ids if i.startswith('msft')), 2)
        self.assertIn('aapl:1', ids)
        # 优先级仍在前，同一家公司的两条挨在一起
        self.assertEqual(ids, ['msft:0', 'msft:1', 'aapl:1'])

    def test_research_subject_cap_counts_titles_across_queries(self):
        now_ts = 1782250000

        def fake_fetch(query, size=10, news_type=None):
            if query == '微软':
                titles = [
                    '联博集团维持微软(MSFT.US)买入评级，维持目标价660美元',
                    '摩根士丹利：微软为AI时代重塑业务架构，重申增持评级',
                ]
                return [{
                    'news_id': f'msft:{i}',
                    'publish_time': str(now_ts - i * 3600),
                    'title': title,
                    'url': f'https://news.example.com/msft{i}',
                } for i, title in enumerate(titles)]
            if query == '科技股 评级':
                return [{
                    'news_id': 'leak:1',
                    'publish_time': str(now_ts - 5 * 3600),
                    'title': '大行上调微软目标价至700美元',
                    'url': 'https://news.example.com/leak',
                }]
            return []

        with patch('scripts.fetch_data.time.time', return_value=now_ts):
            with patch('scripts.fetch_data._fetch_raw_news', side_effect=fake_fetch):
                items = fetch_research(
                    history_ids=set(),
                    recency_hours=72,
                    limit=5,
                    queries=['微软', '科技股 评级'],
                )

        # leak:1 由别的查询召回但标题仍是微软，算进同一主题限额；
        # 限额用满后 msft:1 被挡下，整栏最多两条微软。
        ids = [item['news_id'] for item in items]
        self.assertEqual(ids, ['msft:0', 'leak:1'])
        self.assertNotIn('msft:1', ids)

    def test_short_low_signal_community_titles_are_filtered(self):
        self.assertFalse(is_useful_community_title('微软股东'))
        self.assertTrue(is_useful_community_title('做空美光'))
        self.assertTrue(is_useful_community_title('亚马逊云科技称Agentic AI拐点已到'))


if __name__ == '__main__':
    unittest.main()
