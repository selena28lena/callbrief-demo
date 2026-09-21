// Главная: у менеджера — загрузка звонка и то, что требует его внимания. У руководителя — состояние отдела.

import { api } from "../api.js";
import { isHead, mount, setBack, state } from "../app.js";
import { donut, legend } from "../components/charts.js";
import { callList, callTable } from "../components/callTable.js";
import { uploadCard } from "../components/uploadCard.js";
import { avatar, el, errorBox, icoTile, icon, loading, plural, tag } from "../ui.js";

function kpi(label, value, foot, tone, href, iconName) {
  const card = el(href ? "a" : "div", "kpi " + (tone || ""));
  if (href) card.href = href;
  const head = el("div", "kpi-label");
  if (iconName) head.append(icon(iconName, "i-sm"));
  head.append(el("span", null, label));
  card.append(head, el("div", "kpi-value tabular", String(value)));
  const footBox = el("div", "kpi-foot");
  if (typeof foot === "string") footBox.append(el("span", null, foot));
  else if (foot) footBox.append(foot);
  card.append(footBox);
  return card;
}

function managerRow(manager) {
  const row = el("a", "row");
  row.href = `#/coach?user=${manager.id}`;
  row.style.cssText = "gap:14px;padding:12px 0;border-bottom:1px solid var(--line)";
  row.append(avatar(manager));
  const info = el("div");
  info.style.flex = "1";
  info.style.minWidth = "0";
  info.append(el("div", "strong", manager.name));
  info.append(el("div", "t-sub", `${manager.calls} ${plural(manager.calls, ["звонок", "звонка", "звонков"])} · ${manager.critical} ${plural(manager.critical, ["критический", "критических", "критических"])}`));
  // Зона роста — под именем: в узкой колонке справа она сжимала имя до слова в строке
  const problem = tag(manager.problem, "alert", manager.critical > 3 ? "bad" : "warn");
  problem.style.marginTop = "8px";
  info.append(problem);
  row.append(info);
  return row;
}

function insightCard(item) {
  const box = el("div", "item");
  box.style.background = "var(--surface-2)";
  const head = el("div", "row");
  head.append(tag(
    { objections: "Системная проблема", funnel: "Воронка", losing: "Менеджеры", repeats: "Повтор у многих",
      questions: "Скрипт", best_phrases: "Новая практика" }[item.kind] || "Инсайт", "sparkle", "ai"));
  box.append(head);
  const title = el("div", "item-title", item.title);
  title.style.marginTop = "12px";
  box.append(title, el("p", "small muted", item.body));
  box.lastChild.style.marginTop = "8px";
  const more = el("a", "link", "Смотреть звонки →");
  more.href = "#/insights";
  more.style.marginTop = "12px";
  box.append(more);
  return box;
}

/** Главный блок менеджера: сколько звонков ждут разбора и переход к ним одним кликом. */
function attentionCard(stats, href) {
  const count = stats.counts.attention + stats.counts.critical;
  const card = el("a", "card attention-card" + (count ? "" : " calm"));
  card.href = href;
  const head = el("div", "row");
  head.append(icoTile(count ? "alert" : "check-c", count ? "red" : "green", "lg"));
  const titleBox = el("div");
  titleBox.append(el("h2", null, count ? "Требует вашего внимания" : "Всё разобрано"));
  titleBox.append(el("div", "small muted", count
    ? "Звонки, где что-то пошло не так — разберите их с тренером"
    : "Проблемных звонков за последние 30 дней нет"));
  head.append(titleBox);
  card.append(head);

  const big = el("div", "attention-value tabular", String(count));
  card.append(big);
  const sub = el("div", "col");
  sub.style.gap = "8px";
  if (stats.counts.critical) {
    const r = el("div", "row");
    r.append(tag(`${stats.counts.critical} ${plural(stats.counts.critical, ["критический", "критических", "критических"])}`, "alert", "bad"));
    sub.append(r);
  }
  if (stats.no_next_step) {
    const r = el("div", "row");
    r.append(tag(`${stats.no_next_step} без следующего шага`, "steps", "warn"));
    sub.append(r);
  }
  card.append(sub);

  const go = el("div", "link");
  go.style.marginTop = "18px";
  go.append(el("span", null, count ? "Разобрать звонки" : "Посмотреть все звонки"), icon("arrow-r", "i-sm"));
  card.append(go);
  return card;
}

export async function render() {
  setBack(null);
  const page = el("div", "page");
  const head = el("div", "page-head");
  const title = el("div");
  title.append(
    el("h1", null, isHead() ? "Панель руководителя" : `Рабочий стол · ${(state.user?.name || "").split(" ")[0]}`),
    el("p", "sub", isHead()
      ? "Что происходит в отделе продаж и на что нужно посмотреть именно вам"
      : "Загрузите звонок — разбор, комментарий и задача для CRM появятся сами")
  );
  head.append(title);
  const period = el("span", "pill");
  period.append(icon("calendar", "i-sm"), el("span", null, "Последние 30 дней"));
  head.append(period);
  page.append(head);

  const body = el("div");
  page.append(body);
  const spinner = loading("Собираю данные…");
  page.append(spinner);
  mount(page);

  let stats, calls;
  try {
    [stats, calls] = await Promise.all([
      api.stats({ days: 30, mine: !isHead() }),
      api.calls({ days: 30, limit: 300, mine: !isHead() }),
    ]);
  } catch (err) {
    spinner.replaceWith(errorBox(err));
    return;
  }
  spinner.remove();
  const items = calls.items;
  const pct = (n) => (stats.total ? Math.round((n / stats.total) * 100) + "%" : "0%");
  const problems = items.filter((c) => c.severity === "critical" || c.severity === "attention");

  // ---------- Менеджер: загрузка звонка + что требует внимания ----------
  if (!isHead()) {
    const top = el("div", "grid grid-start stagger");
    const upload = uploadCard((id) => (location.hash = `#/calls/${id}`));
    upload.classList.add("upload-hero");
    top.append(upload, attentionCard(stats, "#/calls?severity=critical&mine=1"));
    body.append(top);

    const bottom = el("div", "grid grid-main mt stagger");
    const listCard = el("div", "card");
    const lHead = el("div", "card-head");
    const lRow = el("div", "row");
    lRow.append(icoTile("alert", "red", "sm"), el("h2", null, "Ваши звонки с ошибками"));
    lHead.append(lRow);
    const allLink = el("a", "link nowrap", "Все звонки →");
    allLink.href = "#/calls?mine=1";
    lHead.append(allLink);
    listCard.append(lHead);
    if (problems.length) {
      listCard.append(callList(problems, { limit: 6 }));
    } else {
      listCard.append(el("p", "muted", "Звонков с замечаниями нет — так держать."));
    }
    bottom.append(listCard);

    const side = el("div", "card");
    const sHead = el("div", "card-head");
    const sRow = el("div", "row");
    sRow.append(icoTile("target", "amber", "sm"), el("h2", null, "Почему клиенты отказывают"));
    sHead.append(sRow);
    side.append(sHead);
    if (stats.rejections.length) {
      const wrap = el("div", "donut-wrap");
      const totalRejections = stats.rejections.reduce((sum, r) => sum + r.value, 0);
      wrap.append(donut(stats.rejections, { centerValue: totalRejections, centerLabel: "отказов" }), legend(stats.rejections));
      side.append(wrap);
    } else {
      side.append(el("p", "muted", "Отказов за период нет."));
    }
    bottom.append(side);
    body.append(bottom);
    return;
  }

  // ---------- Руководитель: состояние отдела ----------
  const kpis = el("div", "grid grid-4 stagger");
  kpis.append(
    kpi("Всего звонков", stats.total, `${stats.trend > 0 ? "+" : ""}${stats.trend}% к прошлому периоду`, "info", "#/calls", "phone"),
    kpi("Без проблем", stats.counts.ok, pct(stats.counts.ok), "ok", "#/calls?severity=ok", "check-c"),
    kpi("Требует внимания", stats.counts.attention, pct(stats.counts.attention), "warn", "#/calls?severity=attention", "alert"),
    kpi("Критические", stats.counts.critical, pct(stats.counts.critical), "bad", "#/calls?severity=critical", "alert"),
  );
  body.append(kpis);

  const columns = el("div", "grid grid-dash mt stagger");
  body.append(columns);

  const first = el("div", "card");
  const fHead = el("div", "card-head");
  const fRow = el("div", "row");
  fRow.append(icoTile("users", "violet", "sm"), el("h2", null, "Кому нужна помощь"));
  const teamLink = el("a", "link nowrap", "Команда →");
  teamLink.href = "#/team";
  fHead.append(fRow, teamLink);
  first.append(fHead);
  stats.managers.slice(0, 5).forEach((m) => first.append(managerRow(m)));
  columns.append(first);

  const aiCard = el("div", "card");
  const aHead = el("div", "card-head");
  const aRow = el("div", "row");
  aRow.append(icoTile("sparkle", "violet", "sm"), el("h2", null, "AI Insights"));
  const aLink = el("a", "link", "Все →");
  aLink.href = "#/insights";
  aHead.append(aRow, aLink);
  aiCard.append(aHead);
  const aiBox = el("div", "col");
  aiCard.append(aiBox);
  columns.append(aiCard);
  api.insights({ days: 30 }).then((data) => {
    aiBox.replaceChildren();
    data.items.slice(0, 2).forEach((i) => aiBox.append(insightCard(i)));
    if (!data.items.length) aiBox.append(el("p", "muted", "Пока недостаточно данных для выводов."));
  }).catch(() => aiBox.replaceChildren(el("p", "muted", "Инсайты недоступны")));

  const third = el("div", "card");
  const tHead = el("div", "card-head");
  const tRow = el("div", "row");
  tRow.append(icoTile("target", "amber", "sm"), el("h2", null, "Причины отказов"));
  tHead.append(tRow);
  third.append(tHead);
  if (stats.rejections.length) {
    const wrap = el("div", "donut-wrap");
    const totalRejections = stats.rejections.reduce((sum, r) => sum + r.value, 0);
    wrap.append(donut(stats.rejections, { centerValue: totalRejections, centerLabel: "отказов" }), legend(stats.rejections));
    third.append(wrap);
  } else {
    third.append(el("p", "muted", "Отказов за период нет — это хорошая новость."));
  }
  columns.append(third);

  const tableCard = el("div", "card mt");
  const pHead = el("div", "card-head");
  const pRow = el("div", "row");
  pRow.append(icoTile("alert", "red", "sm"), el("h2", null, "Последние проблемные звонки"));
  pHead.append(pRow);
  const allLink = el("a", "link", "Все звонки →");
  allLink.href = "#/calls?severity=critical";
  pHead.append(allLink);
  tableCard.append(pHead, callTable(problems.slice(0, 8), {}));
  body.append(tableCard);
}
