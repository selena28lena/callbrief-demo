// Хеш-роутинг: #/calls, #/calls/12, #/coach и т.д.

const routes = [];
let notFound = null;
let currentDispose = null;

export function route(pattern, render) {
  // "#/calls/:id" → регулярное выражение с именованными параметрами
  const names = [];
  const regex = new RegExp(
    "^" + pattern.replace(/:([\w]+)/g, (_, name) => { names.push(name); return "([^/]+)"; }) + "$"
  );
  routes.push({ regex, names, render });
}

export function setNotFound(render) {
  notFound = render;
}

export function parse() {
  const hash = location.hash.replace(/^#/, "") || "/";
  const [path, query] = hash.split("?");
  return { path, params: Object.fromEntries(new URLSearchParams(query || "")) };
}

export function go(path, replace = false) {
  const url = "#" + path;
  if (location.hash === url) return handle();
  if (replace) location.replace(url); else location.hash = url;
}

export function current() {
  return parse().path;
}

async function handle() {
  const { path, params } = parse();
  for (const r of routes) {
    const match = path.match(r.regex);
    if (!match) continue;
    const args = Object.fromEntries(r.names.map((n, i) => [n, decodeURIComponent(match[i + 1])]));
    if (typeof currentDispose === "function") { currentDispose(); currentDispose = null; }
    currentDispose = await r.render({ ...args, query: params, path });
    return;
  }
  if (notFound) notFound(path);
}

export function start() {
  window.addEventListener("hashchange", handle);
  handle();
}
