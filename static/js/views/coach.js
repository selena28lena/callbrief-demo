// Тренер: персональный разбор ошибок менеджера.

import { api } from "../api.js";
import { isHead, mount, setBack, state } from "../app.js";
import { avatar, el, emptyState, errorBox, fmtTime, icoTile, icon, loading, plural, tag, toast } from "../ui.js";

function patternCard(pattern) {
  const card = el("div", "coach-card");
  const head = el("div", "coach-head");
  head.append(icoTile("alert", "red", "sm"));
  const titleBox = el("div");
  titleBox.style.flex = "1";
  titleBox.append(el("div", "strong big", pattern.skill));
  titleBox.append(el("div", "small muted", `Повторяется в ${pattern.count} ${plural(pattern.count, ["звонке", "звонках", "звонках"])}`));
  head.append(titleBox);
  head.append(tag("Зона роста", "coach", "bad"));
  card.append(head);

  const steps = [
    { label: "Что произошло", text: pattern.evidence[0]?.quote ? `«${pattern.evidence[0].quote}»` : pattern.title, icon: "quote", tone: "" },
    { label: "Почему это проблема", text: pattern.description, icon: "alert", tone: "red" },
    { label: "Как было бы лучше", text: pattern.better_action, icon: "check-c", tone: "green" },
  ];
  steps.forEach((step) => {
    const row = el("div", "coach-step");
    row.append(icoTile(step.icon, step.tone, "sm"));
    const body = el("div");
    body.style.flex = "1";
    body.append(el("div", "label", step.label), el("p", null, step.text));
    row.append(body);
    card.append(row);
  });

  if (pattern.sample_phrase) {
    const row = el("div", "coach-step");
    row.append(icoTile("sparkle", "violet", "sm"));
    const body = el("div");
    body.style.flex = "1";
    body.append(el("div", "label", "Готовая фраза"), el("div", "phrase", pattern.sample_phrase));
    row.append(body);
    card.append(row);
  }

  const foot = el("div", "coach-step");
  const evidence = el("div", "row");
  evidence.style.flex = "1";
  evidence.append(el("span", "small dim", "Примеры:"));
  pattern.evidence.slice(0, 3).forEach((ev) => {
    const link = el("a", "chip", `${ev.call_title?.slice(0, 22) || "звонок"} · ${fmtTime(ev.time_sec || 0)}`);
    link.href = `#/calls/${ev.call_id}`;
    evidence.append(link);
  });
  foot.append(evidence);
  const train = el("button", "btn btn-primary btn-sm");
  train.append(icon("coach", "i-sm"), el("span", null, "Потренироваться"));
  train.addEventListener("click", () => toast("Тренировки включим на следующем шаге"));
  foot.append(train);
  card.append(foot);
  return card;
}

export async function render(mode = "coach", query = {}) {
  setBack(null);
  const page = el("div", "page");
  const head = el("div", "page-head");
  const title = el("div");
  title.append(el("h1", null, "Тренер"),
    el("p", "sub", "Что мешает закрывать сделки именно вам — с примерами из ваших звонков и готовыми формулировками"));
  head.append(title);
  page.append(head);
  const spinner = loading("Разбираю ваши звонки…");
  page.append(spinner);
  mount(page);

  // У руководителя своих звонков нет: без выбранного менеджера раздел был бы пустым
  const managers = state.users.filter((u) => u.role === "manager");
  const userId = query.user ? Number(query.user) : (isHead() ? managers[0]?.id : undefined);
  let data;
  try {
    data = await api.coach({ days: 30, user_id: userId });
  } catch (err) {
    spinner.replaceWith(errorBox(err));
    return;
  }
  spinner.remove();

  if (isHead()) {
    const people = el("div", "chips");
    people.style.marginBottom = "18px";
    managers.forEach((u) => {
      const chip = el("a", "chip" + ((data.user?.id || userId) === u.id ? " on" : ""));
      chip.href = `#/coach?user=${u.id}`;
      chip.append(avatar(u, "sm"), el("span", null, u.name));
      chip.style.paddingLeft = "6px";
      people.append(chip);
    });
    page.append(people);
  }

  const top = el("div", "grid grid-3 stagger");
  [
    ["Звонков разобрано", data.calls_analyzed, "за 30 дней", "info", "phone"],
    ["Повторяющихся ошибок", data.patterns.length, "над чем работать", "warn", "alert"],
    ["Сильных сторон", data.strengths.length, "что уже получается", "ok", "star"],
  ].forEach(([label, value, foot, tone, iconName]) => {
    const card = el("div", "kpi " + tone);
    const labelRow = el("div", "kpi-label");
    labelRow.append(icon(iconName, "i-sm"), el("span", null, label));
    card.append(labelRow, el("div", "kpi-value tabular", String(value)), el("div", "kpi-foot", foot));
    top.append(card);
  });
  page.append(top);

  const body = el("div", "grid grid-main mt");
  const left = el("div", "col");
  left.style.gap = "var(--gap)";
  const sec = el("div", "row");
  sec.append(icoTile("coach", "red", "sm"), el("h2", null, "Повторяющиеся ошибки"));
  left.append(sec);
  if (!data.patterns.length) {
    left.append(emptyState("Повторяющихся ошибок не найдено — отличная работа", "check-c"));
  } else {
    data.patterns.slice(0, 4).forEach((p) => left.append(patternCard(p)));
  }
  body.append(left);

  const right = el("div", "col");
  right.style.gap = "var(--gap)";

  const skills = el("div", "card");
  const sHead = el("div", "card-head");
  const sRow = el("div", "row");
  sRow.append(icoTile("target", "sky", "sm"), el("h2", null, "Навыки по разговорам"));
  sHead.append(sRow);
  skills.append(sHead);
  if (data.skills.length) {
    // Без баллов: важен порядок — что тянет вниз, а что уже держится уверенно
    const list = el("div", "mini-list");
    data.skills.slice(0, 7).forEach((skill, i) => {
      const weak = i < 2;
      const strong = i >= data.skills.length - 2 && data.skills.length > 3;
      const item = el("div", "mini-item " + (weak ? "bad" : strong ? "ok" : "warn"));
      const row = el("div", "row-between");
      row.append(el("div", "t", skill.name));
      row.append(weak ? tag("слабое место", "alert", "bad")
        : strong ? tag("получается", "check-c", "ok") : tag("нестабильно", "flag", "warn"));
      item.append(row);
      list.append(item);
    });
    skills.append(list);
  } else {
    skills.append(el("p", "muted", "Пока нет разобранных звонков за период"));
  }
  right.append(skills);

  const strong = el("div", "card");
  const stHead = el("div", "card-head");
  const stRow = el("div", "row");
  stRow.append(icoTile("star", "green", "sm"), el("h2", null, "Сильные стороны"));
  stHead.append(stRow);
  strong.append(stHead);
  if (data.strengths.length) {
    const list = el("ul", "bullets ok");
    data.strengths.forEach((s) => list.append(el("li", null, `${s.skill} — ${s.n} ${plural(s.n, ["удачный момент", "удачных момента", "удачных моментов"])}`)));
    strong.append(list);
    const link = el("a", "link", "Смотреть лучшие моменты →");
    link.href = "#/best";
    strong.append(link);
  } else {
    strong.append(el("p", "muted", "Пока нет выделенных удачных моментов"));
  }
  right.append(strong);

  const growth = el("div", "card");
  const gHead = el("div", "card-head");
  const gRow = el("div", "row");
  gRow.append(icoTile("bolt", "amber", "sm"), el("h2", null, "План на неделю"));
  gHead.append(gRow);
  growth.append(gHead);
  const plan = el("ul", "bullets");
  const worst = data.skills[0];
  if (worst) plan.append(el("li", null, `Сфокусироваться на навыке «${worst.name}» — он чаще всего проседает в ваших звонках`));
  if (data.patterns[0]) plan.append(el("li", null, data.patterns[0].better_action));
  plan.append(el("li", null, "Послушать два эталонных звонка коллег в разделе «Лучшие звонки»"));
  growth.append(plan);
  right.append(growth);

  body.append(right);
  page.append(body);
}
