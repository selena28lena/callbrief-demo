// Заглушка для разделов, которые появятся на следующих шагах.

import { mount, setBack } from "../app.js";
import { el, icon } from "../ui.js";

export async function render(title, text) {
  setBack(null);
  const page = el("div", "page");
  const head = el("div", "page-head");
  head.append(el("h1", null, title));
  const card = el("div", "card");
  const box = el("div", "empty");
  box.append(icon("bolt", "i-lg"), el("div", null, text), el("div", "small dim", "Раздел в работе"));
  card.append(box);
  page.append(head, card);
  mount(page);
}
