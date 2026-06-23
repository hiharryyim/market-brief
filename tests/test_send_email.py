import unittest

from scripts.send_email import markdown_to_html


class MarkdownPercentageColorTests(unittest.TestCase):
    def test_signed_percentages_are_colored(self):
        html = markdown_to_html("上涨 +1.59%，下跌 -0.65%")

        self.assertIn('<span class="pos">+1.59%</span>', html)
        self.assertIn('<span class="neg">-0.65%</span>', html)

    def test_chinese_direction_percentages_are_colored(self):
        html = markdown_to_html(
            "上证综指涨 1.59%，恒指跌 0.65%，小鹏上涨0.10%，理想下跌2.88%。"
        )

        self.assertIn('<span class="pos">涨 1.59%</span>', html)
        self.assertIn('<span class="neg">跌 0.65%</span>', html)
        self.assertIn('<span class="pos">上涨0.10%</span>', html)
        self.assertIn('<span class="neg">下跌2.88%</span>', html)


if __name__ == "__main__":
    unittest.main()
