"""Unit tests for llm_analyze helpers."""

import unittest

import pandas as pd

from stock_radar.llm.llm_analyze import (
    build_analyze_prompt,
    extract_verdict,
    is_analyze_complete,
    parse_analyze_sections,
)

SAMPLE_ANALYZE = """### 排序推荐
- [600000 浦发银行](https://xueqiu.com/S/SH600000) [keep] 连板强势

### 建议剔除
- [000002 万科A](https://xueqiu.com/S/SZ000002) [veto] 换手过高
"""


class AnalyzeCompleteTests(unittest.TestCase):
    def test_complete_output(self):
        self.assertTrue(is_analyze_complete(SAMPLE_ANALYZE))

    def test_missing_rank_section(self):
        self.assertFalse(is_analyze_complete("### 建议剔除\n- item"))

    def test_ranked_only_is_complete(self):
        self.assertTrue(is_analyze_complete("### 排序推荐\n- item"))

    def test_build_analyze_prompt_includes_track_and_payload(self):
        records = [{"symbol": "600000", "name": "浦发银行", "matched_selectors": ["test"]}]
        prompt = build_analyze_prompt(records, pd.Timestamp("2026-01-10"), track="pool")
        self.assertIn("track=pool", prompt)
        self.assertIn("600000", prompt)
        self.assertIn("### 排序推荐", prompt)

    def test_parse_analyze_sections(self):
        parsed = parse_analyze_sections(SAMPLE_ANALYZE)
        self.assertEqual(len(parsed.ranked_lines), 1)
        self.assertEqual(len(parsed.veto_lines), 1)
        self.assertIn("600000", parsed.ranked_lines[0])
        self.assertIn("000002", parsed.veto_lines[0])

    def test_extract_verdict(self):
        self.assertEqual(extract_verdict("- [600000 浦发银行](url) [keep] reason"), "keep")
        self.assertEqual(extract_verdict("- [000002 万科A](url) [veto] reason"), "veto")
        self.assertIsNone(extract_verdict("- no verdict here"))


if __name__ == "__main__":
    unittest.main()
