// Диаграммы на чистом SVG: кольцо, полосы, столбики динамики.

import { el } from "../ui.js";

const NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(NS, tag);
  Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
  return node;
}

/** Кольцевая диаграмма: [{label, value, color}] */
export function donut(items, { size = 170, thickness = 20, centerValue, centerLabel } = {}) {
  const wrap = el("div", "donut");
  wrap.style.width = `${size}px`;
  wrap.style.height = `${size}px`;
  const total = items.reduce((sum, i) => sum + i.value, 0) || 1;
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;

  const svg = svgEl("svg", { width: size, height: size, viewBox: `0 0 ${size} ${size}` });
  svg.append(svgEl("circle", {
    cx: size / 2, cy: size / 2, r: radius, fill: "none",
    stroke: "rgba(148,163,184,.12)", "stroke-width": thickness,
  }));

  let offset = 0;
  items.forEach((item, index) => {
    const length = (item.value / total) * circumference;
    const arc = svgEl("circle", {
      cx: size / 2, cy: size / 2, r: radius, fill: "none",
      stroke: item.color, "stroke-width": thickness, "stroke-linecap": "round",
      "stroke-dasharray": `${Math.max(0, length - 3)} ${circumference}`,
      "stroke-dashoffset": -offset,
    });
    arc.style.setProperty("--len", `${circumference}`);
    arc.style.animation = `ring-draw .9s var(--ease) ${index * 0.08}s both`;
    svg.append(arc);
    offset += length;
  });
  wrap.append(svg);

  if (centerValue != null) {
    const center = el("div", "center");
    center.append(el("b", null, String(centerValue)));
    if (centerLabel) center.append(el("span", null, centerLabel));
    wrap.append(center);
  }
  return wrap;
}

/** Легенда к кольцу */
export function legend(items, { suffix = "%" } = {}) {
  const box = el("div", "legend");
  items.forEach((item) => {
    const row = el("div", "legend-row");
    const dot = el("i");
    dot.style.background = item.color;
    row.append(dot, el("span", null, item.label));
    row.append(el("span", "val", item.percent != null ? `${item.percent}${suffix}` : String(item.value)));
    box.append(row);
  });
  return box;
}

/** Горизонтальная полоса прогресса */
export function bar(percent, color = "var(--indigo)") {
  const box = el("div", "bar");
  const fill = el("i");
  fill.style.width = `${Math.max(2, Math.min(100, percent))}%`;
  fill.style.background = color;
  box.append(fill);
  return box;
}

/** Столбики динамики по дням */
export function spark(values, { hotIndexes = [] } = {}) {
  const box = el("div", "spark");
  const max = Math.max(...values, 1);
  values.forEach((value, index) => {
    const column = el("span");
    column.style.height = `${Math.max(6, (value / max) * 100)}%`;
    if (hotIndexes.includes(index)) column.classList.add("hot");
    column.title = String(value);
    box.append(column);
  });
  return box;
}

/** Строка оценки по критерию: название, шкала, балл */
export function scoreRow(name, score, max = 10) {
  const row = el("div", "score-row");
  row.append(el("span", "name", name));
  const track = el("div", "score-track");
  const fill = el("i");
  const color = score >= 8 ? "var(--green)" : score >= 5 ? "var(--amber)" : "var(--red)";
  fill.style.width = `${(score / max) * 100}%`;
  fill.style.background = color;
  track.append(fill);
  const value = el("span", "val " + (score >= 8 ? "high" : score >= 5 ? "mid" : "low"), `${score}/${max}`);
  row.append(track, value);
  return row;
}
