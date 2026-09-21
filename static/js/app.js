// Точка входа рабочего приложения: сессия, сайдбар, маршруты.

import { api, currentUserId, setCurrentUserId } from "./api.js";
import * as router from "./router.js";
import { $, avatar, el, icon, modal, toast } from "./ui.js";

export const state = {
  user: null,
  users: [],
  health: null,
  crm: null,
  pending: 0,
};

export const isHead = () => state.user?.role === "head";

const NAV = [
  { path: "/", label: "Главная", icon: "home" },
  { path: "/calls", label: "Звонки", icon: "phone" },
  { path: "/coach", label: "Тренер", icon: "coach" },
  { path: "/best", label: "Лучшие звонки", icon: "star" },
  { path: "/clients", label: "Клиенты", icon: "users" },
  { path: "/team", label: "Команда", icon: "team", head: true },
  { path: "/insights", label: "Инсайты", icon: "bulb", head: true },
  { path: "/settings", label: "Настройки", icon: "gear" },
];

export function renderNav() {
  const nav = $("#sideNav");
  nav.replaceChildren();
  const path = router.current();
  let groupAdded = false;
  NAV.forEach((item) => {
    if (item.head && !isHead()) return;
    if (item.head && !groupAdded) {
      nav.append(el("div", "side-group", "Руководителю"));
      groupAdded = true;
    }
    const link = el("a");
    link.href = "#" + item.path;
    link.append(icon(item.icon), el("span", null, item.label));
    if (item.badge && state.pending) link.append(el("span", "badge", String(state.pending)));
    const active = item.path === "/" ? path === "/" : path.startsWith(item.path);
    if (active) link.classList.add("active");
    nav.append(link);
  });
}

export function setUserUi() {
  const user = state.user;
  if (!user) return;
  const img = $("#userAvatar");
  if (user.avatar) {
    img.src = `/static/img/avatars/${user.avatar}`;
    img.alt = user.name;
  }
  $("#userName").textContent = user.name;
  $("#userRole").textContent = user.title || (user.role === "head" ? "Руководитель" : "Менеджер");
}

function openUserPicker() {
  const list = el("div", "col");
  state.users.forEach((u) => {
    const btn = el("button", "user-card");
    btn.append(avatar(u));
    const info = el("span");
    info.style.flex = "1";
    info.append(el("b", null, u.name), el("span", null, u.title || (u.role === "head" ? "Руководитель" : "Менеджер")));
    btn.append(info);
    if (u.id === state.user?.id) btn.append(el("span", "tag ok", "вы"));
    btn.addEventListener("click", async () => {
      setCurrentUserId(u.id);
      close();
      await loadSession();
      renderNav();
      router.go("/", true);
      toast(`Вы вошли как ${u.name}`);
    });
    list.append(btn);
  });
  const close = modal("Кто работает", list);
}

export function setStatus() {
  const pill = $("#statusPill");
  pill.classList.remove("ok", "warn", "bad");
  const text = $("#statusText");
  const crm = state.crm;
  if (crm && crm.connected && crm.ok !== false) {
    pill.classList.add("ok");
    text.textContent = `${crm.title} подключён`;
    return;
  }
  if (!state.health) { pill.classList.add("bad"); text.textContent = "Сервер недоступен"; return; }
  if (!state.health.has_key) { pill.classList.add("warn"); text.textContent = "Нет ключа Gemini"; return; }
  pill.classList.add("ok");
  text.textContent = `AI · ${state.health.model}`;
}

export function setBack(path) {
  const link = $("#backLink");
  link.hidden = !path;
  if (path) link.href = "#" + path;
}

export function mount(node) {
  $("#view").replaceChildren(node);
  renderNav();
  window.scrollTo(0, 0);
}

async function loadSession() {
  const data = await api.session();
  state.user = data.user;
  state.users = data.users;
  if (!currentUserId()) setCurrentUserId(data.user.id);
  setUserUi();
}

async function loadBadges() {
  try {
    const data = await api.actions({ status: "draft" });
    state.pending = data.items.length;
    renderNav();
  } catch { /* не критично */ }
}

function applyEmbedMode() {
  if (new URLSearchParams(location.search).get("embed") !== "1") return;
  document.body.classList.add("embed-mode");
}

async function boot() {
  applyEmbedMode();
  $("#userSwitch").addEventListener("click", openUserPicker);
  try {
    await loadSession();
  } catch (err) {
    $("#view").replaceChildren(el("div", "page").appendChild(el("div", "alert alert-error", err.message)).parentNode);
    return;
  }
  const [health, crm] = await Promise.allSettled([api.health(), api.crmStatus()]);
  state.health = health.status === "fulfilled" ? health.value : null;
  state.crm = crm.status === "fulfilled" ? crm.value : null;
  setStatus();

  const load = (path) => () => import(path);
  router.route("/", async () => (await import("./views/home.js")).render());
  router.route("/calls", async ({ query }) => (await import("./views/calls.js")).render(query));
  router.route("/calls/:id", async ({ id }) => (await import("./views/call.js")).render(Number(id)));
  router.route("/actions", async () => (await import("./views/actions.js")).render());
  router.route("/coach", async ({ query }) => (await import("./views/coach.js")).render("coach", query));
  router.route("/best", async () => (await import("./views/best.js")).render());
  router.route("/clients", async () => (await import("./views/clients.js")).render());
  router.route("/team", async () => (await import("./views/team.js")).render());
  router.route("/insights", async () => (await import("./views/insights.js")).render());
  router.route("/settings", async () => (await import("./views/settings.js")).render());
  router.setNotFound(() => router.go("/", true));
  router.start();
  loadBadges();
}

boot();
