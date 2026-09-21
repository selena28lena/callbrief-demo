// Инсайты: что AI видит по всему массиву звонков отдела.

import { api } from "../api.js";
import { mount, setBack } from "../app.js";
import { el, errorBox, icoTile, icon, loading } from "../ui.js";

const KINDS = {
  objections: { tone: "amber", icon: "alert", label: "Что мешает продажам" },
  funnel: { tone: "red", icon: "steps", label: "Где ломается воронка" },
  losing: { tone: "red", icon: "users", label: "Кто теряет клиентов" },
  repeats: { tone: "violet", icon: "copy", label: "Повторяется у разных менеджеров" },
  questions: { tone: "sky", icon: "help", label: "Что забывают выяснить" },
  best_phrases: { tone: "green", icon: "star", label: "Формулировки лучших" },
};

function insightCard(item, index) {
  const meta = KINDS[item.kind] || { tone: "", icon: "sparkle", label: "Наблюдение" };
  const card = el("div", "card card-hover");
  const head = el("div", "row");
  head.append(icoTile(meta.icon, meta.tone, "lg"));
  const titleBox = el("div");
  titleBox.style.flex = "1";
  titleBox.style.minWidth = "0";
  titleBox.append(el("div", "small muted", `${String(index + 1).padStart(2, "0")} · ${meta.label}`));
  titleBox.append(el("h2", null, item.title));
  head.append(titleBox);
  card.append(head);

  const body = el("p", "muted");
  body.style.marginTop = "14px";
  body.style.fontSize = "15.5px";
  body.textContent = item.body;
  card.append(body);

  if (item.evidence?.length) {
    const row = el("div", "row");
    row.style.marginTop = "16px";
    row.append(el("span", "small dim", "Основано на звонках:"));
    item.evidence.slice(0, 3).forEach((ev) => {
      const link = el("a", "chip", `Звонок №${ev.call_id}`);
      link.href = `#/calls/${ev.call_id}`;
      row.append(link);
    });
    card.append(row);
    const quotes = item.evidence.filter((e) => e.quote).slice(0, 2);
    quotes.forEach((q) => card.append(el("div", "quote", `«${q.quote}»`)));
  }
  return card;
}

export async function render() {
  setBack(null);
  const page = el("div", "page");
  const head = el("div", "page-head");
  const title = el("div");
  title.append(el("h1", null, "AI Insights"),
    el("p", "sub", "Выводы по всем звонкам отдела за месяц — каждый с доказательствами"));
  head.append(title);
  const period = el("span", "pill");
  period.append(icon("calendar", "i-sm"), el("span", null, "30 дней"));
  head.append(period);
  page.append(head);

  const spinner = loading("AI анализирует звонки отдела…");
  page.append(spinner);
  mount(page);

  let data;
  try {
    data = await api.insights({ days: 30 });
  } catch (err) {
    spinner.replaceWith(errorBox(err));
    return;
  }
  spinner.remove();

  if (!data.items.length) {
    page.append(el("div", "card").appendChild(el("p", "muted", "Пока мало звонков для выводов.")).parentNode);
    return;
  }

  const grid = el("div", "grid grid-2 stagger");
  data.items.forEach((item, i) => grid.append(insightCard(item, i)));
  page.append(grid);

  const actions = el("div", "card mt");
  const aHead = el("div", "card-head");
  const aRow = el("div", "row");
  aRow.append(icoTile("bolt", "green", "sm"), el("h2", null, "Что с этим делать"));
  aHead.append(aRow);
  actions.append(aHead);
  const list = el("ul", "bullets");
  [
    "Добавьте в скрипт обязательный вопрос про бюджет и критерий выбора — это закрывает половину возражений по цене.",
    "Введите правило: звонок не закрыт, пока не назначена дата следующего контакта.",
    "Разберите с менеджерами два звонка из раздела «Лучшие звонки» — там есть готовые формулировки.",
  ].forEach((text) => list.append(el("li", null, text)));
  actions.append(list);
  page.append(actions);
}
