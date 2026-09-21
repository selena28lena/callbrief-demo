// Раздел «Звонки»: поиск, фильтры, таблица.

import { api } from "../api.js";
import { isHead, mount, setBack } from "../app.js";
import { callTable } from "../components/callTable.js";
import { el, errorBox, icon, loading } from "../ui.js";

const SEVERITIES = [
  { key: "", label: "Все" },
  { key: "critical", label: "Критические" },
  { key: "attention", label: "Требуют внимания" },
  { key: "ok", label: "Без проблем" },
];

const FLAGS = [
  { key: "high_risk", label: "Высокий риск" },
  { key: "no_next_step", label: "Нет следующего шага" },
  { key: "price", label: "Возражение по цене" },
  { key: "competitor", label: "Упомянут конкурент" },
  { key: "refused", label: "Отказ" },
  { key: "interested", label: "Заинтересован" },
];

export async function render(query = {}) {
  setBack(null);
  const params = {
    severity: query.severity || "",
    flags: (query.flags || "").split(",").filter(Boolean),
    mine: query.mine === "1",
    q: query.q || "",
  };

  const page = el("div", "page");
  const head = el("div", "page-head");
  const title = el("div");
  title.append(el("h1", null, "Звонки"),
    el("p", "sub", isHead()
      ? "Все звонки отдела. Фильтры показывают, где именно теряются сделки."
      : "Ваши звонки и открытые звонки коллег — на чужих примерах тоже можно учиться."));
  head.append(title);
  page.append(head);

  const toolbar = el("div", "toolbar");
  const search = el("div", "search-box");
  const input = el("input");
  input.type = "search";
  input.placeholder = "Поиск по клиенту, названию или тексту разговора";
  input.value = params.q;
  search.append(icon("search"), input);
  toolbar.append(search);

  if (isHead()) {
    const mine = el("button", "chip" + (params.mine ? " on" : ""), "Только мои");
    mine.addEventListener("click", () => { params.mine = !params.mine; sync(); });
    toolbar.append(mine);
  }

  const sevRow = el("div", "chips");
  SEVERITIES.forEach((s) => {
    const chip = el("button", "chip" + (params.severity === s.key ? " on" : ""), s.label);
    chip.addEventListener("click", () => { params.severity = s.key; sync(); });
    sevRow.append(chip);
  });

  const flagRow = el("div", "chips");
  flagRow.style.marginTop = "10px";
  FLAGS.forEach((f) => {
    const chip = el("button", "chip" + (params.flags.includes(f.key) ? " on" : ""), f.label);
    chip.addEventListener("click", () => {
      params.flags = params.flags.includes(f.key)
        ? params.flags.filter((x) => x !== f.key)
        : [...params.flags, f.key];
      sync();
    });
    flagRow.append(chip);
  });

  const card = el("div", "card");
  const box = el("div");
  card.append(box);
  page.append(toolbar, sevRow, flagRow, card);
  mount(page);

  let timer;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => { params.q = input.value.trim(); sync(); }, 350);
  });

  function sync() {
    const search = new URLSearchParams();
    if (params.severity) search.set("severity", params.severity);
    if (params.flags.length) search.set("flags", params.flags.join(","));
    if (params.mine) search.set("mine", "1");
    if (params.q) search.set("q", params.q);
    const str = search.toString();
    history.replaceState(null, "", "#/calls" + (str ? "?" + str : ""));
    [...sevRow.children].forEach((chip, i) => chip.classList.toggle("on", SEVERITIES[i].key === params.severity));
    [...flagRow.children].forEach((chip, i) => chip.classList.toggle("on", params.flags.includes(FLAGS[i].key)));
    load();
  }

  async function load() {
    box.replaceChildren(loading("Загружаю звонки…"));
    try {
      const data = await api.calls({
        severity: params.severity,
        flags: params.flags.join(","),
        mine: params.mine,
        q: params.q,
        limit: 200,
      });
      const count = el("div", "row-between");
      count.style.marginBottom = "16px";
      count.append(el("span", "muted small", `Найдено звонков: ${data.items.length}`));
      box.replaceChildren(count, callTable(data.items));
    } catch (err) {
      box.replaceChildren(errorBox(err));
    }
  }

  load();
}
