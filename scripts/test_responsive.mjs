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
          if (!root) return { id, dividerPresent:false, leadCount:0, publisherCounts:{}, leadAgeHours:null, freshCandidateCount:0 };
          const articles = Array.from(root.querySelectorAll("article.news-item"));
          const lead = root.querySelector("article.news-lead");
          const now = Date.now();
          const freshCandidates = articles.filter(element => {
            const published = Date.parse(element.dataset.published || "");
            const ageHours = (now - published) / 3600000;
            return Number.isFinite(published) && ageHours >= -24 && ageHours <= 18;
          });
          const leadPublished = lead ? Date.parse(lead.dataset.published || "") : NaN;
          const leadAgeHours = Number.isFinite(leadPublished) ? (now - leadPublished) / 3600000 : null;
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
            leadAgeHours,
            freshCandidateCount: freshCandidates.length,
            freshnessNotePresent: !!root.querySelector(".news-stale-note"),
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
      if (section.freshCandidateCount > 0) {
        assert.ok(section.leadAgeHours !== null && section.leadAgeHours >= -24 && section.leadAgeHours <= 18,
          viewport.name + ": lead story must be published within the last 18 hours when fresh candidates exist");
        assert.equal(section.freshnessNotePresent, false,
          viewport.name + ": fresh lead candidates exist but stale-news notice was rendered");
      } else {
        assert.equal(section.leadAgeHours, null,
          viewport.name + ": an old story must not be styled as a fresh lead");
        assert.equal(section.freshnessNotePresent, true,
          viewport.name + ": missing notice when there is no story within the 18-hour lead window");
      }
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

    const inflationUrl = new URL("tseni-i-inflatsia/", SITE_URL).toString();
    const inflationResponse = await page.goto(inflationUrl, { waitUntil: "domcontentloaded", timeout: 20000 });
    assert.ok(inflationResponse && inflationResponse.ok(), viewport.name + ": inflation resource did not load");
    await page.waitForSelector("#annual-chart svg", { timeout: 10000 });
    await page.waitForFunction(() => {
      const rows = document.querySelectorAll("#history-table tbody tr");
      const categories = document.querySelectorAll("#category-table tbody tr");
      return rows.length >= 10 && categories.length >= 10 &&
        document.querySelector("#cpi-annual")?.textContent?.trim() === "6,0%";
    }, null, { timeout: 10000 });
    const inflationMetrics = await page.evaluate(() => ({
      innerWidth: window.innerWidth,
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      title: document.querySelector("h1")?.textContent?.trim() ?? "",
      cpiAnnual: document.querySelector("#cpi-annual")?.textContent?.trim() ?? "",
      hicpAnnual: document.querySelector("#hicp-annual")?.textContent?.trim() ?? "",
      annualChart: !!document.querySelector("#annual-chart svg"),
      monthlyChart: !!document.querySelector("#monthly-chart svg"),
      historyRows: document.querySelectorAll("#history-table tbody tr").length,
      categoryRows: document.querySelectorAll("#category-table tbody tr").length,
      sources: document.querySelectorAll("#source-list a").length,
    }));
    assert.equal(inflationMetrics.clientWidth, viewport.width,
      viewport.name + ": inflation viewport width mismatch");
    assert.ok(inflationMetrics.scrollWidth <= inflationMetrics.clientWidth + 1,
      viewport.name + ": inflation page has horizontal overflow");
    assert.ok(inflationMetrics.title.includes("Цени и инфлация"),
      viewport.name + ": inflation page title is missing");
    assert.equal(inflationMetrics.cpiAnnual, "6,0%",
      viewport.name + ": official CPI annual value did not load");
    assert.equal(inflationMetrics.hicpAnnual, "5,9%",
      viewport.name + ": official HICP annual value did not load");
    assert.ok(inflationMetrics.annualChart && inflationMetrics.monthlyChart,
      viewport.name + ": inflation charts failed to render");
    assert.ok(inflationMetrics.historyRows >= 10 && inflationMetrics.categoryRows >= 10,
      viewport.name + ": inflation tables are incomplete");
    assert.ok(inflationMetrics.sources >= 5,
      viewport.name + ": primary-source list is incomplete");

    const debtUrl = new URL("dalg-i-byudzhet/", SITE_URL).toString();
    const debtResponse = await page.goto(debtUrl, { waitUntil: "domcontentloaded", timeout: 20000 });
    assert.ok(debtResponse && debtResponse.ok(), viewport.name + ": debt and budget resource did not load");
    await page.waitForSelector("#state-debt-gdp-forecast-chart svg", { timeout: 10000 });
    await page.waitForFunction(() => {
      const reportedRows = document.querySelectorAll("#maastricht-table tbody tr");
      const forecastRows = document.querySelectorAll("#state-debt-forecast-table tbody tr");
      const nsiRows = document.querySelectorAll("#monthly-fiscal-table tbody tr");
      return reportedRows.length >= 4 && forecastRows.length >= 5 && nsiRows.length >= 3 &&
        document.querySelector("#state-debt")?.textContent?.includes("35,255");
    }, null, { timeout: 10000 });
    const debtMetrics = await page.evaluate(() => ({
      innerWidth: window.innerWidth,
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      title: document.querySelector("h1")?.textContent?.trim() ?? "",
      stateDebt: document.querySelector("#state-debt")?.textContent?.trim() ?? "",
      octoberDeficit: document.querySelector("#oct-deficit")?.textContent?.trim() ?? "",
      kfpChart: !!document.querySelector("#kfp-chart svg"),
      monthlyBalanceChart: !!document.querySelector("#monthly-balance-chart svg"),
      monthlyFlowsChart: !!document.querySelector("#monthly-flows-chart svg"),
      maastrichtDebtChart: !!document.querySelector("#maastricht-debt-chart svg"),
      debtForecastChart: !!document.querySelector("#state-debt-forecast-chart svg"),
      debtGdpChart: !!document.querySelector("#state-debt-gdp-forecast-chart svg"),
      kfpForecastChart: !!document.querySelector("#kfp-forecast-chart svg"),
      generalGovernmentForecastChart: !!document.querySelector("#general-government-forecast-chart svg"),
      kfpRows: document.querySelectorAll("#kfp-table tr").length,
      monthlyRows: document.querySelectorAll("#monthly-fiscal-table tbody tr").length,
      maastrichtRows: document.querySelectorAll("#maastricht-table tbody tr").length,
      forecastRows: document.querySelectorAll("#state-debt-forecast-table tbody tr").length,
      sources: document.querySelectorAll("#source-list a").length,
    }));
    assert.equal(debtMetrics.clientWidth, viewport.width,
      viewport.name + ": debt and budget viewport width mismatch");
    assert.ok(debtMetrics.scrollWidth <= debtMetrics.clientWidth + 1,
      viewport.name + ": debt and budget page has horizontal overflow");
    assert.ok(debtMetrics.title.includes("Дълг и бюджет"),
      viewport.name + ": debt and budget page title is missing");
    assert.ok(debtMetrics.stateDebt.includes("35,255"),
      viewport.name + ": official state debt value did not load");
    assert.ok(debtMetrics.octoberDeficit.includes("5,200"),
      viewport.name + ": preliminary October KFP deficit did not load");
    for (const chart of [
      "kfpChart", "monthlyBalanceChart", "monthlyFlowsChart", "maastrichtDebtChart",
      "debtForecastChart", "debtGdpChart", "kfpForecastChart", "generalGovernmentForecastChart"
    ]) {
      assert.ok(debtMetrics[chart], viewport.name + ": missing rendered debt chart " + chart);
    }
    assert.ok(debtMetrics.kfpRows >= 6 && debtMetrics.monthlyRows >= 3,
      viewport.name + ": debt or monthly fiscal table is incomplete");
    assert.ok(debtMetrics.maastrichtRows >= 4 && debtMetrics.forecastRows >= 5,
      viewport.name + ": debt history or forecast table is incomplete");
    assert.ok(debtMetrics.sources >= 7,
      viewport.name + ": primary-source list is incomplete");

    const bankUrl = new URL("banki/", SITE_URL).toString();
    const bankResponse = await page.goto(bankUrl, { waitUntil: "domcontentloaded", timeout: 20000 });
    assert.ok(bankResponse && bankResponse.ok(), viewport.name + ": banking resource did not load");
    await page.waitForSelector("#sector-loans-chart svg", { timeout: 10000 });
    await page.waitForSelector("#household-loans-chart svg", { timeout: 10000 });
    await page.waitForFunction(() => {
      const rows = document.querySelectorAll("#sector-table tbody tr");
      const rates = document.querySelectorAll("#interest-table tbody tr");
      return rows.length >= 4 && rates.length >= 6 &&
        document.querySelector("#assets")?.textContent?.includes("124,4") &&
        document.querySelector("#npl-ratio")?.textContent?.trim() === "2,59%";
    }, null, { timeout: 10000 });
    const bankMetrics = await page.evaluate(() => ({
      innerWidth: window.innerWidth,
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      title: document.querySelector("h1")?.textContent?.trim() ?? "",
      assets: document.querySelector("#assets")?.textContent?.trim() ?? "",
      loans: document.querySelector("#loans")?.textContent?.trim() ?? "",
      deposits: document.querySelector("#deposits")?.textContent?.trim() ?? "",
      nplRatio: document.querySelector("#npl-ratio")?.textContent?.trim() ?? "",
      sectorLoansChart: !!document.querySelector("#sector-loans-chart svg"),
      sectorDepositsChart: !!document.querySelector("#sector-deposits-chart svg"),
      householdLoansChart: !!document.querySelector("#household-loans-chart svg"),
      loanRatesChart: !!document.querySelector("#loan-rates-chart svg"),
      depositRatesChart: !!document.querySelector("#deposit-rates-chart svg"),
      sectorRows: document.querySelectorAll("#sector-table tbody tr").length,
      interestRows: document.querySelectorAll("#interest-table tbody tr").length,
      sources: document.querySelectorAll("#source-list a").length,
    }));
    assert.equal(bankMetrics.clientWidth, viewport.width,
      viewport.name + ": banking viewport width mismatch");
    assert.ok(bankMetrics.scrollWidth <= bankMetrics.clientWidth + 1,
      viewport.name + ": banking page has horizontal overflow");
    assert.ok(bankMetrics.title.includes("Банки"),
      viewport.name + ": banking page title is missing");
    assert.ok(bankMetrics.assets.includes("124,4"),
      viewport.name + ": banking assets value did not load");
    assert.ok(bankMetrics.loans.includes("67,693"),
      viewport.name + ": monetary credit aggregate did not load");
    assert.ok(bankMetrics.deposits.includes("87,590"),
      viewport.name + ": monetary deposit aggregate did not load");
    assert.equal(bankMetrics.nplRatio, "2,59%",
      viewport.name + ": supervisory NPL ratio did not load");
    for (const chart of [
      "sectorLoansChart", "sectorDepositsChart", "householdLoansChart",
      "loanRatesChart", "depositRatesChart"
    ]) {
      assert.ok(bankMetrics[chart], viewport.name + ": missing rendered banking chart " + chart);
    }
    assert.ok(bankMetrics.sectorRows >= 4 && bankMetrics.interestRows >= 6,
      viewport.name + ": banking data tables are incomplete");
    assert.ok(bankMetrics.sources >= 8,
      viewport.name + ": primary-source list is incomplete");

    const labourUrl = new URL("pazar-na-truda/", SITE_URL).toString();
    const labourResponse = await page.goto(labourUrl, { waitUntil: "domcontentloaded", timeout: 20000 });
    assert.ok(labourResponse && labourResponse.ok(), viewport.name + ": labour-market resource did not load");
    await page.waitForSelector("#unemployment-chart svg", { timeout: 10000 });
    await page.waitForSelector("#wage-september-table tbody tr", { timeout: 10000 });
    await page.waitForFunction(() => {
      const wageRows = document.querySelectorAll("#wage-activity-table tbody tr");
      const septemberRows = document.querySelectorAll("#wage-september-table tbody tr");
      return wageRows.length >= 6 && septemberRows.length >= 18 &&
        document.querySelector("#survey-unemployment")?.textContent?.trim() === "3,1%" &&
        document.querySelector("#registered-unemployment")?.textContent?.trim() === "5,60%";
    }, null, { timeout: 10000 });
    const labourMetrics = await page.evaluate(() => ({
      innerWidth: window.innerWidth,
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      title: document.querySelector("h1")?.textContent?.trim() ?? "",
      surveyUnemployment: document.querySelector("#survey-unemployment")?.textContent?.trim() ?? "",
      employmentRate: document.querySelector("#employment-rate")?.textContent?.trim() ?? "",
      averageWage: (document.querySelector("#average-wage")?.textContent ?? "").replace(/\s+/g, " ").trim(),
      registeredUnemployment: document.querySelector("#registered-unemployment")?.textContent?.trim() ?? "",
      activeVacancies: document.querySelector("#active-vacancies")?.textContent?.trim() ?? "",
      unemploymentChart: !!document.querySelector("#unemployment-chart svg"),
      employmentChart: !!document.querySelector("#employment-chart svg"),
      sectorChart: !!document.querySelector("#employment-sector-chart svg"),
      monthlyWageChart: !!document.querySelector("#wage-monthly-chart svg"),
      highWageChart: !!document.querySelector("#wage-high-chart svg"),
      lowWageChart: !!document.querySelector("#wage-low-chart svg"),
      payrollChart: !!document.querySelector("#payroll-employees-chart svg"),
      productivityChart: !!document.querySelector("#productivity-sector-chart svg"),
      productivityPerEmployed: (document.querySelector("#productivity-per-employed")?.textContent ?? "").replace(/\s+/g, " ").trim(),
      productivityGrowth: document.querySelector("#productivity-growth")?.textContent?.trim() ?? "",
      wageRows: document.querySelectorAll("#wage-activity-table tbody tr").length,
      septemberRows: document.querySelectorAll("#wage-september-table tbody tr").length,
      sources: document.querySelectorAll("#source-list a").length,
    }));
    assert.equal(labourMetrics.clientWidth, viewport.width,
      viewport.name + ": labour-market viewport width mismatch");
    assert.ok(labourMetrics.scrollWidth <= labourMetrics.clientWidth + 1,
      viewport.name + ": labour-market page has horizontal overflow");
    assert.ok(labourMetrics.title.includes("Пазар на труда"),
      viewport.name + ": labour-market title is missing");
    assert.equal(labourMetrics.surveyUnemployment, "3,1%",
      viewport.name + ": NSI survey unemployment did not load");
    assert.equal(labourMetrics.registeredUnemployment, "5,60%",
      viewport.name + ": registered unemployment did not load");
    assert.ok(labourMetrics.employmentRate.includes("77,0"),
      viewport.name + ": employment rate did not load");
    assert.ok(labourMetrics.averageWage.includes("1 438"),
      viewport.name + ": average wage did not load");
    assert.ok(labourMetrics.productivityPerEmployed.includes("8 272,6"),
      viewport.name + ": labour productivity per employed person did not load");
    assert.equal(labourMetrics.productivityGrowth, "+3,1%",
      viewport.name + ": real labour productivity growth did not load");
    for (const chart of [
      "unemploymentChart", "employmentChart", "sectorChart", "monthlyWageChart",
      "highWageChart", "lowWageChart", "payrollChart", "productivityChart"
    ]) {
      assert.ok(labourMetrics[chart], viewport.name + ": missing rendered labour chart " + chart);
    }
    assert.ok(labourMetrics.wageRows >= 6 && labourMetrics.septemberRows >= 18,
      viewport.name + ": wage detail tables are incomplete");
    assert.ok(labourMetrics.sources >= 7,
      viewport.name + ": primary-source list is incomplete");

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
