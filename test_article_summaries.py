import unittest

from article_summaries import FORBIDDEN_ANALYSIS, _preserve_source_units, _sanitize_summary, repair_legacy_unit_corruption, summarize_articles, summary_quality_issues


class ArticleSummaryTests(unittest.TestCase):
    def test_no_api_fallback_uses_article_body_not_headline_template(self):
        body = (
            "Company A announced a new warehouse robot on Friday. "
            "The robot can lift 20 kilograms and will enter testing at two distribution centers in September. "
            "The company said the trial will run for six months with its logistics partner. "
        ) * 3
        item = {
            "headline": "A short headline",
            "article_text": body,
            "summary_language": "English",
        }
        result = summarize_articles([item], api_key="")[0]
        self.assertIn("20 kilograms", result["local_summary"])
        self.assertNotIn("A short headline", result["local_summary"])
        self.assertEqual("", result["zh_summary"])

    def test_quality_check_rejects_analysis_templates(self):
        item = {
            "headline": "Example",
            "local_summary": "Factual source extract.",
            "zh_summary": "总结事实。后续要看商业指标。",
        }
        self.assertTrue(summary_quality_issues([item]))
        self.assertIn("后续要看", FORBIDDEN_ANALYSIS)

    def test_large_units_are_not_mistranslated(self):
        source = "Cloud operators are expected to spend approximately $733 billion in 2026."
        chinese = "云运营商预计2026年支出约733亿美元。"
        corrected = _preserve_source_units(chinese, source)
        self.assertIn("$733 billion", corrected)
        self.assertNotIn("733亿美元", corrected)

    def test_large_unit_guard_does_not_replace_dates_or_plain_numbers(self):
        source = "Asteria announced on August 13 that it invested $1 million."
        chinese = "Asteria于8月13日宣布投资100万美元，这是第一笔投资。"
        corrected = _preserve_source_units(chinese, source)
        self.assertIn("8月13日", corrected)
        self.assertIn("100万美元", corrected)
        self.assertNotIn("$1 million3日", corrected)

    def test_analytical_sentence_is_removed_without_losing_facts(self):
        summary = "公司发布了新机器人，并公布三项技术参数。后续要看量产节奏和商业指标。产品将于9月公开展示。"
        sanitized = _sanitize_summary(summary)
        self.assertIn("三项技术参数", sanitized)
        self.assertIn("9月公开展示", sanitized)
        self.assertNotIn("后续要看", sanitized)

    def test_legacy_embedded_units_are_repaired(self):
        broken = "8月$1 million3日，出货8,4 billion00台，占比4 billion4%。On August 1 trillion0 billion, valuation was 60 millionbillion.993 billion yuan."
        repaired = repair_legacy_unit_corruption(broken)
        self.assertIn("8月13日", repaired)
        self.assertIn("8,400台", repaired)
        self.assertIn("占比44%", repaired)
        self.assertIn("On August 10,", repaired)
        self.assertIn("60.993 billion yuan", repaired)


if __name__ == "__main__":
    unittest.main()
