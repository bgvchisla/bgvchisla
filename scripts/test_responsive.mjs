import assert from "node:assert/strict";
import { chromium } from "playwright";

const SITE_URL = "https://bgvchisla.com/";
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
    await page.waitForSelector("#site-content nav#nav button[data-i='15']", { timeout: 20000 });
    await page.waitForTimeout(500);

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
        sideNewsDisplay: style(".news-side")?.display ?? null,
        headingDirection: style(".page-heading-row")?.flexDirection ?? null,
        headingRect: rect(".page-heading"),
        headingRowRect: rect(".page-heading-row"),
        ctaRect: rect(".analysis-hero-cta"),
        headingGap: rect(".analysis-hero-cta") && rect(".page-heading")
          ? rect(".analysis-hero-cta").y - rect(".page-heading").bottom : null,
        cssLoaded: !!css?.sheet,
      };
    });

    assert.equal(metrics.innerWidth, viewport.width, viewport.name + ": innerWidth mismatch");
    assert.equal(metrics.clientWidth, viewport.width, viewport.name + ": clientWidth mismatch");
    assert.ok(metrics.scrollWidth <= metrics.clientWidth + 1,
      viewport.name + ": horizontal overflow (" + metrics.scrollWidth + " > " + metrics.clientWidth + ")");
    assert.equal(metrics.navButtonCount, 16, viewport.name + ": expected 16 navigation buttons");
    assert.equal(metrics.navColumns, viewport.navColumns,
      viewport.name + ": unexpected navigation grid column count");
    assert.ok(metrics.cssLoaded, viewport.name + ": design-system.css failed to load");

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
      pageErrors,
    }));
    await context.close();
  }
} finally {
  await browser.close();
}
