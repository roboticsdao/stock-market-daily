import unittest
from unittest.mock import patch

import news_digest as news


class QuoteValidationTests(unittest.TestCase):
    def test_same_story_bilingual_summaries_do_not_block_publication(self):
        body = 'ARM announced a chip design partnership with two manufacturers and published details of its licensing contract.'
        digest = f'- **[{news.DATE_STR}] ARM partnership**\n  English: {body}\n  中文：总结：{body}'
        self.assertEqual([], news.digest_quality_issues(digest))

    def test_quotes_cannot_replace_all_news(self):
        with patch.object(news, 'fetch_rss_items', return_value=[]), patch.object(news, 'publisher_candidates', return_value=[]), patch.object(news, 'enrich_articles', return_value=[]), patch.object(news, 'market_snapshot_items') as quotes:
            with self.assertRaisesRegex(RuntimeError, 'No readable fresh news'):
                news.generate_digest()
        quotes.assert_not_called()

    def test_empty_japan_section_does_not_discard_fresh_us_news(self):
        items = [dict(date=news.DATE_STR, dt=news.TODAY, headline=title, source='Test', link=f'https://example.com/{index}', local_summary='A source-specific factual summary.', zh_summary='根据该篇原文提炼的事实内容，保留公司、事件、时间和关键数字。') for index,title in enumerate(['Factory output increased after new production line opened', 'Cloud business revenue changed after a contract was signed', 'Chip producer released a new processor design'])]
        with patch.object(news,'fetch_rss_items',side_effect=[items,[],[]]), patch.object(news,'publisher_candidates',return_value=[]), patch.object(news,'enrich_articles',side_effect=lambda x:x), patch.object(news,'summarize_articles',side_effect=lambda x,*args,**kwargs:x), patch.object(news,'deduplicate_summaries',side_effect=lambda x:(x,[])), patch.object(news,'remove_repeated_summary_sentences',side_effect=lambda x:(x,[])), patch.object(news,'summary_quality_issues',return_value=[]), patch.object(news,'validate_digest_quality',return_value=True), patch.object(news,'write_feed') as write, patch.object(news,'market_snapshot_items',return_value=[]):
            digest=news.generate_digest()
        self.assertEqual(3,digest.count('- **'))
        self.assertIn('暂无可核实',digest)
        self.assertEqual(3,len(write.call_args.args[1]))

    def test_empty_section_notice_is_visible_without_replacing_disclaimer(self):
        page=news.md_to_html('> Original disclaimer\n## 🇯🇵 Japan Market\n> No verified new source during this session.\n## 🇺🇸 US Market\n- **['+news.DATE_STR+'] Example**\n  English: Specific article facts.')
        self.assertIn('Original disclaimer',page)
        self.assertIn('Japan Market',page)
        self.assertIn('No verified new source',page)

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
