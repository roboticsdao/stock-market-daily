import unittest
from unittest.mock import patch

import news_digest as news


class QuoteValidationTests(unittest.TestCase):
    def test_similar_quotes_do_not_block_publication(self):
        def quote(symbol):
            return dict(price=100, pct=-0.58, time='2026.09.18 22:30 JST')

        with patch.object(news, 'fetch_quote', side_effect=quote):
            digest = '## US Market\n' + '\n'.join(news.market_snapshot_items(news.CONFIG['sections'][0]))
        self.assertEqual([], news.digest_quality_issues(digest))
        self.assertEqual([], news.digest_summary_records(digest))
        page = news.md_to_html(digest)
        self.assertIn('Apple stood at', page)
        self.assertIn('Microsoft stood at', page)
        self.assertIn('2026.09.18 22:30 JST', page)
        self.assertIn('[2026.09.18]', digest)

    def test_duplicate_news_still_blocks_publication(self):
        body = 'A company announced a large factory expansion with production starting in October and new equipment arriving in September.'
        digest = '\n'.join(f'- **[2026.09.18] {title}**\n  English: {body}' for title in ('First story', 'Another story'))
        self.assertTrue(news.digest_quality_issues(digest))

    def test_quote_source_timestamp_is_required(self):
        import io
        import json
        payload = {'chart': {'result': [{'meta': {'regularMarketPrice': 100, 'chartPreviousClose': 99}}]}}
        with patch.object(news.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
            self.assertIsNone(news.fetch_quote('AAPL'))


if __name__ == '__main__':
    unittest.main()
