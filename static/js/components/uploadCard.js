// Карточка загрузки звонка: перетаскивание аудио, текст, примеры.

import { api } from "../api.js";
import { el, fmtSize, icoTile, icon, toast } from "../ui.js";

const AUDIO_EXT = ["mp3", "wav", "m4a", "ogg"];

export function uploadCard(onDone) {
  const card = el("div", "card");
  const head = el("div", "card-head");
  const row = el("div", "row");
  row.append(icoTile("cloud", "sky", "sm"), el("h2", null, "Новый звонок"));
  head.append(row);
  card.append(head);

  const drop = el("label", "drop");
  const input = el("input");
  input.type = "file";
  input.accept = ".mp3,.wav,.m4a,.ogg,audio/*";
  drop.append(input, icon("cloud", "i-xl"), el("strong", null, "Перетащите запись разговора"),
    el("span", null, "или нажмите, чтобы выбрать файл"), el("small", null, "MP3, WAV, M4A, OGG · до 200 МБ"));

  const steps = el("div", "card progress-steps");
  steps.hidden = true;
  steps.style.marginTop = "14px";
  const stepNodes = ["Загружаю файл", "Распознаю речь", "Разбираю разговор"].map((label) => {
    const node = el("div", "pstep");
    const mark = el("span", "mark");
    node.append(mark, el("span", null, label));
    steps.append(node);
    return node;
  });
  const timer = el("div", "small dim");
  timer.style.marginTop = "6px";
  steps.append(timer);

  const textArea = el("textarea");
  textArea.placeholder = "…или вставьте готовый текст разговора";
  textArea.style.minHeight = "110px";
  textArea.style.marginTop = "16px";

  const actions = el("div", "row");
  actions.style.marginTop = "16px";
  const analyzeBtn = el("button", "btn btn-primary");
  analyzeBtn.append(el("span", null, "Разобрать текст"), icon("arrow-r", "i-sm"));
  actions.append(analyzeBtn);
  const examples = el("div", "chips");
  [["Успешный", 1], ["Размытый", 2], ["Длинный", 3]].forEach(([label, n]) => {
    const chip = el("button", "chip", label);
    chip.addEventListener("click", async () => {
      const data = await api.example(n);
      textArea.value = data.text;
      textArea.dataset.title = data.title;
      toast(`Загружен ${data.title.toLowerCase()}`);
    });
    examples.append(chip);
  });
  actions.append(examples);

  let tick;
  function setStep(index) {
    stepNodes.forEach((node, i) => {
      node.classList.toggle("done", i < index);
      node.classList.toggle("active", i === index);
      if (i < index) node.querySelector(".mark").replaceChildren(icon("check", "i-sm"));
    });
  }
  function busy(on, fromStep = 0) {
    steps.hidden = !on;
    drop.hidden = on;
    analyzeBtn.disabled = on;
    clearInterval(tick);
    if (on) {
      setStep(fromStep);
      const started = Date.now();
      const update = () => { timer.textContent = `прошло ${Math.round((Date.now() - started) / 1000)} с`; };
      update();
      tick = setInterval(update, 1000);
    }
  }

  async function uploadFile(file) {
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    if (!AUDIO_EXT.includes(ext)) return toast("Поддерживаются mp3, wav, m4a и ogg");
    busy(true, 0);
    timer.textContent = `${file.name} · ${fmtSize(file.size)}`;
    try {
      setTimeout(() => setStep(1), 800);
      const res = await api.uploadAudio(file);
      setStep(2);
      onDone(res.id);
    } catch (err) {
      toast(err.message);
      busy(false);
    }
  }

  input.addEventListener("change", () => { if (input.files[0]) uploadFile(input.files[0]); });
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) uploadFile(f); });

  analyzeBtn.addEventListener("click", async () => {
    const text = textArea.value.trim();
    if (text.length < 30) return toast("Вставьте текст разговора");
    busy(true, 2);
    try {
      const res = await api.createCall({ text, title: textArea.dataset.title || "Разговор", source: "text" });
      onDone(res.id);
    } catch (err) {
      toast(err.message);
      busy(false);
    }
  });

  card.append(drop, steps, textArea, actions);
  return card;
}
