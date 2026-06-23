import unittest

from scripts.fetch_data import (
    _parse_external_rss,
    build_community_keywords,
    build_research_queries,
    canonicalize_external_url,
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

    def test_build_community_keywords_expands_sparse_watchlist(self):
        keywords = build_community_keywords(['黄金', '腾讯控股', '美光科技'], limit=6)

        self.assertNotIn('黄金', keywords)
        self.assertIn('腾讯', keywords)
        self.assertIn('美光科技', keywords)
        self.assertIn('英伟达', keywords)
        self.assertLessEqual(len(keywords), 6)

    def test_build_research_queries_covers_watchlist_mag7_and_hotspots(self):
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
        self.assertIn('Rocket Lab USA', queries)
        self.assertNotIn('黄金', queries)

    def test_short_low_signal_community_titles_are_filtered(self):
        self.assertFalse(is_useful_community_title('微软股东'))
        self.assertTrue(is_useful_community_title('做空美光'))
        self.assertTrue(is_useful_community_title('亚马逊云科技称Agentic AI拐点已到'))


if __name__ == '__main__':
    unittest.main()
