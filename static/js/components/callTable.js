// Таблица звонков — общая для главной, списка звонков и команды.

import { avatar, el, emptyState, fmtDateShort, fmtTime, icon, RISK, severityBadge, tag } from "../ui.js";

export function callReason(call) {
  if (call.severity_reason) return call.severity_reason;
  if (!call.status || call.status === "new") return "Ещё не проанализирован";
  return "Замечаний нет";
}

/** Компактный список звонков — для узких колонок дашборда. */
export function callList(rows, { limit = 6, onOpen } = {}) {
  if (!rows.length) return emptyState("Звонков пока нет", "phone");
  const box = el("div", "col");
  box.style.gap = "2px";
  rows.slice(0, limit).forEach((call) => {
    const row = el("a", "row");
    row.href = `#/calls/${call.id}`;
    row.style.cssText = "gap:14px;padding:13px 10px;border-radius:12px;transition:background .2s";
    row.addEventListener("mouseenter", () => { row.style.background = "rgba(148,163,184,.07)"; });
    row.addEventListener("mouseleave", () => { row.style.background = ""; });
    if (onOpen) row.addEventListener("click", (e) => { e.preventDefault(); onOpen(call); });

    const tone = call.severity === "critical" ? "red" : call.severity === "attention" ? "amber" : "green";
    const tile = el("span", "ico-tile sm " + tone);
    tile.append(icon(call.audio_path ? "wave" : "text", "i-sm"));
    row.append(tile);

    const info = el("div");
    info.style.cssText = "flex:1;min-width:0";
    info.append(el("div", "t-main", call.client_company || call.client_name || call.title));
    info.append(el("div", "t-sub clamp-2", callReason(call)));
    row.append(info);

    const right = el("div");
    right.style.cssText = "text-align:right;white-space:nowrap";
    right.append(severityBadge(call.severity));
    right.append(el("div", "t-sub", fmtDateShort(call.started_at)));
    row.append(right);
    box.append(row);
  });
  return box;
}

export function callTable(rows, { compact = false, showManager = true, onOpen } = {}) {
  if (!rows.length) return emptyState("Звонков пока нет", "phone");

  const table = el("table", "table");
  const head = el("thead");
  const headRow = el("tr");
  const columns = compact
    ? ["Клиент", "Что не так", "Критичность"]
    : ["Клиент", showManager ? "Менеджер" : "Дата", "Что не так", "Риск", "Шаг", "Дата"];
  columns.forEach((c) => headRow.append(el("th", null, c)));
  head.append(headRow);
  table.append(head);

  const body = el("tbody");
  rows.forEach((call) => {
    const tr = el("tr");
    tr.addEventListener("click", () => (onOpen ? onOpen(call) : (location.hash = `#/calls/${call.id}`)));

    const first = el("td");
    const firstRow = el("div", "row");
    firstRow.style.gap = "12px";
    const tile = el("span", "ico-tile sm " + (call.audio_path || call.source === "demo" ? "sky" : "violet"));
    tile.append(icon(call.audio_path || call.source === "demo" ? "wave" : "text", "i-sm"));
    const titleBox = el("div");
    titleBox.style.minWidth = "0";
    titleBox.append(el("div", "t-main", call.client_company || call.client_name || call.title || "Разговор"));
    const sub = [call.client_name && call.client_company ? call.client_name : null,
                 call.duration ? fmtTime(call.duration) : null].filter(Boolean).join(" · ");
    if (sub) titleBox.append(el("div", "t-sub", sub));
    firstRow.append(tile, titleBox);
    first.append(firstRow);
    tr.append(first);

    if (!compact) {
      const who = el("td");
      if (showManager) {
        const box = el("span", "who");
        box.append(avatar(call, "sm"), el("span", null, call.user_name || "—"));
        who.append(box);
      } else {
        who.append(el("span", "t-sub", fmtDateShort(call.started_at)));
      }
      tr.append(who);
    }

    const reason = el("td");
    reason.append(el("div", "small muted clamp-2", callReason(call)));
    tr.append(reason);

    if (compact) {
      const sev = el("td");
      sev.append(severityBadge(call.severity));
      tr.append(sev);
    } else {
      const risk = el("td");
      risk.append(tag(RISK[call.risk_level] || "—", "alert",
        call.risk_level === "high" ? "bad" : call.risk_level === "medium" ? "warn" : "plain"));
      tr.append(risk);

      const step = el("td");
      step.append(call.has_next_step ? tag("есть", "check", "ok") : tag("нет", "alert", "warn"));
      tr.append(step);

      tr.append(el("td", "small muted nowrap", fmtDateShort(call.started_at)));
    }
    body.append(tr);
  });
  table.append(body);
  return table;
}
