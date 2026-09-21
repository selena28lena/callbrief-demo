// Сборка отчёта по звонку обычным текстом: такой файл открывается на любом компьютере.

import { fmtDate, fmtTime, WHO } from "./ui.js";

const LEVEL = { high: "Высокий", medium: "Средний", low: "Низкий" };
const RULE = "=".repeat(58);

function head(lines, title) {
  lines.push("", title.toUpperCase(), "-".repeat(title.length), "");
}

export function buildReport({ call, analysis, scorecard, coach_items: coachItems }) {
  const lines = [];
  lines.push(RULE, "CALLBRIEF — РАЗБОР ЗВОНКА", RULE, "");
  lines.push(`Клиент:       ${call.client_company || call.client_name || call.title || "—"}`);
  lines.push(`Менеджер:     ${call.user_name || "—"}`);
  lines.push(`Дата:         ${fmtDate(call.started_at)}`);
  if (call.duration) lines.push(`Длительность: ${fmtTime(call.duration)}`);
  if (call.crm_deal_id) lines.push(`Сделка в CRM: №${call.crm_deal_id}`);
  if (call.severity_reason) lines.push(`Что не так:   ${call.severity_reason}`);

  head(lines, "Комментарий для CRM");
  lines.push(analysis.crm_comment || analysis.summary || "—");

  head(lines, "Договорённости");
  if (!analysis.agreements?.length) lines.push("Явных договорённостей нет.");
  (analysis.agreements || []).forEach((a) => {
    lines.push(`• ${a.text} (${WHO[a.who] || a.who})`, `  Цитата: «${a.quote}»`);
  });

  head(lines, "Следующий шаг");
  if (!analysis.next_steps?.length) lines.push("Следующий шаг не был согласован.");
  (analysis.next_steps || []).forEach((s) => {
    lines.push(`• ${s.action}`, `  Ответственный: ${s.owner || "не указан"} · Срок: ${s.deadline || "не назван"}`);
  });

  head(lines, "Риски");
  if (!analysis.risks?.length) lines.push("Рисков не выявлено.");
  (analysis.risks || []).forEach((r) => {
    lines.push(`• [${LEVEL[r.level] || r.level}] ${r.text}`);
    if (r.advice) lines.push(`  Что делать: ${r.advice}`);
    lines.push(`  Цитата: «${r.quote}»`);
  });

  if (coachItems?.length) {
    head(lines, "Разбор тренера");
    coachItems.forEach((item, i) => {
      lines.push(`${i + 1}. ${item.skill}${item.time_sec != null ? ` (${fmtTime(item.time_sec)})` : ""}`);
      if (item.quote) lines.push(`   Прозвучало: «${item.quote}»`);
      if (item.what_happened) lines.push(`   Что произошло: ${item.what_happened}`);
      if (item.why_problem) lines.push(`   Почему мешает: ${item.why_problem}`);
      if (item.better_action) lines.push(`   Как лучше: ${item.better_action}`);
      if (item.sample_phrase) lines.push(`   Готовая фраза: «${item.sample_phrase}»`);
      lines.push("");
    });
  }

  const advice = [...(scorecard?.general_advice || []), ...(analysis.recommendations || []).map((r) => r.text)];
  if (advice.length) {
    head(lines, "Советы на будущие звонки");
    advice.forEach((a) => lines.push(`• ${a}`));
  }

  if (analysis.open_questions?.length) {
    head(lines, "Осталось невыясненным");
    analysis.open_questions.forEach((q) => lines.push(`• ${q}`));
  }

  lines.push("", RULE, "Сформировано CallBrief. Используйте только обезличенные данные.", "");
  return lines.join("\n");
}
