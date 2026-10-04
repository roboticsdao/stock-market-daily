import io
import json
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import patch

import article_summaries as summaries


class PipelineTests(unittest.TestCase):
    def test_parser_and_decoder_are_compatible(self):
        from googlenewsdecoder import gnewsdecoder
        from selectolax.parser import HTMLParser
        self.assertTrue(callable(gnewsdecoder))
        self.assertEqual("working", HTMLParser("<p>working</p>").css_first("p").text())
        summaries._ensure_article_dependencies()

    def test_decoder_to_article_body_pipeline(self):
        body = ("Atlas Robotics released a tactile sensor for warehouse robot hands. "
                "The sensor measures contact forces and was tested on twelve objects. ") * 5
        page = "<html><body><article><h1>Sensor release</h1><p>" + body + "</p></article></body></html>"
        with patch("googlenewsdecoder.gnewsdecoder", return_value={
            "status": True, "decoded_url": "https://example.com/story"
        }), patch("trafilatura.fetch_url", return_value=page):
            item = summaries._download_article({
                "headline": "Robot sensor release",
                "link": "https://news.google.com/rss/articles/test",
            })
        self.assertIsNotNone(item)
        self.assertEqual("https://example.com/story", item["link"])
        self.assertIn("twelve objects", item["article_text"])

    def test_rss_503_is_retried(self):
        error = urllib.error.HTTPError("https://example.com/rss", 503, "Unavailable", None, None)
        with patch.object(summaries.urllib.request, "urlopen",
                          side_effect=[error, io.BytesIO(b"<rss/>")]) as request, patch.object(summaries.time, "sleep"):
            self.assertEqual(b"<rss/>", summaries.fetch_rss_bytes("https://example.com/rss"))
        self.assertEqual(2, request.call_count)

    def test_permanent_rss_error_is_not_retried(self):
        error = urllib.error.HTTPError("https://example.com/rss", 404, "Not found", None, None)
        with patch.object(summaries.urllib.request, "urlopen", side_effect=error) as request:
            with self.assertRaises(urllib.error.HTTPError):
                summaries.fetch_rss_bytes("https://example.com/rss")
        self.assertEqual(1, request.call_count)

    def test_rss_retries_are_bounded(self):
        error = urllib.error.URLError("connection lost")
        with patch.object(summaries.urllib.request, "urlopen", side_effect=error) as request, patch.object(summaries.time, "sleep"):
            with self.assertRaises(urllib.error.URLError):
                summaries.fetch_rss_bytes("https://example.com/rss")
        self.assertEqual(3, request.call_count)

    def test_summaries_use_short_batches_and_keep_article_identity(self):
        def response(**kwargs):
            payload = json.loads(kwargs["contents"].split("ARTICLES:\n")[1])
            self.assertLessEqual(len(payload), 5)
            return SimpleNamespace(text=json.dumps([
                {"id": item["id"],
                 "local_summary": item["headline"] + " announced new sensors with twelve channels and testing at a warehouse.",
                 "zh_summary": item["headline"] + " 发布了具有十二个通道的新传感器，并在仓库进行了测试，原文还给出了传感器的详细技术参数。"}
                for item in payload
            ]))
        from google import genai
        with patch.object(genai, "Client") as client:
            client.return_value.models.generate_content.side_effect = response
            items = [{"headline": f"Company {i}", "article_text": "Source facts"} for i in range(12)]
            result = summaries.summarize_articles(items, "test-key")
            self.assertEqual(3, client.return_value.models.generate_content.call_count)
        self.assertEqual([item["headline"] for item in items], [item["headline"] for item in result])
        self.assertIn("Company 11", result[-1]["local_summary"])


if __name__ == "__main__":
    unittest.main()
