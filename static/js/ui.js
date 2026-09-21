// Мелкие помощники интерфейса: элементы, иконки, форматирование, тосты.

export const SVG_NS = "http://www.w3.org/2000/svg";

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

export function icon(name, cls) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "i" + (cls ? " " + cls : ""));
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}

export function withIcon(tag, cls, name, text) {
  const node = el(tag, cls);
  node.append(icon(name), document.createTextNode(text));
  return node;
}

export function tag(text, iconName, cls) {
  return iconName ? withIcon("span", "tag" + (cls ? " " + cls : ""), iconName, text)
                  : el("span", "tag" + (cls ? " " + cls : ""), text);
}

/** Аватар сотрудника: фотография, если она есть, иначе инициал на цветном фоне. */
export function avatar(user, size = "") {
  const name = typeof user === "string" ? user : (user?.name || user?.user_name);
  const file = typeof user === "object" ? (user?.avatar || user?.user_avatar || user?.owner_avatar) : null;
  const cls = "avatar" + (size ? " avatar-" + size : "");
  if (file) {
    const img = el("img", cls);
    img.src = `/static/img/avatars/${file}`;
    img.alt = name || "";
    img.loading = "lazy";
    return img;
  }
  const node = el("span", cls, (name || "?").trim().charAt(0).toUpperCase());
  node.style.background = (typeof user === "object" && (user?.color || user?.user_color)) || "#6366f1";
  node.style.display = "grid";
  node.style.placeItems = "center";
  node.style.fontWeight = "600";
  node.style.color = "#0a0e1a";
  return node;
}

/** Цветная плитка с иконкой — базовый визуальный элемент интерфейса. */
export function icoTile(name, tone = "", size = "") {
  const box = el("span", ["ico-tile", tone, size].filter(Boolean).join(" "));
  box.append(icon(name));
  return box;
}

export function meter(on, color) {
  const box = el("span", "meter");
  if (color) box.style.setProperty("--c", color);
  for (let i = 0; i < 5; i++) box.append(el("i", i < on ? "on" : ""));
  return box;
}

const pad = (n) => String(n).padStart(2, "0");

export function fmtTime(sec) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  sec = Math.floor(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

export function fmtDate(value, withTime = true) {
  if (!value) return "";
  const iso = typeof value === "string" && !value.includes("T") ? value.replace(" ", "T") + "Z" : value;
  const d = new Date(iso);
  if (isNaN(d)) return String(value);
  const opts = { day: "numeric", month: "long", year: "numeric" };
  if (withTime) Object.assign(opts, { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleString("ru-RU", opts);
}

export function fmtDateShort(value) {
  if (!value) return "";
  const iso = typeof value === "string" && !value.includes("T") ? value.replace(" ", "T") + "Z" : value;
  const d = new Date(iso);
  return isNaN(d) ? String(value) : d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export const fmtSize = (b) => b >= 1048576 ? (b / 1048576).toFixed(1) + " МБ" : Math.max(1, Math.round(b / 1024)) + " КБ";

export function plural(n, forms) {
  const a = Math.abs(n) % 100, b = a % 10;
  if (a > 10 && a < 20) return forms[2];
  if (b > 1 && b < 5) return forms[1];
  if (b === 1) return forms[0];
  return forms[2];
}

export const normalize = (t) =>
  String(t || "").toLowerCase().replace(/ё/g, "е").replace(/[^\p{L}\p{N}]+/gu, " ").trim();

export const SEVERITY = {
  ok: { label: "Без проблем", cls: "sev-ok" },
  attention: { label: "Требует внимания", cls: "sev-attention" },
  critical: { label: "Критический", cls: "sev-critical" },
};

export const RISK = { high: "Высокий", medium: "Средний", low: "Низкий", none: "Нет" };
export const WHO = { "клиент": "Клиент", "компания": "Компания", "обе стороны": "Обе стороны" };

export function severityBadge(value) {
  const info = SEVERITY[value] || { label: "—", cls: "" };
  return el("span", "sev " + info.cls, info.label);
}

let toastTimer;
export function toast(message) {
  let node = $("#toast");
  if (!node) {
    node = el("div", "toast");
    node.id = "toast";
    document.body.append(node);
  }
  node.textContent = message;
  node.hidden = false;
  requestAnimationFrame(() => node.classList.add("show"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    node.classList.remove("show");
    setTimeout(() => { node.hidden = true; }, 260);
  }, 2800);
}

export function loading(text = "Загружаю…") {
  const box = el("div", "loading");
  box.append(el("div", "spinner"), el("span", null, text));
  return box;
}

export function emptyState(text, iconName = "inbox", hint = "") {
  const box = el("div", "empty");
  box.append(icoTile(iconName, "", "lg"), el("b", null, text));
  if (hint) box.append(el("div", "small dim", hint));
  return box;
}

export function errorBox(err) {
  const box = el("div", "alert alert-error", err?.message || String(err));
  return box;
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = el("textarea");
    area.value = text;
    area.style.cssText = "position:fixed;opacity:0";
    document.body.append(area);
    area.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { /* ignore */ }
    area.remove();
    return ok;
  }
}

export function downloadFile(name, text, type = "text/markdown") {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
  const a = el("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function modal(title, body, actions = []) {
  const back = el("div", "modal-back");
  const box = el("div", "modal");
  const head = el("div", "row-between");
  head.append(el("h2", null, title));
  const close = el("button", "btn btn-ghost btn-icon");
  close.append(icon("x"));
  head.append(close);
  box.append(head, body);
  if (actions.length) {
    const row = el("div", "row");
    row.style.marginTop = "22px";
    actions.forEach((a) => row.append(a));
    box.append(row);
  }
  back.append(box);
  document.body.append(back);
  const dispose = () => back.remove();
  close.addEventListener("click", dispose);
  back.addEventListener("click", (e) => { if (e.target === back) dispose(); });
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") { dispose(); document.removeEventListener("keydown", esc); }
  });
  return dispose;
}
