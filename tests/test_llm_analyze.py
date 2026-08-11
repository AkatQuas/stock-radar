"""Unit tests for llm_analyze helpers."""

import unittest

from stock_radar.llm.llm_analyze import is_analyze_complete

SAMPLE_ANALYZE = """### 排序推荐
- [600000 浦发银行](https://xueqiu.com/S/SH600000) [keep] 连板强势

### 建议剔除
- [000002 万科A](https://xueqiu.com/S/SZ000002) [veto] 换手过高
"""


class AnalyzeCompleteTests(unittest.TestCase):
    def test_complete_output(self):
        self.assertTrue(is_analyze_complete(SAMPLE_ANALYZE))

    def test_missing_section(self):
        self.assertFalse(is_analyze_complete("### 建议剔除\n- item"))


if __name__ == "__main__":
    unittest.main()
