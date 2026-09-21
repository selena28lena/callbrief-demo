// Лучшие звонки: библиотека эталонных моментов отдела.

import { api } from "../api.js";
import { mount, setBack } from "../app.js";
import { avatar, el, emptyState, errorBox, fmtTime, icoTile, icon, loading, tag } from "../ui.js";

function momentCard(moment) {
  const card = el("div", "card card-hover");
  const head = el("div", "row-between");
  const left = el("div", "row");
  left.append(avatar(moment, "sm"));
  const who = el("div");
  who.append(el("div", "strong", moment.user_name || "Менеджер"));
  who.append(el("div", "t-sub", moment.call_title || ""));
  left.append(who);
  head.append(left);
  head.append(tag("эталон", "star", "ok"));
  card.append(head);

  const skill = el("div", "row");
  skill.style.marginTop = "14px";
  skill.append(tag(moment.skill, "target", "info"));
  if (moment.time_sec != null) skill.append(tag(fmtTime(moment.time_sec), "clock", "plain"));
  card.append(skill);

  card.append(el("div", "quote", `«${moment.quote}»`));
  if (moment.why_good) {
    const why = el("div", "row");
    why.style.marginTop = "14px";
    why.append(icoTile("bulb", "green", "sm"));
    why.append(el("p", "small", moment.why_good));
    why.lastChild.style.flex = "1";
    card.append(why);
  }

  const open = el("a", "link");
  open.href = `#/calls/${moment.call_id}`;
  open.style.marginTop = "16px";
  open.append(icon("play", "i-sm"), el("span", null, "Послушать этот момент"));
  card.append(open);
  return card;
}

export async function render() {
  setBack(null);
  const page = el("div", "page");
  const head = el("div", "page-head");
  const title = el("div");
  title.append(el("h1", null, "Лучшие звонки"),
    el("p", "sub", "Как коллеги отрабатывают возражения и выявляют потребность — можно слушать и копировать формулировки"));
  head.append(title);
  page.append(head);

  const chips = el("div", "chips");
  chips.style.marginBottom = "18px";
  page.append(chips);
  const grid = el("div", "grid grid-3 stagger");
  page.append(grid);
  grid.append(loading("Собираю эталонные моменты…"));
  mount(page);

  let current = "";
  async function load(skill = "") {
    current = skill;
    grid.replaceChildren(loading("Загружаю…"));
    try {
      const data = await api.best({ skill });
      chips.replaceChildren();
      const all = el("button", "chip" + (current ? "" : " on"), "Все навыки");
      all.addEventListener("click", () => load(""));
      chips.append(all);
      data.skills.forEach((s) => {
        const chip = el("button", "chip" + (current === s.skill ? " on" : ""), `${s.skill} · ${s.n}`);
        chip.addEventListener("click", () => load(s.skill));
        chips.append(chip);
      });
      grid.replaceChildren();
      if (!data.items.length) {
        grid.append(emptyState("Эталонных моментов пока нет", "star"));
        return;
      }
      data.items.forEach((m) => grid.append(momentCard(m)));
    } catch (err) {
      grid.replaceChildren(errorBox(err));
    }
  }
  load();
}
