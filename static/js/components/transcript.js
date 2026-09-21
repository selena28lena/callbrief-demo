// Разбор транскрипта на реплики и его отрисовка с метками времени.

import { el, normalize } from "../ui.js";

const LINE_RE = /^\s*(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*[-–—]?\s*)?(менеджер|клиент)\s*:\s*(.*)$/i;
const toSec = (value) => value.split(":").reduce((acc, part) => acc * 60 + Number(part), 0);

export function parseTranscript(text) {
  const lines = [];
  for (const raw of String(text || "").split(/\r?\n/)) {
    const trimmed = raw.trim();
    if (!trimmed) continue;
    const match = trimmed.match(LINE_RE);
    if (match) {
      lines.push({
        time: match[1] ? toSec(match[1]) : null,
        timeLabel: match[1] || null,
        speaker: match[2].toLowerCase() === "менеджер" ? "manager" : "client",
        text: match[3],
      });
    } else if (lines.length) {
      lines[lines.length - 1].text += " " + trimmed;
    } else {
      lines.push({ time: null, timeLabel: null, speaker: null, text: trimmed });
    }
  }
  lines.forEach((line) => { line.norm = normalize(line.text); });
  return lines;
}

export function findLineIndex(lines, quote) {
  const needle = normalize(quote);
  if (!needle || !lines.length) return -1;
  const exact = lines.findIndex((line) => ` ${line.norm} `.includes(` ${needle} `));
  if (exact >= 0) return exact;
  const words = [...new Set(needle.split(" "))];
  let best = -1;
  let bestScore = 0;
  lines.forEach((line, index) => {
    const lineWords = new Set(line.norm.split(" "));
    const score = words.filter((w) => lineWords.has(w)).length / words.length;
    if (score > bestScore) { bestScore = score; best = index; }
  });
  return bestScore >= 0.6 ? best : -1;
}

export function renderTranscript(lines, { onSeek, markers = [] } = {}) {
  const box = el("div", "transcript");
  if (!lines.length) {
    box.append(el("p", "muted", "Текст разговора пуст."));
    return box;
  }
  const markerByLine = new Map(markers.map((m) => [m.lineIndex, m]));
  lines.forEach((line, index) => {
    const row = el("div", "tline" + (line.speaker ? " " + line.speaker : ""));
    row.dataset.index = index;

    let timeNode;
    if (line.timeLabel && onSeek) {
      timeNode = el("button", "t", line.timeLabel);
      timeNode.title = "Воспроизвести с этого места";
      timeNode.addEventListener("click", () => onSeek(line.time));
    } else {
      timeNode = el("span", "t", line.timeLabel || String(index + 1).padStart(2, "0"));
    }

    const content = el("div");
    content.append(
      el("div", "who-label", line.speaker === "manager" ? "Менеджер" : line.speaker === "client" ? "Клиент" : "Реплика"),
      el("div", "txt", line.text)
    );
    const marker = markerByLine.get(index);
    if (marker) {
      const badge = el("span", "tag " + (marker.cls || "ai"), marker.label);
      badge.style.marginTop = "8px";
      content.append(badge);
    }
    row.append(timeNode, el("span", "dot"), content);
    box.append(row);
  });
  return box;
}

export function flashLine(container, index, seconds, onSeek) {
  const row = container.querySelector(`[data-index="${index}"]`);
  if (!row) return;
  row.scrollIntoView({ block: "center", behavior: "smooth" });
  row.classList.add("flash");
  setTimeout(() => row.classList.remove("flash"), 2200);
  if (seconds != null && onSeek) onSeek(seconds, false);
}

export function highlightPlaying(container, lines, time) {
  let active = -1;
  lines.forEach((line, index) => { if (line.time != null && line.time <= time + 0.2) active = index; });
  container.querySelectorAll(".tline.playing").forEach((row) => row.classList.remove("playing"));
  if (active >= 0) {
    const row = container.querySelector(`[data-index="${active}"]`);
    if (row) row.classList.add("playing");
  }
  return active;
}
