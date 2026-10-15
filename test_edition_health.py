import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from edition_health import publisher_candidates, write_feed


class EditionHealthTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,15,12,tzinfo=timezone.utc)

    def test_publisher_feed_does_not_accept_stale_future_or_undated_news(self):
        xml=b'<rss><channel><title>Publisher</title><item><title>Fresh robot</title><link>https://example.com/a</link><pubDate>Thu, 15 Oct 2026 10:00:00 GMT</pubDate></item><item><title>Old robot</title><link>https://example.com/b</link><pubDate>Thu, 01 Oct 2026 10:00:00 GMT</pubDate></item><item><title>Future robot</title><link>https://example.com/c</link><pubDate>Fri, 16 Oct 2026 10:00:00 GMT</pubDate></item><item><title>Undated robot</title><link>https://example.com/d</link></item></channel></rss>'
        rows=publisher_candidates(['https://example.com/feed'],self.now-timedelta(days=1),self.now,lambda title:'robot' in title,lambda request:xml)
        self.assertEqual(['Fresh robot'],[r['headline'] for r in rows])

    def test_partial_state_keeps_real_count_and_original_publication_time(self):
        item=dict(date='2026.10.15',dt=self.now-timedelta(hours=2),headline='Specific event',source='Publisher',link='https://example.com/a',region_label='Japan',local_summary='Source facts',zh_summary='Chinese facts')
        with tempfile.TemporaryDirectory() as directory:
            status=write_feed(directory,[item],'robot',self.now,{'Japan':5})
            feed=json.loads((Path(directory)/'feed.json').read_text())
        self.assertEqual('partial',status['state'])
        self.assertEqual(1,status['articles'])
        self.assertNotEqual(feed['updated_at'],feed['articles'][0]['published_at'])

    def test_zero_articles_does_not_replace_previous_edition(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                write_feed(directory,[],'robot',self.now,{'Japan':5})
            self.assertFalse((Path(directory)/'feed.json').exists())
