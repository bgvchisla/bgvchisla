#!/usr/bin/env python3
"""Regression tests for chronological news ordering in the collector and homepage."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import update_news


class NewsOrderingTests(unittest.TestCase):
    def test_selected_items_are_displayed_newest_first(self):
        items = [
            {"title": "Older but important", "published": "2026-11-21T14:58:00+00:00", "priority_score": 90},
            {"title": "Newest", "published": "2026-11-22T07:50:54+00:00", "priority_score": 0},
            {"title": "Middle", "published": "2026-11-22T07:20:00+00:00", "priority_score": 45},
        ]
        result = update_news.select_news_items(items, limit=3)
        self.assertEqual([item["title"] for item in result], ["Newest", "Middle", "Older but important"])

    def test_editorial_relevance_still_controls_which_items_are_selected(self):
        items = [
            {"title": "Older high relevance", "published": "2026-11-21T14:00:00+00:00", "priority_score": 100},
            {"title": "Newer low relevance", "published": "2026-11-22T07:50:00+00:00", "priority_score": 1},
        ]
        result = update_news.select_news_items(items, limit=1)
        self.assertEqual([item["title"] for item in result], ["Older high relevance"])

    def test_offsets_are_normalized_to_utc_before_ordering(self):
        items = [
            {"title": "06:30 UTC", "published": "2026-11-22T08:30:00+02:00", "priority_score": 10},
            {"title": "07:00 UTC", "published": "2026-11-22T07:00:00+00:00", "priority_score": 10},
        ]
        result = update_news.select_news_items(items, limit=2)
        self.assertEqual([item["title"] for item in result], ["07:00 UTC", "06:30 UTC"])

    def test_missing_or_invalid_timestamps_are_placed_last(self):
        items = [
            {"title": "Missing date", "published": None, "priority_score": 100},
            {"title": "Valid date", "published": "2026-11-22T07:00:00+00:00", "priority_score": 1},
            {"title": "Invalid date", "published": "not-a-date", "priority_score": 80},
        ]
        result = update_news.select_news_items(items, limit=3)
        self.assertEqual(result[0]["title"], "Valid date")
        self.assertEqual({item["title"] for item in result[1:]}, {"Missing date", "Invalid date"})

    def test_non_positive_limit_returns_no_items(self):
        self.assertEqual(update_news.select_news_items([{"priority_score": 1}], limit=0), [])


class HomepageOrderingTests(unittest.TestCase):
    def test_news_renderer_uses_chronological_order_not_priority(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("function sortNewsChronologically(items){", homepage)
        self.assertIn("items=sortNewsChronologically(items);", homepage)
        self.assertNotIn("sortNewsByEditorialPriority", homepage)
        self.assertIn("var leadItem = items.reduce(function(best,item){", homepage)
        self.assertIn('article.className = leadItem && item===leadItem.item ? "news-item news-lead" : "news-item";', homepage)
        self.assertIn(".news-panel .news-item.news-lead:before", homepage)
        self.assertNotIn(".news-panel .news-item:first-child:before", homepage)


if __name__ == "__main__":
    unittest.main(verbosity=2)
