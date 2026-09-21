// Клиенты: AI-слой поверх CRM — история звонков, договорённости и риски.

import { api } from "../api.js";
import { mount, setBack } from "../app.js";
import { callTable } from "../components/callTable.js";
import { avatar, el, emptyState, errorBox, fmtDateShort, icoTile, icon, loading, modal, plural, tag } from "../ui.js";

function clientCard(client) {
  const card = el("button", "card card-hover");
  card.style.textAlign = "left";
  const head = el("div", "row");
  const tone = client.critical ? "red" : client.has_next_step ? "green" : "amber";
  head.append(icoTile("users", tone, "lg"));
  const info = el("div");
  info.style.flex = "1";
  info.style.minWidth = "0";
  info.append(el("div", "strong big", client.company || client.name));
  info.append(el("div", "t-sub", `${client.name || ""}${client.industry ? " · " + client.industry : ""}`));
  head.append(info);
  card.append(head);

  const stats = el("div", "row");
  stats.style.marginTop = "16px";
  stats.append(tag(`${client.calls_count} ${plural(client.calls_count, ["звонок", "звонка", "звонков"])}`, "phone"));
  if (client.critical) stats.append(tag(`${client.critical} ${plural(client.critical, ["критический", "критических", "критических"])}`, "alert", "bad"));
  stats.append(client.has_next_step ? tag("шаг назначен", "check", "ok") : tag("нет следующего шага", "alert", "warn"));
  card.append(stats);

  const foot = el("div", "row-between");
  foot.style.marginTop = "16px";
  const owner = el("div", "row");
  owner.append(avatar({ name: client.owner_name, avatar: client.owner_avatar }, "sm"),
    el("span", "small muted", client.owner_name || "—"));
  foot.append(owner);
  foot.append(el("span", "small dim", client.last_call_at ? fmtDateShort(client.last_call_at) : "—"));
  card.append(foot);

  card.addEventListener("click", () => openClient(client.id));
  return card;
}

async function openClient(id) {
  const body = el("div", "col");
  body.append(loading("Открываю карточку клиента…"));
  const close = modal("Клиент", body);
  try {
    const data = await api.client(id);
    body.replaceChildren();
    const head = el("div", "row");
    head.append(icoTile("users", "sky", "lg"));
    const info = el("div");
    info.append(el("h2", null, data.client.company || data.client.name));
    info.append(el("div", "small muted", [data.client.name, data.client.phone, data.client.industry].filter(Boolean).join(" · ")));
    head.append(info);
    body.append(head);

    if (data.agreements.length) {
      body.append(el("div", "sec-title", "Договорённости"));
      const list = el("ul", "bullets ok");
      data.agreements.slice(0, 5).forEach((a) => list.append(el("li", null, a.text)));
      body.append(list);
    }
    if (data.risks.length) {
      body.append(el("div", "sec-title", "Риски"));
      const list = el("ul", "bullets bad");
      data.risks.slice(0, 5).forEach((r) => list.append(el("li", null, r.text)));
      body.append(list);
    }
    body.append(el("div", "sec-title", "История звонков"));
    body.append(callTable(data.calls, { compact: true, onOpen: (call) => { close(); location.hash = `#/calls/${call.id}`; } }));
  } catch (err) {
    body.replaceChildren(errorBox(err));
  }
}

export async function render() {
  setBack(null);
  const page = el("div", "page");
  const head = el("div", "page-head");
  const title = el("div");
  title.append(el("h1", null, "Клиенты"),
    el("p", "sub", "Что AI знает о каждом клиенте: договорённости, риски и следующий шаг"));
  head.append(title);
  page.append(head);

  const toolbar = el("div", "toolbar");
  const search = el("div", "search-box");
  const input = el("input");
  input.type = "search";
  input.placeholder = "Поиск по компании или контакту";
  search.append(icon("search"), input);
  toolbar.append(search);
  page.append(toolbar);

  const grid = el("div", "grid grid-3 stagger");
  page.append(grid);
  grid.append(loading("Загружаю клиентов…"));
  mount(page);

  try {
    const data = await api.clients();
    const draw = (query = "") => {
      const lowered = query.toLowerCase();
      const items = data.items.filter((c) => !query ||
        `${c.company || ""} ${c.name || ""}`.toLowerCase().includes(lowered));
      grid.replaceChildren();
      if (!items.length) grid.append(emptyState("Клиенты не найдены", "users"));
      items.forEach((c) => grid.append(clientCard(c)));
    };
    draw();
    let timer;
    input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => draw(input.value.trim()), 250); });
  } catch (err) {
    grid.replaceChildren(errorBox(err));
  }
}
