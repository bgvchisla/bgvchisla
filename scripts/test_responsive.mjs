import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { chromium } from "playwright";

const SITE_URL = process.env.SITE_URL || "https://bgvchisla.com/";
const ARTICLE_INCLUDED_IN_CHECKOUT = existsSync(new URL("../analizi/budget-2027/index.html", import.meta.url));
const VIEWPORTS = [
  { name: "mobile-390x844", width: 390, height: 844, mobile: true, navColumns: 2 },
  { name: "mobile-360x800", width: 360, height: 800, mobile: true, navColumns: 2 },
  { name: "tablet-768x1024", width: 768, height: 1024, mobile: false, navColumns: 4 },
  { name: "desktop-1440x900", width: 1440, height: 900, mobile: false, navColumns: 5 },
];

const browser = await chromium.launch({ headless: true, args: ["--no-sandbox"] });
try {
  for (const viewport of VIEWPORTS) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: 1,
      isMobile: viewport.mobile,
      hasTouch: viewport.mobile,
    });
    const page = await context.newPage();
    const pageErrors = [];
    page.on("pageerror", error => pageErrors.push(error.message));

    const response = await page.goto(SITE_URL, { waitUntil: "domcontentloaded", timeout: 45000 });
    assert.ok(response && response.ok(), viewport.name + ": homepage HTTP response failed");
    await page.waitForSelector("#site-content nav#nav button[data-i='15']", { state: "attached", timeout: 20000 });
    await page.waitForFunction(() => {
      const counter = document.querySelector("#debt");
      return !!counter && /^€/.test((counter.textContent || "").trim());
    }, null, { timeout: 15000 });
    await page.waitForTimeout(250);

    const metrics = await page.evaluate(() => {
      const get = selector => document.querySelector(selector);
      const style = selector => {
        const element = get(selector);
        return element ? getComputedStyle(element) : null;
      };
      const rect = selector => {
        const element = get(selector);
        if (!element) return null;
        const r = element.getBoundingClientRect();
        return { x:r.x, y:r.y, width:r.width, height:r.height, right:r.right, bottom:r.bottom };
      };
      const css = get('link[href*="design-system.css"]');
      return {
        innerWidth: window.innerWidth,
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        navColumns: style("#site-content nav#nav")?.gridTemplateColumns.split(" ").length ?? 0,
        navButtonCount: get("#site-content nav#nav")?.querySelectorAll("button[data-i]").length ?? 0,
        navVisibleButtonCount: Array.from(get("#site-content nav#nav")?.querySelectorAll("button[data-i]") ?? [])
          .filter(button => getComputedStyle(button).display !== "none").length,
        newsNavButtonDisplay: style('#site-content nav#nav button[data-i="15"]')?.display ?? null,
        longNavLabels: ["Фискални данни", "Кредити и банки"].map(label => {
          const button = Array.from(get("#site-content nav#nav")?.querySelectorAll("button[data-i]") ?? [])
            .find(item => item.querySelector(".nav-title")?.textContent?.trim() === label);
          const title = button?.querySelector(".nav-title");
          return {
            label,
            text: title?.textContent?.trim() ?? "",
            clientWidth: title?.clientWidth ?? 0,
            scrollWidth: title?.scrollWidth ?? 0,
            whiteSpace: title ? getComputedStyle(title).whiteSpace : "",
          };
        }),
        sideNewsDisplay: style(".news-side")?.display ?? null,
        headingDirection: style(".page-heading-row")?.flexDirection ?? null,
        headingRect: rect(".page-heading"),
        headingRowRect: rect(".page-heading-row"),
        ctaRect: rect(".analysis-hero-cta"),
        headingGap: rect(".analysis-hero-cta") && rect(".page-heading")
          ? rect(".analysis-hero-cta").y - rect(".page-heading").bottom : null,
        cssLoaded: !!css?.sheet,
        debtText: get("#debt")?.textContent?.trim() ?? "",
        debtWhiteSpace: style("#debt")?.whiteSpace ?? null,
        debtFontSize: Number.parseFloat(style("#debt")?.fontSize ?? "0"),
        debtClientWidth: get("#debt")?.clientWidth ?? 0,
        debtScrollWidth: get("#debt")?.scrollWidth ?? 0,
        debtTitleFontSize: Number.parseFloat(style(".hero > small")?.fontSize ?? "0"),
        debtMetricsFontSize: Number.parseFloat(style(".hero .r")?.fontSize ?? "0"),
        newsLeadStats: ["news-left-list", "news-right-list"].map(id => {
          const root = get("#" + id);
          if (!root) return { id, dividerPresent:false, leadCount:0, publisherCounts:{} };
          const children = Array.from(root.children);
          const dividerIndex = children.findIndex(element => element.classList.contains("news-more-divider"));
          const leadChildren = children.slice(0, dividerIndex >= 0 ? dividerIndex : children.length)
            .filter(element => element.matches("article.news-item"));
          const publisherCounts = {};
          leadChildren.forEach(element => {
            const publisher = element.dataset.publisher || "unknown";
            publisherCounts[publisher] = (publisherCounts[publisher] || 0) + 1;
          });
          return {
            id,
            dividerPresent: dividerIndex >= 0,
            leadCount: leadChildren.length,
            publisherCounts,
          };
        }),
      };
    });

    assert.equal(metrics.innerWidth, viewport.width, viewport.name + ": innerWidth mismatch");
    assert.equal(metrics.clientWidth, viewport.width, viewport.name + ": clientWidth mismatch");
    assert.ok(metrics.scrollWidth <= metrics.clientWidth + 1,
      viewport.name + ": horizontal overflow (" + metrics.scrollWidth + " > " + metrics.clientWidth + ")");
    assert.equal(metrics.navButtonCount, 16, viewport.name + ": expected 16 navigation buttons");
    assert.equal(metrics.navVisibleButtonCount, viewport.width >= 640 ? 15 : 16,
      viewport.name + ": unexpected number of visible navigation buttons");
    if (viewport.width >= 640) {
      assert.equal(metrics.newsNavButtonDisplay, "none",
        viewport.name + ": News navigation button must be hidden on desktop");
    } else {
      assert.notEqual(metrics.newsNavButtonDisplay, "none",
        viewport.name + ": News navigation button must remain available below desktop width");
    }
    for (const label of metrics.longNavLabels) {
      assert.equal(label.text, label.label, viewport.name + ": navigation label text changed");
      assert.ok(label.clientWidth > 0, viewport.name + ": " + label.label + " has no visible text width");
      assert.ok(label.scrollWidth <= label.clientWidth + 1,
        viewport.name + ": " + label.label + " is clipped instead of wrapping");
    }
    assert.equal(metrics.navColumns, viewport.navColumns,
      viewport.name + ": unexpected navigation grid column count");
    assert.ok(metrics.cssLoaded, viewport.name + ": design-system.css failed to load");
    assert.equal(metrics.debtWhiteSpace, "nowrap",
      viewport.name + ": debt counter must stay on one line");
    assert.ok(metrics.debtFontSize >= 18,
      viewport.name + ": debt counter font is too small (" + metrics.debtFontSize + "px)");
    assert.ok(metrics.debtClientWidth > 0 && metrics.debtScrollWidth <= metrics.debtClientWidth + 1,
      viewport.name + ": debt counter content overflows its line");
    assert.ok(metrics.debtTitleFontSize >= 15,
      viewport.name + ": debt title is too small (" + metrics.debtTitleFontSize + "px)");
    assert.ok(metrics.debtMetricsFontSize >= 14,
      viewport.name + ": debt supporting metrics are too small (" + metrics.debtMetricsFontSize + "px)");
    for (const section of metrics.newsLeadStats) {
      assert.ok(section.dividerPresent,
        viewport.name + ": " + section.id + " must visibly separate additional headlines");
      assert.ok(section.leadCount > 0 && section.leadCount <= 10,
        viewport.name + ": " + section.id + " has an invalid lead-headline count");
      for (const [publisher, count] of Object.entries(section.publisherCounts)) {
        assert.ok(count <= 2,
          viewport.name + ": " + section.id + " has more than two lead headlines from " + publisher);
      }
    }

    if (viewport.mobile) {
      assert.equal(metrics.sideNewsDisplay, "none", viewport.name + ": desktop news sidebars should be hidden");
      assert.equal(metrics.headingDirection, "column", viewport.name + ": title/CTA should stack");
      assert.ok(metrics.headingRect && metrics.headingRowRect && metrics.ctaRect);
      assert.ok(metrics.ctaRect.width >= metrics.headingRowRect.width - 1,
        viewport.name + ": analysis CTA is not full-width");
      assert.ok(metrics.ctaRect.y >= metrics.headingRect.bottom - 1,
        viewport.name + ": analysis CTA is not below the heading");
      assert.ok(metrics.headingRect.height <= 110,
        viewport.name + ": mobile heading retained an oversized flex height");
      assert.ok(metrics.headingGap >= 0 && metrics.headingGap <= 24,
        viewport.name + ": excessive vertical gap between heading and analysis CTA (" + metrics.headingGap + "px)");
      const ariaState = await page.locator("#site-content nav#nav button[data-i]").evaluateAll(buttons =>
        buttons.every(button => {
          const pressed = button.getAttribute("aria-pressed");
          const controls = button.getAttribute("aria-controls");
          return (pressed === "true" || pressed === "false") &&
            !!controls && !!document.getElementById(controls);
        })
      );
      assert.ok(ariaState, viewport.name + ": invalid nav ARIA or missing target section");
    } else if (viewport.width >= 1200) {
      assert.notEqual(metrics.sideNewsDisplay, "none", viewport.name + ": desktop news sidebars should be visible");
      assert.equal(metrics.headingDirection, "row", viewport.name + ": title/CTA should be side-by-side");
    } else {
      assert.equal(metrics.sideNewsDisplay, "none", viewport.name + ": tablet news sidebars should be hidden");
    }

    if (viewport.name === "mobile-390x844") {
      for (let index = 0; index < 16; index += 1) {
        const nav = page.locator("#site-content nav#nav");
        if (await nav.evaluate(element => element.classList.contains("mobile-collapsed"))) {
          await page.locator("#mobile-nav-toggle").click();
        }
        await page.locator("#site-content nav#nav button[data-i=\"" + index + "\"]").click();
        await page.waitForFunction(i => {
          const section = document.getElementById("s" + i);
          return !!section && section.classList.contains("on");
        }, index, { timeout: 5000 });
      }
      await page.waitForFunction(
        () => document.querySelectorAll("#news-mobile-bg .news-item").length > 0,
        null,
        { timeout: 10000 }
      );
      assert.ok(await page.locator("#news-mobile").isVisible(),
        "390px: mobile news panel did not become visible after selecting News");
    }

    let articleMetrics = { skipped: true, reason: "Article not included in this checkout." };
    if (ARTICLE_INCLUDED_IN_CHECKOUT) {
      const articleUrl = new URL("analizi/budget-2027/", SITE_URL).toString();
      const articleResponse = await page.goto(articleUrl, { waitUntil: "domcontentloaded", timeout: 20000 });
      assert.ok(articleResponse && articleResponse.ok(), viewport.name + ": article page did not load");
      articleMetrics = await page.evaluate(() => ({
        innerWidth: window.innerWidth,
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        titleVisible: !!document.querySelector("article h1") || !!document.querySelector("h1"),
        sourceCount: document.querySelectorAll(".source-list li").length,
        articleWidth: document.querySelector("article")?.getBoundingClientRect().width ?? 0,
      }));
      assert.equal(articleMetrics.clientWidth, viewport.width,
        viewport.name + ": article viewport width mismatch");
      assert.ok(articleMetrics.scrollWidth <= articleMetrics.clientWidth + 1,
        viewport.name + ": article has horizontal overflow");
      assert.ok(articleMetrics.titleVisible, viewport.name + ": article title is missing");
      assert.ok(articleMetrics.sourceCount >= 10, viewport.name + ": article source list is incomplete");
    }

    assert.equal(pageErrors.length, 0,
      viewport.name + ": uncaught browser errors: " + pageErrors.join("; "));
    console.log(JSON.stringify({
      viewport: viewport.name,
      measured: {
        innerWidth: metrics.innerWidth,
        clientWidth: metrics.clientWidth,
        scrollWidth: metrics.scrollWidth,
      },
      navColumns: metrics.navColumns,
      sidebarDisplay: metrics.sideNewsDisplay,
      headingDirection: metrics.headingDirection,
      ctaRect: metrics.ctaRect,
      cssLoaded: metrics.cssLoaded,
      navButtons: metrics.navButtonCount,
      newsLeadStats: metrics.newsLeadStats,
      article: articleMetrics,
      pageErrors,
    }));
    await context.close();
  }
} finally {
  await browser.close();
}
