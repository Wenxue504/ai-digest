"""rank.py 的回归测试。纯函数，不需要网络。

跑法：E:\\Python\\python.exe -m unittest discover -s 04_Project/tests -v
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from digest import rank  # noqa: E402

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=CST)


def make(title, source_id="techcrunch", hours_old=1.0, summary="这是一段足够长的摘要，用来测试排序。",
         weight=0.9, url=None):
    return {
        "id": rank.item_id(url or f"https://example.com/{title}"),
        "title": title,
        "url": url or f"https://example.com/{title}",
        "summary": summary,
        "published": NOW - timedelta(hours=hours_old),
        "source": source_id,
        "source_id": source_id,
        "weight": weight,
    }


class TestItemId(unittest.TestCase):
    def test_same_url_same_id(self):
        self.assertEqual(rank.item_id("https://a.com/x"), rank.item_id("https://a.com/x"))

    def test_query_string_and_case_ignored(self):
        self.assertEqual(rank.item_id("https://A.com/x?id=1"), rank.item_id("https://a.com/x"))

    def test_different_url_different_id(self):
        self.assertNotEqual(rank.item_id("https://a.com/x"), rank.item_id("https://a.com/y"))


class TestAiFilter(unittest.TestCase):
    def test_generic_source_non_ai_dropped(self):
        item = make("Show HN: BBRouter – 8-bit computer on breadboards", source_id="hn")
        self.assertFalse(rank.is_ai_related(item))

    def test_substring_is_not_enough(self):
        # 回归：早期用 `"ai" in text`，explained / available / said 全部误命中
        item = make("Engineer explained why the server is available", source_id="hn")
        self.assertFalse(rank.is_ai_related(item))

    def test_generic_source_ai_with_word_boundary(self):
        item = make("Anthropic ships a new model", source_id="hn")
        self.assertTrue(rank.is_ai_related(item))

    def test_dedicated_source_always_passes(self):
        item = make("完全无关的标题", source_id="qbitai")
        self.assertTrue(rank.is_ai_related(item))


class TestScore(unittest.TestCase):
    def test_fresher_wins_when_all_else_equal(self):
        fresh = make("同一件事的新报道", hours_old=1)
        stale = make("另一件不相干的事", hours_old=30)
        for item in (fresh, stale):
            item["score"] = rank.score(item, NOW)
        self.assertGreater(fresh["score"], stale["score"])

    def test_ad_keyword_penalised(self):
        ad = make("限时折扣：AI 课程大促销")
        normal = make("OpenAI 发布新模型")
        self.assertLess(rank.score(ad, NOW), rank.score(normal, NOW))

    def test_empty_summary_not_penalised(self):
        # InfoQ 只给「点击查看原文」，解析层已归零；空摘要不该被当成信息量不足扣分
        empty = make("某个模型上线", hours_old=1, summary="")
        short = make("另一个模型上线", hours_old=1, summary="很短的摘要")
        self.assertGreater(rank.score(empty, NOW), rank.score(short, NOW))


class TestClassify(unittest.TestCase):
    def test_capital(self):
        self.assertEqual(rank.classify(make("某公司完成 3 亿元融资")), "资本")

    def test_policy(self):
        self.assertEqual(rank.classify(make("法院裁定该模型侵权")), "政策")

    def test_hardware(self):
        self.assertEqual(rank.classify(make("新一代 GPU 芯片量产")), "硬件")

    def test_fallback_is_product(self):
        self.assertEqual(rank.classify(make("一款新应用上线")), "产品")


class TestDedupe(unittest.TestCase):
    def test_same_title_keeps_higher_weight(self):
        low = make("OpenAI releases a new model today", weight=0.5,
                   url="https://low.com/a")
        high = make("OpenAI releases a new model today!", weight=1.0,
                    url="https://high.com/b")
        kept = rank.dedupe([low, high])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["weight"], 1.0)

    def test_different_titles_both_kept(self):
        a = make("OpenAI 发布新模型")
        b = make("谷歌开源新的视频模型")
        self.assertEqual(len(rank.dedupe([a, b])), 2)


class TestRank(unittest.TestCase):
    def test_old_items_dropped(self):
        pool, dropped = rank.rank([make("三天前的旧闻", hours_old=72)], NOW, 15)
        self.assertEqual(pool, [])
        self.assertEqual(dropped, 1)

    def test_limit_respected(self):
        # 标题必须真的不同——只差一个字的标题会被去重合并，那是预期行为
        titles = ["OpenAI 发布新模型", "谷歌开源视频模型", "英伟达芯片出货",
                  "某公司完成融资", "监管出台新规", "论文刷新基准",
                  "苹果上线新功能", "微软调整订阅", "Meta 开源权重",
                  "亚马逊发布芯片", "百度升级搜索", "阿里开源模型",
                  "腾讯云推出服务", "字节跳动投资", "xAI 数据中心被诉",
                  "DeepSeek 更新版本", "Mistral 融资", "Claude 取消限制",
                  "Qwen 登顶榜单", "Anthropic 被植入后门"]
        items = [make(t, url=f"https://e.com/{i}") for i, t in enumerate(titles)]
        pool, _ = rank.rank(items, NOW, 15)
        self.assertEqual(len(pool), 15)

    def test_sorted_desc(self):
        items = [make(f"消息{i}", hours_old=i + 1, url=f"https://e.com/{i}") for i in range(5)]
        pool, _ = rank.rank(items, NOW, 15)
        scores = [item["score"] for item in pool]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
