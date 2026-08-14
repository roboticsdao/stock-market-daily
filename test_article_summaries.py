import unittest

from article_summaries import FORBIDDEN_ANALYSIS, _preserve_source_units, summarize_articles, summary_quality_issues


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


if __name__ == "__main__":
    unittest.main()
