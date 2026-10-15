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
        with patch.object(summaries, "_decode_google_news", return_value={
            "status": True, "decoded_url": "https://example.com/story"
        }), patch.object(summaries.urllib.request, "urlopen", return_value=io.BytesIO(page.encode())) as fetch:
            item = summaries._download_article({
                "headline": "Robot sensor release",
                "link": "https://news.google.com/rss/articles/test",
            })
        self.assertIsNotNone(item)
        self.assertEqual("https://example.com/story", item["link"])
        self.assertIn("twelve objects", item["article_text"])
        self.assertEqual(15, fetch.call_args.kwargs["timeout"])

    def test_decoder_has_a_hard_process_deadline(self):
        with patch.object(summaries.subprocess, "run") as run:
            run.return_value.stdout = '{"status":false}'
            self.assertFalse(summaries._decode_google_news("https://news.google.com/rss/articles/test")["status"])
            self.assertEqual(35, run.call_args.kwargs["timeout"])

    def test_one_refused_article_cannot_discard_other_translations(self):
        def response(**kwargs):
            payload = json.loads(kwargs["contents"].split("ARTICLES:\n")[1])
            if len(payload) > 1 or payload[0]["headline"] == "Refused":
                return SimpleNamespace(text="")
            return SimpleNamespace(text=json.dumps([{
                "id": "0", "local_summary": "This source describes a new tactile sensor with twelve force channels, tested on ten different objects.",
                "zh_summary": "该公司发布新触觉传感器，拥有十二个力通道，并在十种不同物体上进行了测试。原文还介绍了硬件的测试方法、具体参数与实验过程。"
            }]))
        from google import genai
        with patch.object(genai, "Client") as client, patch.object(summaries.time, "sleep"):
            client.return_value.models.generate_content.side_effect = response
            items = [{"headline": title, "article_text": "A factual source body about sensors and robotics." * 10} for title in ("Valid", "Refused")]
            result = summaries.summarize_articles(items, "test-key")
        self.assertTrue(result[0]["zh_summary"])
        self.assertFalse(result[1]["zh_summary"])

    def test_timed_out_source_does_not_discard_other_articles(self):
        good = {"headline": "Good source", "article_text": "Verified facts"}
        with patch.object(summaries, "_download_article", side_effect=[TimeoutError("source stalled"), good]):
            self.assertEqual([good], summaries.enrich_articles([{"headline": "Stalled"}, good], workers=1))

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
