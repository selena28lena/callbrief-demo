// Экран звонка: обработка, запись, транскрипция, разбор, оценки и действия.

import { api } from "../api.js";
import { mount, setBack } from "../app.js";
import { createPlayer } from "../components/player.js";
import { findLineIndex, flashLine, highlightPlaying, parseTranscript, renderTranscript } from "../components/transcript.js";
import { buildReport } from "../report.js";
import {
  copyText, downloadFile, el, errorBox, fmtDate, fmtTime, icoTile, icon, loading, modal,
  plural, severityBadge, tag, toast, WHO,
} from "../ui.js";

const LEVEL = { high: "Высокий", medium: "Средний", low: "Низкий" };
const LEVEL_ORDER = { high: 0, medium: 1, low: 2 };
const sortRisks = (list) => [...(list || [])].sort((a, b) => (LEVEL_ORDER[a.level] ?? 3) - (LEVEL_ORDER[b.level] ?? 3));

let player = null;
let lines = [];
let activeTab = "coach";
let pollTimer = null;
let switchTab = () => {};

function stopAll() {
  if (player) { player.destroy(); player = null; }
  clearTimeout(pollTimer);
}

/** Сделка, из карточки которой открыта панель: запись уйдёт именно в неё. */
function openedDealId() {
  return new URLSearchParams(location.search).get("deal") || "";
}

function savedToast(result) {
  toast(result.deal_id
    ? `Сохранено в ${result.provider}, сделка №${result.deal_id}: ${result.applied} ${plural(result.applied, ["действие", "действия", "действий"])}`
    : `Отправлено в ${result.provider}: ${result.applied}`);
}

async function applyToCrm(callId, button, reload) {
  button.disabled = true;
  try {
    savedToast(await api.crmApplyCall(callId, openedDealId()));
    reload();
  } catch (err) {
    button.disabled = false;
    // Звонок загружен не из карточки сделки — даём выбрать, куда его сохранить
    if (err.code === "no_deal") pickDeal(callId, reload);
    else toast(err.message);
  }
}

function pickDeal(callId, reload) {
  const box = el("div", "col");
  const search = el("input");
  search.type = "search";
  search.placeholder = "Поиск по названию сделки";
  const list = el("div", "col");
  box.append(el("p", "muted", "Звонок загружен не из карточки сделки. Выберите, куда сохранить комментарий и задачу."),
    search, list);

  const load = async (query) => {
    list.replaceChildren(loading("Ищу сделки…"));
    try {
      const data = await api.crmDeals(query);
      list.replaceChildren();
      if (!data.items.length) list.append(el("p", "muted", "Сделки не найдены."));
      data.items.slice(0, 12).forEach((deal) => {
        const btn = el("button", "user-card");
        const info = el("span");
        info.style.flex = "1";
        info.append(el("b", null, deal.title || `Сделка №${deal.id}`),
          el("span", null, `№${deal.id}${deal.stage ? " · " + deal.stage : ""}`));
        btn.append(info);
        btn.addEventListener("click", async () => {
          btn.disabled = true;
          try {
            await api.crmLink({ call_id: callId, deal_id: deal.id, deal_title: deal.title });
            savedToast(await api.crmApplyCall(callId, deal.id));
            close();
            reload();
          } catch (err) {
            toast(err.message);
            btn.disabled = false;
          }
        });
        list.append(btn);
      });
    } catch (err) {
      list.replaceChildren(el("div", "alert alert-error", err.message));
    }
  };
  let timer = null;
  search.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => load(search.value.trim()), 350);
  });
  const close = modal("В какую сделку сохранить?", box);
  load("");
}

function verifyTag(verified) {
  return verified ? tag("подтверждено", "check", "ok") : tag("цитата не найдена", "help", "warn");
}

function itemNode(title, tags, data, cls, onQuote) {
  const box = el("div", "item" + (cls ? " " + cls : ""));
  // Маркеры сверху — видно статус до чтения текста
  const meta = el("div", "item-meta");
  tags.filter(Boolean).forEach((t) => meta.append(t));
  if (typeof data.verified === "boolean") meta.append(verifyTag(data.verified));
  box.append(meta, el("div", "item-title", title));
  if (data.advice) {
    const advice = el("div", "item-advice");
    advice.append(icon("bulb", "i-sm"));
    const b = el("div");
    b.style.flex = "1";
    b.append(el("div", "label", "Что делать"), el("p", null, data.advice));
    advice.append(b);
    box.append(advice);
  }
  if (data.quote) {
    box.append(el("div", "quote", `«${data.quote}»`));
    const index = findLineIndex(lines, data.quote);
    if (index >= 0 && onQuote) {
      const link = el("button", "link");
      link.append(icon("play", "i-sm"), el("span", null, "Показать в расшифровке"));
      link.addEventListener("click", () => onQuote(index));
      box.append(link);
    }
  }
  return box;
}

function cardWithHead(iconName, tone, title, subtitle) {
  const card = el("div", "card");
  const head = el("div", "row");
  head.style.marginBottom = "16px";
  head.append(icoTile(iconName, tone, "lg"));
  const box = el("div");
  box.append(el("h2", null, title));
  if (subtitle) box.append(el("div", "small muted", subtitle));
  head.append(box);
  card.append(head);
  return card;
}

// ---------- Правая колонка ----------

function commentCard(data, onSave) {
  const { call, analysis, actions } = data;
  const draft = (actions || []).find((a) => a.type === "crm_comment");
  const text = draft?.payload?.text || analysis.crm_comment || analysis.summary || "—";
  const applied = draft?.status === "applied";

  const card = cardWithHead("text", "violet", "Комментарий для CRM",
    applied ? "Уже сохранён в карточке клиента" : "Готов к отправке — правки не нужны");
  card.append(el("div", "crm-comment", text));

  const row = el("div", "row");
  row.style.marginTop = "16px";
  const copy = el("button", "btn btn-ghost btn-sm");
  copy.append(icon("copy", "i-sm"), el("span", null, "Скопировать"));
  copy.addEventListener("click", async () => toast(await copyText(text) ? "Комментарий скопирован" : "Не удалось скопировать"));
  row.append(copy);

  const drafts = (actions || []).filter((a) => a.status === "draft");
  if (drafts.length) {
    const save = el("button", "btn btn-primary btn-sm");
    save.append(icon("check", "i-sm"), el("span", null, "Сохранить в CRM"));
    save.addEventListener("click", () => onSave(save));
    row.prepend(save);
  } else if (applied) {
    row.append(tag("в CRM", "check-c", "ok"));
  }
  card.append(row);
  return card;
}

function agreementsCard(analysis) {
  const card = cardWithHead("check-c", "green", "Договорённости и следующий шаг");
  const agreements = analysis.agreements || [];
  const steps = analysis.next_steps || [];

  const list = el("div", "mini-list");
  agreements.forEach((a) => {
    const item = el("div", "mini-item ok");
    item.append(el("div", "t", a.text));
    item.append(el("div", "s", `${WHO[a.who] || a.who}${a.verified ? "" : " · цитата не найдена"}`));
    list.append(item);
  });
  if (!agreements.length) {
    const item = el("div", "mini-item warn");
    item.append(el("div", "t", "Явных договорённостей в разговоре нет"));
    list.append(item);
  }
  card.append(el("div", "sec-title", "Договорённости"), list);

  card.append(el("div", "sec-title", "Следующий шаг"));
  const stepsList = el("div", "mini-list");
  if (steps.length) {
    steps.slice(0, 3).forEach((s) => {
      const item = el("div", "mini-item ok");
      item.append(el("div", "t", s.action));
      item.append(el("div", "s", `${s.owner || "ответственный не назван"} · ${s.deadline || "срок не назван"}`));
      stepsList.append(item);
    });
  } else {
    const item = el("div", "mini-item bad");
    item.append(el("div", "t", "Следующий шаг не был согласован"));
    item.append(el("div", "s", "Клиент ушёл без договорённости о следующем контакте — это первое, что стоит исправить."));
    stepsList.append(item);
  }
  card.append(stepsList);
  return card;
}

function risksCard(analysis) {
  const risks = sortRisks(analysis.risks);
  const card = cardWithHead("flag", risks.some((r) => r.level === "high") ? "red" : "amber",
    "Риски по сделке", "Что мешает довести клиента до покупки");
  if (!risks.length) {
    card.append(el("p", "muted", "Рисков в разговоре не выявлено."));
    return card;
  }
  const list = el("div", "mini-list");
  risks.forEach((r) => {
    const item = el("div", "mini-item " + (r.level === "high" ? "bad" : r.level === "medium" ? "warn" : "ok"));
    const head = el("div", "item-meta");
    head.style.marginBottom = "8px";
    head.append(tag(LEVEL[r.level] || r.level, "alert",
      r.level === "high" ? "bad" : r.level === "medium" ? "warn" : "ok"));
    item.append(head, el("div", "t", r.text));
    if (r.advice) item.append(el("div", "s", `Что делать: ${r.advice}`));
    list.append(item);
  });
  card.append(list);

  const questions = analysis.open_questions || [];
  if (questions.length) {
    card.append(el("div", "sec-title", "Осталось невыясненным"));
    const ul = el("ul", "bullets");
    questions.slice(0, 4).forEach((q) => ul.append(el("li", null, q)));
    card.append(ul);
  }
  return card;
}

// ---------- Обработка ----------

function processingView(data, reload) {
  const { call, job } = data;
  const card = cardWithHead("bolt", "violet", "AI обрабатывает звонок",
    call.title || "Запись загружена, обработка идёт на сервере");
  const stages = [
    { key: "transcribe", label: "Распознаю речь" },
    { key: "analyze", label: "Разбираю разговор" },
    { key: "done", label: "Готовлю действия для CRM" },
  ];
  const order = { transcribe: 0, analyze: 1, done: 2, error: 0 };
  const current = order[job?.stage ?? "transcribe"] ?? 0;
  const list = el("div", "progress-steps");
  stages.forEach((stage, index) => {
    const row = el("div", "pstep " + (index < current ? "done" : index === current ? "active" : ""));
    const mark = el("span", "mark");
    if (index < current) mark.append(icon("check", "i-sm"));
    row.append(mark, el("span", null, stage.label));
    list.append(row);
  });
  card.append(list);

  if (job?.stage === "error") {
    card.append(el("div", "alert alert-error", job.message || "Не удалось обработать звонок"));
  } else {
    const hint = el("div", "small muted");
    hint.style.marginTop = "16px";
    hint.textContent = job?.seconds
      ? `Идёт ${job.seconds} с · обычно занимает меньше минуты`
      : "Обычно занимает меньше минуты — можно не ждать на этой странице";
    card.append(hint);
  }

  if (call.transcript) {
    const preview = el("div", "card");
    preview.style.marginTop = "var(--gap)";
    preview.append(el("div", "sec-title", "Текст появляется по мере распознавания"));
    const box = el("div");
    box.style.cssText = "max-height:360px;overflow:auto";
    box.append(renderTranscript(parseTranscript(call.transcript), {}));
    preview.append(box);
    const wrap = el("div");
    wrap.append(card, preview);
    return wrap;
  }
  return card;
}

// ---------- Разбор ----------

function analyzedView(data, reload) {
  const { call, analysis, verification, scorecard, coach_items: coachItems, actions } = data;
  lines = parseTranscript(call.transcript);

  const grid = el("div", "grid grid-main");
  const left = el("div", "col");
  left.style.gap = "var(--gap)";
  const right = el("div", "col");
  right.style.gap = "var(--gap)";
  grid.append(left, right);

  let transcriptBox = null;
  if (call.audio_path) {
    player = createPlayer(api.audioUrl(call.id), {
      duration: call.duration || 0,
      onTime: (time) => { if (transcriptBox && activeTab === "transcript") highlightPlaying(transcriptBox, lines, time); },
    });
    left.append(player.node);
  }

  const tabsCard = el("div", "card tabs-card");
  const tabs = el("div", "tabs");
  const body = el("div", "tab-body");
  const foot = el("div", "tabs-foot");
  foot.append(el("span", null, "Расшифровка разговора текстовым файлом"));
  const txtBtn = el("button", "link", "Скачать .txt");
  txtBtn.addEventListener("click", () => downloadFile(`callbrief-${call.id}.txt`, call.transcript, "text/plain"));
  foot.append(txtBtn);
  tabsCard.append(tabs, body, foot);
  left.append(tabsCard);

  const goToLine = (index) => {
    switchTab("transcript");
    requestAnimationFrame(() => flashLine(body, index, lines[index]?.time, (sec) => player && player.seek(sec, false)));
  };

  // Главное (комментарий, договорённости, риски) всегда справа — вкладки только для длинных текстов
  const TABS = [
    { key: "coach", label: "Разбор тренера", count: coachItems?.length || 0 },
    { key: "transcript", label: "Расшифровка" },
    { key: "actions", label: "Что ушло в CRM", count: actions?.filter((a) => a.status === "draft").length || 0 },
  ];

  function renderBody() {
    body.replaceChildren();
    body.scrollTop = 0;

    if (activeTab === "transcript") {
      transcriptBox = renderTranscript(lines, { onSeek: player ? (sec) => player.seek(sec) : null });
      body.append(transcriptBox);
      return;
    }

    if (activeTab === "coach") {
      if (coachItems?.length) {
        body.append(el("div", "sec-title", `Разбор ошибок · ${coachItems.length} ${plural(coachItems.length, ["момент", "момента", "моментов"])}`));
        coachItems.forEach((item, index) => {
          const card = el("div", "coach-card");
          const head = el("div", "coach-head");
          head.append(icoTile("alert", "red", "sm"));
          const titleBox = el("div");
          titleBox.style.flex = "1";
          const titleRow = el("div", "row");
          titleRow.style.gap = "9px";
          titleRow.append(el("span", "coach-num", `#${index + 1}`), el("span", "strong", item.skill));
          titleBox.append(titleRow);
          if (item.time_sec != null) titleBox.append(el("div", "small muted", `момент разговора — ${fmtTime(item.time_sec)}`));
          head.append(titleBox);
          if (item.time_sec != null && player) {
            const play = el("button", "btn btn-ghost btn-sm");
            play.append(icon("play", "i-sm"), el("span", null, "Послушать"));
            play.addEventListener("click", () => player.seek(item.time_sec));
            head.append(play);
          }
          card.append(head);

          if (item.quote) {
            const row = el("div", "coach-step");
            row.append(icoTile("quote", "", "sm"));
            const b = el("div");
            b.style.flex = "1";
            b.append(el("div", "label", "Как это прозвучало"), el("div", "quote", `«${item.quote}»`));
            b.lastChild.style.marginTop = "6px";
            const index2 = findLineIndex(lines, item.quote);
            if (index2 >= 0) {
              const link = el("button", "link");
              link.append(icon("play", "i-sm"), el("span", null, "Показать в расшифровке"));
              link.addEventListener("click", () => goToLine(index2));
              b.append(link);
            }
            row.append(b);
            card.append(row);
          }
          [["Что произошло", item.what_happened, "text", ""],
           ["Почему это мешает продаже", item.why_problem, "alert", "red"],
           ["Как было бы лучше", item.better_action, "check-c", "green"]].forEach(([label, text, ic, tone]) => {
            if (!text) return;
            const row = el("div", "coach-step");
            row.append(icoTile(ic, tone, "sm"));
            const b = el("div");
            b.style.flex = "1";
            b.append(el("div", "label", label), el("p", null, text));
            row.append(b);
            card.append(row);
          });
          if (item.sample_phrase) {
            const row = el("div", "coach-step");
            row.append(icoTile("sparkle", "violet", "sm"));
            const b = el("div");
            b.style.flex = "1";
            b.append(el("div", "label", "Готовая фраза на следующий раз"), el("div", "phrase", item.sample_phrase));
            row.append(b);
            card.append(row);
          }
          body.append(card);
        });
      } else {
        body.append(el("p", "muted", "Грубых ошибок в этом разговоре тренер не нашёл."));
      }

      const advice = [...(scorecard?.general_advice || []), ...(analysis.recommendations || []).map((r) => r.text)];
      if (advice.length) {
        const title = el("div", "sec-title", "Советы на будущие звонки");
        title.style.marginTop = "26px";
        body.append(title);
        const list = el("ul", "bullets");
        advice.slice(0, 6).forEach((a) => list.append(el("li", null, a)));
        body.append(list);
      }
      return;
    }

    // Что уходит (или уже ушло) в карточку сделки
    const drafts = (actions || []).filter((a) => a.status === "draft");
    const applied = (actions || []).filter((a) => a.status === "applied");
    if (!drafts.length && !applied.length) {
      body.append(el("p", "muted", "Действия появятся после анализа."));
      return;
    }
    const META = {
      crm_comment: ["Комментарий в карточке клиента", "text"],
      task: ["Задача менеджеру", "actions"],
      next_contact: ["Следующий контакт", "calendar"],
      tags: ["Теги сделки", "star"],
    };
    const actionBox = (action, done) => {
      const [label, iconName] = META[action.type] || [action.type, "file"];
      const box = el("div", "item");
      const head = el("div", "row");
      head.append(icoTile(done ? "check-c" : iconName, done ? "green" : "violet", "sm"), el("div", "strong", label));
      if (done && action.external_id) head.append(tag(`ID ${action.external_id}`, "check", "ok"));
      box.append(head);
      const text = action.payload.text || action.payload.title || action.payload.when ||
                   (action.payload.tags || []).join(", ");
      if (text) {
        const p = el("p", "small muted", text);
        p.style.cssText = "margin-top:10px;white-space:pre-wrap";
        box.append(p);
      }
      return box;
    };

    if (drafts.length) {
      body.append(el("div", "sec-title", `Уйдёт в сделку${openedDealId() ? ` №${openedDealId()}` : ""}`));
      drafts.forEach((a) => body.append(actionBox(a, false)));
      const send = el("button", "btn btn-primary btn-lg");
      send.style.marginTop = "18px";
      send.append(icon("check", "i-sm"), el("span", null, "Сохранить всё в CRM"));
      send.addEventListener("click", () => applyToCrm(call.id, send, reload));
      body.append(send);
    }
    if (applied.length) {
      const title = el("div", "sec-title", "Уже сохранено в CRM");
      if (drafts.length) title.style.marginTop = "26px";
      body.append(title);
      applied.forEach((a) => body.append(actionBox(a, true)));
    }
  }

  switchTab = (key) => {
    activeTab = key;
    [...tabs.children].forEach((t) => t.classList.toggle("active", t.dataset.tab === key));
    renderBody();
  };

  TABS.forEach((t) => {
    const btn = el("button", "tab");
    btn.dataset.tab = t.key;
    btn.append(document.createTextNode(t.label));
    if (t.count) btn.append(el("span", "count", String(t.count)));
    btn.addEventListener("click", () => switchTab(t.key));
    tabs.append(btn);
  });

  right.append(
    commentCard(data, (btn) => applyToCrm(call.id, btn, reload)),
    agreementsCard(analysis),
    risksCard(analysis),
  );
  switchTab(TABS.some((t) => t.key === activeTab) ? activeTab : "coach");
  return grid;
}

export async function render(id) {
  stopAll();
  setBack("/calls");
  const page = el("div", "page");
  page.append(loading("Открываю звонок…"));
  mount(page);

  const reload = () => render(id);
  let data;
  try {
    data = await api.call(id);
  } catch (err) {
    page.replaceChildren(errorBox(err));
    return;
  }
  const { call, analysis, verification } = data;
  page.replaceChildren();

  const head = el("div", "page-head");
  const titleBox = el("div");
  const titleRow = el("div", "row");
  titleRow.append(icoTile(call.audio_path ? "wave" : "text", "sky", "lg"));
  const names = el("div");
  names.append(el("h1", null, call.client_company || call.client_name || call.title || "Звонок"));
  const meta = el("div", "row small muted");
  meta.style.marginTop = "8px";
  const metaItem = (iconName, text) => {
    const item = el("span", "row");
    item.style.gap = "7px";
    item.append(icon(iconName, "i-sm"), el("span", null, text));
    return item;
  };
  meta.append(metaItem("calendar", fmtDate(call.started_at)));
  if (call.duration) meta.append(metaItem("clock", fmtTime(call.duration)));
  meta.append(metaItem("user", call.user_name || "—"));
  if (call.crm_deal_id) meta.append(metaItem("actions", `сделка №${call.crm_deal_id}`));
  if (call.severity && ["analyzed", "saved"].includes(call.status)) meta.append(severityBadge(call.severity));
  names.append(meta);
  titleRow.append(names);
  titleBox.append(titleRow);
  head.append(titleBox);

  const actionsRow = el("div", "page-actions");
  if (analysis) {
    const drafts = (data.actions || []).filter((a) => a.status === "draft");
    if (drafts.length) {
      const save = el("button", "btn btn-primary");
      save.append(icon("check", "i-sm"), el("span", null, "Сохранить в CRM"));
      save.addEventListener("click", () => applyToCrm(call.id, save, reload));
      actionsRow.append(save);
    }
    const reportBtn = el("button", "btn");
    reportBtn.append(icon("download", "i-sm"), el("span", null, "Отчёт"));
    reportBtn.addEventListener("click", () => {
      downloadFile(`callbrief-report-${call.id}.txt`, buildReport(data), "text/plain");
      toast("Отчёт скачан");
    });
    const shareBtn = el("button", "btn");
    shareBtn.append(icon("share", "i-sm"), el("span", null, "Поделиться"));
    shareBtn.addEventListener("click", async () => {
      const text = buildReport(data);
      if (navigator.share) {
        try { await navigator.share({ title: "CallBrief", text }); return; } catch (e) { if (e.name === "AbortError") return; }
      }
      toast(await copyText(text) ? "Отчёт скопирован" : "Не удалось скопировать");
    });
    actionsRow.append(reportBtn, shareBtn);
  }
  if (data.can_manage) {
    const del = el("button", "btn btn-ghost btn-icon");
    del.append(icon("trash", "i-sm"));
    del.title = "Удалить звонок";
    del.addEventListener("click", () => {
      const body = el("p", "muted", "Звонок и его разбор будут удалены без возможности восстановления.");
      const yes = el("button", "btn btn-danger", "Удалить");
      yes.addEventListener("click", async () => {
        await api.deleteCall(call.id);
        toast("Звонок удалён");
        location.hash = "#/calls";
      });
      modal("Удалить звонок?", body, [yes]);
    });
    actionsRow.append(del);
  }
  head.append(actionsRow);
  page.append(head);

  const processing = ["transcribing", "analyzing"].includes(call.status);
  if (processing) {
    // Обновляем только карточку прогресса: страница не перерисовывается и не мигает
    const holder = el("div");
    holder.append(processingView(data, reload));
    page.append(holder);

    const tick = async () => {
      let fresh;
      try {
        fresh = await api.call(id);
      } catch {
        pollTimer = setTimeout(tick, 4000);   // сеть моргнула — просто ждём дальше
        return;
      }
      if (["transcribing", "analyzing"].includes(fresh.call.status)) {
        holder.replaceChildren(processingView(fresh, reload));
        pollTimer = setTimeout(tick, 2000);
      } else {
        reload();   // разбор готов или упал — показываем результат целиком, один раз
      }
    };
    pollTimer = setTimeout(tick, 2000);
  } else if (call.status === "failed") {
    page.append(el("div", "alert alert-error", data.job?.message || "Не удалось обработать звонок"));
    const retry = el("button", "btn btn-primary");
    retry.append(icon("bolt", "i-sm"), el("span", null, "Попробовать снова"));
    retry.addEventListener("click", async () => {
      await api.analyzeCall(call.id);
      reload();
    });
    page.append(retry);
  } else if (!analysis) {
    const card = cardWithHead("text", "violet", "Расшифровка готова", "Проверьте текст и запустите разбор");
    const area = el("textarea");
    area.value = call.transcript;
    area.style.minHeight = "340px";
    card.append(area);
    const btn = el("button", "btn btn-primary btn-lg");
    btn.style.marginTop = "16px";
    btn.append(icon("bolt", "i-sm"), el("span", null, "Проанализировать"));
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        if (area.value.trim() !== call.transcript) await api.updateTranscript(call.id, area.value.trim());
        await api.analyzeCall(call.id);
        reload();
      } catch (err) {
        toast(err.message);
        btn.disabled = false;
      }
    });
    card.append(btn);
    page.append(card);
  } else {
    page.append(analyzedView(data, reload));
  }

  return stopAll;
}
