#!/usr/bin/env python3
"""Regression tests for significance-first editorial news selection."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import update_news


NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


class EditorialScoringTests(unittest.TestCase):
    def test_strategic_national_investment_outranks_minor_regional_notice(self):
        investment = {
            "section": "bulgaria",
            "feed_id": "investor-economy",
            "source": "Investor.bg – Икономика и политика",
            "title": "Саудитска Арабия обмисля инвестиции в индустриални паркове и производство на електромобили в България",
            "summary": "Потенциални инвестиции в индустриални паркове и производство с висока добавена стойност.",
            "published": "2026-11-23T08:14:00+00:00",
        }
        regional_jobs = {
            "section": "bulgaria",
            "feed_id": "bta-bulgaria",
            "source": "БТА",
            "title": "Общо 13 свободни работни места за специалисти с висше образование обяви Бюрото по труда в Монтана",
            "summary": "Всичките свободни работни места са за лекари и медицински лаборант в болницата в Монтана.",
            "published": "2026-11-23T08:42:00+00:00",
        }
        investment_components = update_news.editorial_priority_components(investment, NOW)
        regional_components = update_news.editorial_priority_components(regional_jobs, NOW)
        self.assertGreater(investment_components["strategic_significance"], regional_components["strategic_significance"])
        self.assertGreater(investment_components["national_impact"], regional_components["national_impact"])
        self.assertGreater(investment_components["score"], regional_components["score"])

    def test_score_contains_all_six_editorial_dimensions(self):
        item = {
            "feed_id": "economic-bg",
            "title": "Инфлацията и лихвените проценти влияят върху бизнеса и домакинствата",
            "summary": "Промените в цените и кредита имат национално отражение.",
            "published": "2026-11-23T10:00:00+00:00",
        }
        components = update_news.editorial_priority_components(item, NOW)
        self.assertEqual(
            set(components) - {"score", "weights"},
            {
                "economic_significance",
                "national_impact",
                "household_business_impact",
                "strategic_significance",
                "timeliness",
                "source_reliability",
            },
        )
        self.assertEqual(sum(components["weights"].values()), 1.0)
        self.assertGreaterEqual(components["score"], 0)
        self.assertLessEqual(components["score"], 100)

    def test_fresher_article_wins_only_when_significance_is_equal(self):
        items = [
            {"title": "Older high relevance", "published": "2026-11-22T14:00:00+00:00", "priority_score": 80, "section": "bulgaria"},
            {"title": "Newer same relevance", "published": "2026-11-23T07:50:00+00:00", "priority_score": 80, "section": "bulgaria"},
            {"title": "Newest but less important", "published": "2026-11-23T09:50:00+00:00", "priority_score": 35, "section": "bulgaria"},
        ]
        result = update_news.select_news_items(items, limit=3)
        self.assertEqual(
            [item["title"] for item in result],
            ["Newer same relevance", "Older high relevance", "Newest but less important"],
        )

    def test_fresh_lead_overtakes_stale_weekly_roundup_without_removing_it(self):
        now = datetime(2026, 11, 23, 14, 15, tzinfo=timezone.utc)
        stale_weekly_roundup = {
            "section": "bulgaria",
            "publisher": "Economic.bg",
            "source": "Economic.bg",
            "title": "Седмични новини: България ще строи целия жп тунел „Деве баир“",
            "published": "2026-11-22T15:30:13+00:00",
            "priority_score": 67,
        }
        fresh_business_story = {
            "section": "bulgaria",
            "publisher": "Economic.bg",
            "source": "Economic.bg",
            "title": "Бизнесът има достъп до 81.5 млн. евро за иновации и развитие на технологии",
            "published": "2026-11-23T13:04:47+00:00",
            "priority_score": 54,
        }

        self.assertFalse(update_news.is_lead_eligible(stale_weekly_roundup, now))
        self.assertTrue(update_news.is_lead_eligible(fresh_business_story, now))
        selected = update_news.select_news_items(
            [stale_weekly_roundup, fresh_business_story],
            limit=2,
            now=now,
        )
        self.assertEqual(selected[0]["title"], fresh_business_story["title"])
        self.assertIn(stale_weekly_roundup, selected)

    def test_oldest_available_story_is_not_marked_as_fresh_lead(self):
        now = datetime(2026, 11, 23, 14, 15, tzinfo=timezone.utc)
        stale = {
            "section": "bulgaria",
            "publisher": "Economic.bg",
            "published": "2026-11-22T15:30:13+00:00",
            "priority_score": 67,
            "title": "Седмичен обзор",
        }
        self.assertFalse(update_news.is_lead_eligible(stale, now))

    def test_oldest_available_story_is_not_marked_as_fresh_lead(self):
        now = datetime(2026, 11, 23, 14, 15, tzinfo=timezone.utc)
        stale = {
            "section": "bulgaria",
            "publisher": "Economic.bg",
            "published": "2026-11-22T15:30:13+00:00",
            "priority_score": 67,
            "title": "Седмичен обзор",
        }
        self.assertFalse(update_news.is_lead_eligible(stale, now))

    def test_wall_street_and_asian_market_stories_are_classified_as_world(self):
        item = {
            "feed_id": "investor-finance",
            "section": "bulgaria",
            "title": "Сривът на Уолстрийт потопи и технологичните компании в Азия",
            "summary": "Азиатските пазари реагираха на понижението.",
        }
        self.assertEqual(update_news.classify_investor_section(item)["section"], "europe")


class PublisherDiversityTests(unittest.TestCase):
    def test_first_ten_have_at_most_two_items_per_publisher(self):
        items = []
        investor_feeds = ["investor-bg", "investor-economy", "investor-finance"]
        for i in range(12):
            feed_id = investor_feeds[i % len(investor_feeds)]
            items.append({
                "title": f"Investor headline {i}",
                "published": f"2026-11-23T{11 - (i // 2):02d}:{(i % 2) * 20:02d}:00+00:00",
                "priority_score": 100 - i,
                "feed_id": feed_id,
                "source": f"Investor.bg – {feed_id}",
                "section": "bulgaria",
            })
        other_publishers = [
            ("bta-bulgaria", "БТА"),
            ("economic-bg", "Economic.bg"),
            ("parliament-news", "Народно събрание"),
            ("bnb-news", "БНБ"),
        ]
        for index, (feed_id, source) in enumerate(other_publishers):
            for sequence in range(3):
                i = index * 3 + sequence
                items.append({
                    "title": f"{source} headline {i}",
                    "published": f"2026-11-23T{10 - (i // 2):02d}:{(i % 2) * 20:02d}:00+00:00",
                    "priority_score": 70 - i,
                    "feed_id": feed_id,
                    "source": source,
                    "section": "bulgaria",
                })

        selected = update_news.select_news_items(items, limit=20, top_window=10, max_per_publisher=2)
        first_ten_counts = {}
        for item in selected[:10]:
            publisher = item.get("publisher") or update_news.publisher_key(item)
            first_ten_counts[publisher] = first_ten_counts.get(publisher, 0) + 1
        self.assertLessEqual(first_ten_counts.get("investor.bg", 0), 2)
        self.assertEqual(len(selected), 20)

    def test_publisher_categories_are_aggregated_under_one_brand(self):
        feeds = ["investor-bg", "investor-economy", "investor-finance"]
        publishers = {
            update_news.publisher_key({"feed_id": feed, "source": feed})
            for feed in feeds
        }
        self.assertEqual(publishers, {"investor.bg"})

    def test_each_news_section_gets_its_own_diversified_top_ten(self):
        items = []
        publisher_specs = [
            ("investor-economy", "Investor.bg – Икономика и политика", 12, 100),
            ("bta-bulgaria", "БТА", 3, 70),
            ("economic-bg", "Economic.bg", 3, 60),
            ("parliament-news", "Народно събрание", 3, 50),
            ("bnb-news", "БНБ", 3, 40),
        ]
        for section in ("bulgaria", "europe"):
            for feed_id, source, count, base_score in publisher_specs:
                for i in range(count):
                    items.append({
                        "title": f"{section} {source} story {i}",
                        "published": f"2026-11-23T{11 - (i % 12):02d}:{i:02d}:00+00:00",
                        "priority_score": base_score - i,
                        "feed_id": feed_id,
                        "source": source,
                        "section": section,
                    })
        selected = update_news.select_news_items(items, limit=40)
        for section in ("bulgaria", "europe"):
            section_items = [item for item in selected if item["section"] == section]
            counts = {}
            for item in section_items[:10]:
                publisher = update_news.publisher_key(item)
                counts[publisher] = counts.get(publisher, 0) + 1
            self.assertLessEqual(counts.get("investor.bg", 0), 2)
            self.assertLessEqual(counts.get("БТА", 0), 2)


class RelatedCoverageTests(unittest.TestCase):
    def test_related_union_protests_are_grouped_but_both_sources_are_kept(self):
        blagoevgrad = {
            "section": "bulgaria",
            "feed_id": "bta-bulgaria",
            "source": "БТА",
            "title": "Социални работници в Благоевград стачкуваха предупредително с искания, свързани с правата на работещите в сферата",
            "summary": "Служители на Регионална дирекция за социално подпомагане участват в стачка, организирана от синдиката на административните служители „Подкрепа“.",
            "url": "https://example.com/news/blagoevgrad",
            "published": "2026-11-23T08:34:00+00:00",
            "priority_score": 68,
            "publisher": "БТА",
        }
        ruse = {
            "section": "bulgaria",
            "feed_id": "bta-bulgaria",
            "source": "БТА",
            "title": "Служители от Регионална дирекция Социално подпомагане излязоха на протест в Русе с искане за по-високи заплати",
            "summary": "Стачката е организирана от Конфедерацията на труда „Подкрепа“.",
            "url": "https://example.com/news/ruse",
            "published": "2026-11-23T08:14:00+00:00",
            "priority_score": 65,
            "publisher": "БТА",
        }
        grouped = update_news.deduplicate_related_events([blagoevgrad, ruse])
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["url"], blagoevgrad["url"])
        self.assertEqual(grouped[0]["related_count"], 1)
        self.assertEqual(grouped[0]["related_items"][0]["url"], ruse["url"])

    def test_unrelated_local_protests_are_not_automatically_grouped(self):
        water_protest = {
            "title": "Жители на квартал в Пловдив протестираха заради прекъснато водоснабдяване",
            "summary": "Организаторите настояват за спешно отстраняване на аварията.",
            "published": "2026-11-23T08:20:00+00:00",
        }
        wage_protest = {
            "title": "Служители на регионална дирекция протестираха за по-високи заплати",
            "summary": "Синдикатът „Подкрепа“ организира акцията.",
            "published": "2026-11-23T08:10:00+00:00",
        }
        grouped = update_news.deduplicate_related_events([water_protest, wage_protest])
        self.assertEqual(len(grouped), 2)


class HomepageOrderingTests(unittest.TestCase):
    def test_homepage_uses_an_18_hour_freshness_window_for_lead_news(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("var NEWS_LEAD_MAX_AGE_HOURS=18;", homepage)
        self.assertIn("function isFreshLeadNews(item,now){", homepage)
        self.assertIn("var freshLead=ranked.find(function(item){return isFreshLeadNews(item,Date.now())});", homepage)
        self.assertIn("var leadItem=items.length&&isFreshLeadNews(items[0],Date.now())?items[0]:null;", homepage)

    def test_homepage_orders_by_significance_then_publication_time(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("function sortNewsByEditorialPriority(items){", homepage)
        self.assertIn("items=sortNewsByEditorialPriority(items);", homepage)
        self.assertNotIn("sortNewsChronologically", homepage)
        self.assertIn("var pa=Number(a.priority_score);", homepage)
        self.assertIn("if(pb!==pa)return pb-pa;", homepage)
        self.assertIn("return tb-ta;", homepage)

    def test_homepage_enforces_publisher_diversity_in_visible_first_ten(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        function = homepage.split("function sortNewsByEditorialPriority(items){", 1)[1].split(
            "function renderNews(target,items){", 1
        )[0]
        self.assertIn("var ranked=items.slice().sort(compare);", function)
        self.assertIn("var top=[],deferred=[],publisherCounts=Object.create(null);", function)
        self.assertIn('String(item.publisher||item.source||"unknown")', function)
        self.assertIn("top.length<10&&(publisherCounts[publisher]||0)<2", function)
        self.assertIn("var result=top.concat(deferred.sort(compare));", function)
        self.assertIn("result.editorialTopCount=top.length;", function)
        self.assertIn("return result;", function)

    def test_homepage_marks_more_news_after_diverse_lead_window(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        sorting = homepage.split("function sortNewsByEditorialPriority(items){", 1)[1].split(
            "function renderNews(target,items){", 1
        )[0]
        rendering = homepage.split("function renderNews(target,items){", 1)[1]
        self.assertIn("result.editorialTopCount=top.length;", sorting)
        self.assertIn("var editorialTopCount=items.editorialTopCount;", rendering)
        self.assertIn("index===editorialTopCount", rendering)
        self.assertIn('more.className="news-more-divider";', rendering)
        self.assertIn('moreLabel.textContent="Още новини";', rendering)

    def test_homepage_renders_related_coverage_links(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("item.related_items.length", homepage)
        self.assertIn("Още отразявания: ", homepage)
        self.assertIn("relatedLink.rel=\"noopener noreferrer\"", homepage)


if __name__ == "__main__":
    unittest.main(verbosity=2)
