// Команда: контроль отдела для руководителя.

import { api } from "../api.js";
import { mount, setBack } from "../app.js";
import { bar, donut, legend } from "../components/charts.js";
import { callTable } from "../components/callTable.js";
import { avatar, el, errorBox, icoTile, icon, loading, plural, tag } from "../ui.js";

function managerCard(manager) {
  const card = el("a", "card card-hover");
  card.href = `#/coach?user=${manager.id}`;
  const head = el("div", "row");
  head.append(avatar(manager, "lg"));
  const info = el("div");
  info.style.minWidth = "0";
  info.append(el("div", "strong big", manager.name));
  info.append(el("div", "t-sub", `${manager.calls} ${plural(manager.calls, ["звонок", "звонка", "звонков"])} за месяц`));
  head.append(info);
  card.append(head);

  // Вместо абстрактного балла — доля разговоров, где всё прошло чисто
  const clean = Math.max(0, manager.calls - manager.critical - manager.attention);
  const share = manager.calls ? Math.round((clean / manager.calls) * 100) : 0;
  const shareRow = el("div", "row-between");
  shareRow.style.margin = "18px 0 10px";
  shareRow.append(el("span", "muted small", "Звонки без замечаний"));
  shareRow.append(el("span", "strong big", `${clean} из ${manager.calls}`));
  card.append(shareRow);
  card.append(bar(share, share >= 70 ? "var(--green)" : share >= 40 ? "var(--amber)" : "var(--red)"));

  const tags = el("div", "row");
  tags.style.marginTop = "16px";
  if (manager.critical) tags.append(tag(`${manager.critical} критических`, "alert", "bad"));
  if (manager.attention) tags.append(tag(`${manager.attention} с замечаниями`, "alert", "warn"));
  if (!manager.critical && !manager.attention) tags.append(tag("без проблем", "check-c", "ok"));
  card.append(tags);

  const problem = el("div", "row");
  problem.style.marginTop = "14px";
  problem.append(icoTile("coach", "violet", "sm"));
  const problemText = el("div");
  problemText.append(el("div", "small muted", "Главная зона роста"));
  problemText.append(el("div", "strong", manager.problem));
  problem.append(problemText);
  card.append(problem);
  return card;
}

export async function render() {
  setBack(null);
  const page = el("div", "page");
  const head = el("div", "page-head");
  const title = el("div");
  title.append(el("h1", null, "Команда"),
    el("p", "sub", "Кто справляется, кому нужна помощь и какие звонки разобрать в первую очередь"));
  head.append(title);
  page.append(head);
  const spinner = loading("Считаю показатели команды…");
  page.append(spinner);
  mount(page);

  let data;
  try {
    data = await api.team({ days: 30 });
  } catch (err) {
    spinner.replaceWith(errorBox(err));
    return;
  }
  spinner.remove();

  const cards = el("div", "grid grid-4 stagger");
  data.managers.forEach((m) => cards.append(managerCard(m)));
  page.append(cards);

  const bottom = el("div", "grid grid-main mt");
  const tableCard = el("div", "card");
  const tHead = el("div", "card-head");
  const tRow = el("div", "row");
  tRow.append(icoTile("alert", "red", "sm"), el("h2", null, "Последние проблемные звонки"));
  tHead.append(tRow);
  const link = el("a", "link", "Все критические →");
  link.href = "#/calls?severity=critical";
  tHead.append(link);
  tableCard.append(tHead, callTable(data.problem_calls, {}));
  bottom.append(tableCard);

  const side = el("div", "card");
  const sHead = el("div", "card-head");
  const sRow = el("div", "row");
  sRow.append(icoTile("team", "sky", "sm"), el("h2", null, "Общая статистика"));
  sHead.append(sRow);
  side.append(sHead);
  const okPercent = data.total ? Math.round((data.counts.ok / data.total) * 100) : 0;
  const wrap = el("div", "donut-wrap");
  wrap.append(
    donut([
      { label: "Без проблем", value: data.counts.ok, color: "var(--green)" },
      { label: "Требует внимания", value: data.counts.attention, color: "var(--amber)" },
      { label: "Критические", value: data.counts.critical, color: "var(--red)" },
    ], { size: 158, centerValue: `${okPercent}%`, centerLabel: "звонков без проблем" }),
    legend([
      { label: "Всего звонков", value: data.total, color: "var(--indigo-2)" },
      { label: "Требуют внимания", value: data.counts.attention, color: "var(--amber)" },
      { label: "Критические", value: data.counts.critical, color: "var(--red)" },
      { label: "Без замечаний", value: data.counts.ok, color: "var(--green)" },
    ], { suffix: "" })
  );
  side.append(wrap);
  bottom.append(side);
  page.append(bottom);
}
