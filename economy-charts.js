(async function () {
  "use strict";

  const host = document.createElement("div");
  host.className = "box wide";
  host.style.marginTop = "16px";

  const overview = document.getElementById("s0");
  if (!overview) return;
  overview.appendChild(host);

  function element(tag, text, parent) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }

  element("h3", "БВП на човек — по години", host);
  const message = element("p", "Зареждане на данните…", host);
  message.className = "h";

  try {
    const response = await fetch("economy.json", { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);

    const data = await response.json();
    const series = (data.series || []).find(
      row => row.id === "gdp_per_capita_current_eur"
    );
    if (!series) throw new Error("Липсва серията.");

    const points = (series.points || [])
      .filter(p => Number.isInteger(p.year) && Number.isFinite(p.value))
      .sort((a, b) => a.year - b.year);

    if (points.length < 2) throw new Error("Недостатъчно данни.");

    message.textContent =
      "По текущи цени, евро на човек. Не е заплата или доход; " +
      "изменението не е равнозначно на реален икономически растеж.";

    const controls = element("div", undefined, host);
    controls.style.cssText =
      "display:flex;gap:8px;flex-wrap:wrap;margin:12px 0;";

    const select = element("select", undefined, controls);
    select.setAttribute("aria-label", "Период на графиката");
    select.style.cssText =
      "padding:8px;border:1px solid var(--bd);border-radius:8px;" +
      "background:var(--card);color:var(--tx);font:inherit;";

    [[10, "Последните 10 години"], [5, "Последните 5 години"],
     [0, "Всички налични години"]].forEach(([value, text]) => {
      const option = element("option", text, select);
      option.value = value;
    });

    const summary = element("p", undefined, host);
    const chart = element("div", undefined, host);
    const details = element("details", undefined, host);
    element("summary", "Таблица с годишните стойности", details);
    const tableWrap = element("div", undefined, details);
    tableWrap.className = "tw";

    const fmt = new Intl.NumberFormat("bg-BG", {
      maximumFractionDigits: 0
    });
    const pct = new Intl.NumberFormat("bg-BG", {
      maximumFractionDigits: 1
    });

    const NS = "http://www.w3.org/2000/svg";
    function svgNode(tag, attrs, parent, text) {
      const node = document.createElementNS(NS, tag);
      Object.entries(attrs).forEach(([key, value]) =>
        node.setAttribute(key, value)
      );
      if (text !== undefined) node.textContent = text;
      parent.appendChild(node);
      return node;
    }

    function draw() {
      const count = Number(select.value);
      const shown = count ? points.slice(-count) : points;
      const latest = points[points.length - 1];
      const previous = points[points.length - 2];
      const consecutive = latest.year === previous.year + 1;
      const difference = latest.value - previous.value;

      summary.textContent =
        latest.year + ": " + fmt.format(latest.value) + " евро на човек.";

      if (consecutive) {
        summary.textContent += " " +
          (difference > 0 ? "Увеличение" :
           difference < 0 ? "Намаление" : "Без промяна") +
          " спрямо " + previous.year + ": " +
          fmt.format(Math.abs(difference)) + " евро";

        if (previous.value > 0) {
          summary.textContent += " (" +
            pct.format(Math.abs(difference / previous.value * 100)) + "%)";
        }
        summary.textContent += ".";
      }

      chart.replaceChildren();
      const W = 760, H = 300;
      const left = 66, right = 16, top = 20, bottom = 44;
      const low = Math.min(0, ...shown.map(p => p.value));
      const high = Math.max(1, ...shown.map(p => p.value)) * 1.1;
      const x = year => left +
        (year - shown[0].year) /
        (shown[shown.length - 1].year - shown[0].year || 1) *
        (W - left - right);
      const y = value => top +
        (high - value) / (high - low) * (H - top - bottom);

      const svg = document.createElementNS(NS, "svg");
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label",
        "Годишен БВП на човек по текущи цени. Точните стойности са в таблицата.");
      chart.appendChild(svg);

      for (let i = 0; i <= 4; i++) {
        const value = low + (high - low) * i / 4;
        svgNode("line", {
          x1: left, x2: W - right, y1: y(value), y2: y(value),
          stroke: "var(--bd)"
        }, svg);
        svgNode("text", {
          x: left - 8, y: y(value) + 4, "text-anchor": "end"
        }, svg, fmt.format(value));
      }

      let segment = [];
      function finishSegment() {
        if (!segment.length) return;
        svgNode("polyline", {
          points: segment.join(" "),
          fill: "none", stroke: "var(--bl)", "stroke-width": 3
        }, svg);
        segment = [];
      }

      shown.forEach((p, index) => {
        if (index && p.year !== shown[index - 1].year + 1) {
          finishSegment();
        }
        segment.push(x(p.year) + "," + y(p.value));
      });
      finishSegment();

      const every = Math.max(1, Math.ceil(shown.length / 8));
      shown.forEach((p, index) => {
        const dot = svgNode("circle", {
          cx: x(p.year), cy: y(p.value), r: 4, fill: "var(--bl)"
        }, svg);
        svgNode("title", {}, dot,
          p.year + ": " + fmt.format(p.value) + " евро на човек");

        if (index % every === 0 || index === shown.length - 1) {
          svgNode("text", {
            x: x(p.year), y: H - 12, "text-anchor": "middle"
          }, svg, p.year);
        }
      });

      tableWrap.replaceChildren();
      const table = element("table", undefined, tableWrap);
      const head = element("thead", undefined, table);
      const header = element("tr", undefined, head);
      ["Година", "Евро на човек", "Флаг на източника"].forEach(text =>
        element("th", text, header)
      );
      const body = element("tbody", undefined, table);
      shown.forEach(p => {
        const row = element("tr", undefined, body);
        element("td", String(p.year), row);
        element("td", fmt.format(p.value), row);
        element("td", p.flag || "—", row);
      });
    }

    select.addEventListener("change", draw);
    draw();

    const source = element("p", undefined, host);
    source.className = "src";
    element("span", "Източник: ", source);
    const link = element("a", "Евростат · " + series.dataset, source);
    const url = new URL(series.source_url);
    if (url.protocol === "https:" &&
        url.hostname === "ec.europa.eu") {
      link.href = url.href;
      link.target = "_blank";
      link.rel = "noopener";
    }

    if (series.updated_at) {
      const date = new Date(series.updated_at);
      if (!Number.isNaN(date.getTime())) {
        element("span",
          " · Извлечено: " + date.toLocaleString("bg-BG"), source);
      }
    }
  } catch (error) {
    message.textContent =
      "Годишните данни не могат да бъдат заредени. " +
      "Липсващите стойности не се заменят с нула.";
    console.error("Графика на икономическите данни:", error);
  }
})();
