// Действия после звонка: очередь «проверил → сохранил в CRM → следующий».

import { api } from "../api.js";
import { mount, setBack } from "../app.js";
import { avatar, el, emptyState, errorBox, fmtDateShort, icoTile, icon, loading, modal, severityBadge, tag, toast } from "../ui.js";

const TYPE_META = {
  crm_comment: { title: "Комментарий в CRM", icon: "text", tone: "sky" },
  task: { title: "Задача менеджеру", icon: "actions", tone: "violet" },
  next_contact: { title: "Следующий контакт", icon: "calendar", tone: "green" },
  tags: { title: "Теги сделки", icon: "star", tone: "amber" },
  follow_up: { title: "Письмо клиенту", icon: "share", tone: "sky" },
  deal_update: { title: "Обновление сделки", icon: "steps", tone: "violet" },
};

function actionBlock(action, onChange) {
  const meta = TYPE_META[action.type] || { title: action.type, icon: "file", tone: "" };
  const box = el("div", "item");
  const head = el("div", "row");
  head.append(icoTile(meta.icon, meta.tone, "sm"));
  const titleBox = el("div");
  titleBox.style.flex = "1";
  titleBox.append(el("div", "strong", meta.title));
  head.append(titleBox);
  head.append(tag("готово", "check", "ok"));
  box.append(head);

  if (action.type === "crm_comment") {
    const area = el("textarea");
    area.value = action.payload.text || "";
    area.style.minHeight = "170px";
    area.style.marginTop = "14px";
    area.addEventListener("change", () => onChange({ ...action.payload, text: area.value }));
    box.append(area);
  } else if (action.type === "task" || action.type === "next_contact") {
    const row = el("div", "row");
    row.style.marginTop = "12px";
    const input = el("input");
    input.type = "text";
    input.value = action.payload.title || action.payload.when || "";
    input.style.flex = "1";
    input.addEventListener("change", () => onChange(
      action.type === "task" ? { ...action.payload, title: input.value } : { ...action.payload, when: input.value }));
    row.append(input);
    if (action.payload.deadline) row.append(tag(action.payload.deadline, "clock", "warn"));
    box.append(row);
  } else if (action.type === "tags") {
    const row = el("div", "row");
    row.style.marginTop = "12px";
    (action.payload.tags || []).forEach((t) => row.append(tag(t, "star", "amber")));
    box.append(row);
  }
  return box;
}

async function pickDeal(callId, clientTitle) {
  const body = el("div", "col");
  const search = el("div", "search-box");
  const input = el("input");
  input.type = "search";
  input.placeholder = "Поиск сделки в CRM";
  search.append(icon("search"), input);
  const list = el("div", "col");
  list.style.maxHeight = "320px";
  list.style.overflow = "auto";
  body.append(el("p", "muted", `Свяжите звонок «${clientTitle}» со сделкой — туда уйдут комментарий и задача.`), search, list);

  let close;
  const load = async (query = "") => {
    list.replaceChildren(loading("Загружаю сделки…"));
    try {
      const data = await api.crmDeals(query);
      list.replaceChildren();
      if (!data.items.length) list.append(el("p", "muted", "Сделки не найдены"));
      data.items.forEach((deal) => {
        const row = el("button", "user-card");
        row.append(icoTile("actions", "sky", "sm"));
        const info = el("span");
        info.style.flex = "1";
        info.append(el("b", null, deal.title), el("span", null, `ID ${deal.id} · ${deal.stage || ""}`));
        row.append(info);
        row.addEventListener("click", async () => {
          await api.crmLink({ call_id: callId, deal_id: deal.id, deal_title: deal.title });
          toast(`Звонок связан со сделкой «${deal.title}»`);
          close();
          location.reload();
        });
        list.append(row);
      });
    } catch (err) {
      list.replaceChildren(errorBox(err));
    }
  };
  let timer;
  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => load(input.value.trim()), 400); });
  close = modal("Выберите сделку в CRM", body);
  load();
}

function callCard(group, crm, refresh) {
  const card = el("div", "card");
  const head = el("div", "row-between");
  const left = el("div", "row");
  left.append(icoTile("phone", group.severity === "critical" ? "red" : group.severity === "attention" ? "amber" : "green", "lg"));
  const info = el("div");
  info.append(el("h2", null, group.client));
  const sub = el("div", "row small muted");
  sub.style.marginTop = "6px";
  sub.append(el("span", null, group.contact || ""), el("span", null, "·"),
    el("span", null, fmtDateShort(group.started_at)), el("span", null, "·"),
    el("span", null, group.user_name || ""));
  info.append(sub);
  left.append(info);
  head.append(left);
  const right = el("div", "row");
  right.append(severityBadge(group.severity));
  const open = el("a", "btn btn-ghost btn-sm");
  open.href = `#/calls/${group.call_id}`;
  open.append(icon("arrow-r", "i-sm"), el("span", null, "Открыть разбор"));
  right.append(open);
  head.append(right);
  card.append(head);

  const items = el("div", "grid grid-2");
  items.style.marginTop = "18px";
  group.actions.forEach((action) => {
    items.append(actionBlock(action, (payload) => api.updateAction(action.id, payload).catch(() => {})));
  });
  card.append(items);

  const foot = el("div", "row-between");
  foot.style.marginTop = "18px";
  const status = el("div", "row small muted");
  if (group.crm_id) {
    status.append(icon("check-c", "i-sm"), el("span", null, `Сделка №${group.crm_id} в ${crm.title}`));
  } else {
    const linkBtn = el("button", "link");
    linkBtn.append(icon("plus", "i-sm"), el("span", null, "Связать со сделкой в CRM"));
    linkBtn.addEventListener("click", () => pickDeal(group.call_id, group.client));
    status.append(linkBtn);
  }
  foot.append(status);

  const buttons = el("div", "row");
  const skip = el("button", "btn btn-ghost btn-sm", "Пропустить");
  skip.addEventListener("click", async () => {
    await Promise.all(group.actions.map((a) => api.skipAction(a.id)));
    toast("Звонок пропущен");
    refresh();
  });
  const save = el("button", "btn btn-primary");
  save.append(icon("check", "i-sm"), el("span", null, `Сохранить всё в ${crm.title}`));
  save.addEventListener("click", async () => {
    save.disabled = true;
    save.replaceChildren(el("span", "spinner spinner-sm"), el("span", null, "Отправляю в CRM…"));
    try {
      const result = await api.crmApplyCall(group.call_id);
      const failed = result.results.filter((r) => r.status === "failed");
      if (failed.length) toast(`Часть действий не прошла: ${failed[0].error}`);
      else toast(`Готово: ${result.applied} действий ушло в ${result.provider}`);
      refresh();
    } catch (err) {
      toast(err.message);
      save.disabled = false;
      save.replaceChildren(icon("check", "i-sm"), el("span", null, `Сохранить всё в ${crm.title}`));
    }
  });
  buttons.append(skip, save);
  foot.append(buttons);
  card.append(foot);
  return card;
}

export async function render() {
  setBack(null);
  const page = el("div", "page");
  const head = el("div", "page-head");
  const title = el("div");
  title.append(el("h1", null, "Действия после звонка"),
    el("p", "sub", "AI уже подготовил комментарий, задачу и следующий контакт. Проверьте и сохраните одной кнопкой."));
  head.append(title);
  const crmPill = el("span", "pill");
  crmPill.append(el("span", "dot"), el("span", null, "Проверяю CRM…"));
  head.append(crmPill);
  page.append(head);

  const list = el("div", "col stagger");
  list.style.gap = "var(--gap)";
  page.append(list);
  list.append(loading("Загружаю очередь…"));
  mount(page);

  const refresh = () => render();
  let crm = { title: "CRM" };
  try {
    crm = await api.crmStatus();
    crmPill.className = "pill " + (crm.connected && crm.ok !== false ? "ok" : "warn");
    crmPill.replaceChildren(el("span", "dot"),
      el("span", null, crm.connected ? `${crm.title}${crm.portal ? " · " + crm.portal : ""}` : "CRM не подключена"));
  } catch {
    crmPill.className = "pill bad";
  }

  try {
    const data = await api.actions({ status: "draft" });
    list.replaceChildren();
    if (!data.items.length) {
      list.append(emptyState("Очередь пуста — все звонки сохранены в CRM", "check-c"));
      return;
    }
    data.items.forEach((group) => list.append(callCard(group, crm, refresh)));
  } catch (err) {
    list.replaceChildren(errorBox(err));
  }
}
