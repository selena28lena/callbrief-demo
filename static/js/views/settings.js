// Настройки: подключение AI и CRM, кнопка в карточке сделки, демо-данные.

import { api, currentUserId, setCurrentUserId } from "../api.js";
import { mount, renderNav, setBack, setUserUi, state } from "../app.js";
import { avatar, el, icoTile, icon, modal, toast } from "../ui.js";

function kvRow(iconName, tone, label, value, extra) {
  const row = el("div", "kv");
  row.append(icoTile(iconName, tone, "sm"));
  const body = el("div");
  body.style.flex = "1";
  body.append(el("div", "kv-label", label));
  const valueRow = el("div", "kv-value");
  valueRow.append(typeof value === "string" ? el("span", "strong", value) : value);
  if (extra) valueRow.append(extra);
  body.append(valueRow);
  row.append(body);
  return row;
}

function card(iconName, tone, title, subtitle) {
  const box = el("div", "card");
  const head = el("div", "row");
  head.style.marginBottom = "16px";
  head.append(icoTile(iconName, tone, "lg"));
  const text = el("div");
  text.append(el("h2", null, title));
  if (subtitle) text.append(el("div", "small muted", subtitle));
  head.append(text);
  box.append(head);
  return box;
}

export async function render() {
  setBack(null);
  const page = el("div", "page");
  const head = el("div", "page-head");
  const title = el("div");
  title.append(el("h1", null, "Настройки"), el("p", "sub", "Подключение AI и CRM, сотрудники и данные"));
  head.append(title);
  page.append(head);

  const grid = el("div", "grid grid-2 stagger");
  page.append(grid);
  mount(page);

  // --- AI ---
  const ai = card("cpu", "violet", "Искусственный интеллект", "Расшифровка и разбор звонков");
  ai.append(
    kvRow("key", "", "Ключ Gemini", state.health?.has_key ? "подключён" : "не найден",
      state.health?.has_key ? el("span", "tag ok", "ок") : el("span", "tag bad", "добавьте в .env")),
    kvRow("cpu", "", "Модель анализа", state.health?.model || "—"),
    kvRow("bolt", "", "Модель расшифровки", "gemini-3.5-flash-lite", el("span", "tag info", "быстрая")),
  );
  grid.append(ai);

  // --- CRM ---
  const crmCard = card("actions", "sky", "CRM", "Куда уходят комментарии и задачи");
  const crmBody = el("div");
  crmCard.append(crmBody);
  grid.append(crmCard);

  // --- Кнопка в карточке сделки ---
  const embed = card("phone", "green", "Кнопка в карточке сделки",
    "Менеджер нажимает её в CRM — и разбор звонка попадает в сделку");
  const embedBody = el("div");
  embed.append(embedBody);
  grid.append(embed);

  // --- Данные ---
  const data = card("db", "amber", "Данные", "Демонстрационный отдел продаж");
  const dataBody = el("div", "col");
  data.append(dataBody);
  const demoRow = el("div", "row");
  const seed = el("button", "btn btn-primary");
  seed.append(icon("bolt", "i-sm"), el("span", null, "Загрузить демо-данные"));
  seed.addEventListener("click", async () => {
    seed.disabled = true;
    try {
      const result = await api.seedDemo();
      toast(`Добавлено ${result.calls} звонков по ${result.managers} менеджерам`);
      render();
    } catch (err) { toast(err.message); seed.disabled = false; }
  });
  const clear = el("button", "btn btn-danger");
  clear.append(icon("trash", "i-sm"), el("span", null, "Очистить демо"));
  clear.addEventListener("click", async () => {
    const body = el("p", "muted", "Все демонстрационные звонки и клиенты будут удалены. Ваши собственные звонки останутся.");
    const yes = el("button", "btn btn-danger", "Удалить демо-данные");
    yes.addEventListener("click", async () => {
      await api.clearDemo();
      toast("Демо-данные удалены");
      render();
    });
    modal("Очистить демо-данные?", body, [yes]);
  });
  demoRow.append(seed, clear);
  dataBody.append(demoRow);
  grid.append(data);

  // --- Сотрудники ---
  const people = card("users", "violet", "Сотрудники", "Роль переключается здесь, паролей пока нет");
  const list = el("div", "col");
  state.users.forEach((u) => {
    const btn = el("button", "user-card");
    btn.append(avatar(u));
    const info = el("span");
    info.style.flex = "1";
    info.append(el("b", null, u.name), el("span", null, u.title || (u.role === "head" ? "Руководитель" : "Менеджер")));
    btn.append(info);
    if (String(u.id) === String(currentUserId())) btn.append(el("span", "tag ok", "вы"));
    btn.addEventListener("click", async () => {
      setCurrentUserId(u.id);
      const session = await api.session();
      state.user = session.user;
      state.users = session.users;
      setUserUi();
      renderNav();
      render();
      toast(`Вы вошли как ${u.name}`);
    });
    list.append(btn);
  });
  people.append(list);
  grid.append(people);

  // Асинхронно подтягиваем статус CRM и кнопки
  try {
    const crm = await api.crmStatus();
    crmBody.replaceChildren(
      kvRow("actions", "", "Система", crm.title,
        crm.connected ? el("span", "tag ok", "подключена") : el("span", "tag warn", "демо-режим")),
      kvRow("shield", "", "Портал", crm.portal || "внутренняя демо-CRM"),
      kvRow("user", "", "Аккаунт", crm.user || "—"),
    );
  } catch (err) {
    crmBody.replaceChildren(el("p", "muted", "Статус CRM недоступен"));
  }

  const origin = location.origin;
  const isLocal = origin.includes("localhost") || origin.includes("127.0.0.1");
  const urlField = el("input");
  urlField.type = "text";
  urlField.value = isLocal ? "" : origin;
  urlField.placeholder = "https://ваш-адрес.example.com";
  const bindBtn = el("button", "btn btn-primary");
  bindBtn.append(icon("plus", "i-sm"), el("span", null, "Добавить кнопку в CRM"));
  bindBtn.addEventListener("click", async () => {
    const url = urlField.value.trim();
    if (!url.startsWith("https://")) return toast("Нужен публичный адрес по https");
    bindBtn.disabled = true;
    try {
      const result = await api.crmBindPlacement(url);
      toast(`Кнопка добавлена: ${result.placements.join(", ")}`);
      render();
    } catch (err) {
      toast(err.message);
      bindBtn.disabled = false;
    }
  });

  embedBody.replaceChildren();
  embedBody.append(el("p", "small muted",
    "Укажите публичный адрес приложения (туннель или сервер) и нажмите кнопку — в карточке сделки появится вкладка CallBrief."));
  const fieldRow = el("div", "row");
  fieldRow.style.marginTop = "14px";
  urlField.style.flex = "1";
  fieldRow.append(urlField, bindBtn);
  embedBody.append(fieldRow);

  try {
    const placement = await api.crmPlacement();
    if (placement.error) {
      embedBody.append(el("div", "alert alert-info", `Для кнопки нужно право «Встраивание» у вебхука Битрикса: ${placement.error}`));
    } else if (placement.items?.length) {
      const ok = el("div", "row");
      ok.style.marginTop = "14px";
      ok.append(el("span", "tag ok", `кнопка активна · ${placement.items.length}`),
        el("span", "small muted", placement.handler || ""));
      embedBody.append(ok);
    }
  } catch { /* необязательный блок */ }
}
