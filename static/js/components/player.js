// Плеер записи: волна из настоящего аудио, скорость, громкость, перемотка.

import { el, fmtTime, icon } from "../ui.js";

const WAVE_BARS = 150;
const SPEEDS = [0.8, 1, 1.2, 1.5, 2];
const MAX_DECODE = 40 * 1024 * 1024;

function fakePeaks(n, seed) {
  let x = seed;
  return Array.from({ length: n }, (_, i) => {
    x = (x * 9301 + 49297) % 233280;
    return 0.18 + 0.82 * Math.abs(Math.sin(i * 0.37 + seed)) * (x / 233280);
  });
}

async function computePeaks(url, n) {
  try {
    const response = await fetch(url);
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength > MAX_DECODE) return null;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    const decoded = await ctx.decodeAudioData(buffer);
    ctx.close();
    const data = decoded.getChannelData(0);
    const step = Math.max(1, Math.floor(data.length / n));
    const peaks = [];
    for (let i = 0; i < n; i++) {
      let max = 0;
      for (let j = i * step, end = Math.min(data.length, (i + 1) * step); j < end; j += 8) {
        const value = Math.abs(data[j]);
        if (value > max) max = value;
      }
      peaks.push(max);
    }
    const top = Math.max(...peaks) || 1;
    return peaks.map((p) => p / top);
  } catch {
    return null;
  }
}

export function createPlayer(audioUrl, { duration = 0, onTime } = {}) {
  const card = el("div", "card player");
  card.append(el("div", "card-title", "Аудиозапись"));

  const wave = el("div", "wave");
  const bars = el("div", "wave-bars");
  const headLine = el("div", "wave-head");
  wave.append(bars, headLine);

  const audio = el("audio");
  audio.preload = "metadata";
  audio.src = audioUrl;

  const controls = el("div", "controls");
  const playBtn = el("button", "play-btn");
  playBtn.append(icon("play"));
  const time = el("span", "time");
  const cur = el("span", null, "00:00");
  const dur = el("span", null, fmtTime(duration));
  time.append(cur, document.createTextNode(" / "), dur);

  const seek = el("input", "range seek");
  seek.type = "range";
  seek.min = 0; seek.max = 1000; seek.value = 0;

  const speedWrap = el("div", "menu-wrap");
  const speedBtn = el("button", "chip", "1.0x");
  const speedMenu = el("div", "menu up");
  speedMenu.hidden = true;
  SPEEDS.forEach((s) => {
    const item = el("button", null, `${s.toFixed(1)}x`);
    item.addEventListener("click", () => {
      audio.playbackRate = s;
      speedBtn.textContent = `${s.toFixed(1)}x`;
      speedMenu.hidden = true;
    });
    speedMenu.append(item);
  });
  speedBtn.addEventListener("click", (e) => { e.stopPropagation(); speedMenu.hidden = !speedMenu.hidden; });
  document.addEventListener("click", () => { speedMenu.hidden = true; });
  speedWrap.append(speedBtn, speedMenu);

  const muteBtn = el("button", "btn btn-ghost btn-icon");
  muteBtn.append(icon("volume"));
  const volume = el("input", "range vol");
  volume.type = "range";
  volume.min = 0; volume.max = 100; volume.value = 100;
  volume.style.setProperty("--p", "100%");

  controls.append(playBtn, time, seek, speedWrap, muteBtn, volume);
  card.append(wave, controls, audio);

  let seeking = false;

  function renderBars(peaks, placeholder) {
    bars.replaceChildren();
    peaks.forEach((p) => {
      const span = el("span");
      span.style.height = Math.max(6, Math.round(p * 100)) + "%";
      if (placeholder) span.style.opacity = ".5";
      bars.append(span);
    });
    update();
  }

  function update() {
    const total = audio.duration || duration;
    const known = total && isFinite(total);
    const position = known ? audio.currentTime / total : 0;
    cur.textContent = fmtTime(audio.currentTime || 0);
    if (known) dur.textContent = fmtTime(total);
    if (!seeking) seek.value = Math.round(position * 1000);
    seek.style.setProperty("--p", `${position * 100}%`);
    headLine.style.left = `calc(${position * 100}% - 1px)`;
    const children = bars.children;
    const filled = Math.round(position * children.length);
    for (let i = 0; i < children.length; i++) children[i].classList.toggle("played", i < filled);
    if (onTime) onTime(audio.currentTime || 0, !audio.paused);
  }

  function setPlayIcon() {
    playBtn.querySelector("use").setAttribute("href", audio.paused ? "#i-play" : "#i-pause");
  }

  playBtn.addEventListener("click", () => {
    if (audio.paused) audio.play().catch(() => {}); else audio.pause();
  });
  ["play", "pause", "ended"].forEach((ev) => audio.addEventListener(ev, setPlayIcon));
  ["timeupdate", "loadedmetadata", "seeked", "durationchange"].forEach((ev) => audio.addEventListener(ev, update));

  seek.addEventListener("input", () => {
    seeking = true;
    seek.style.setProperty("--p", `${seek.value / 10}%`);
  });
  seek.addEventListener("change", () => {
    const total = audio.duration || duration;
    if (total && isFinite(total)) audio.currentTime = (seek.value / 1000) * total;
    seeking = false;
  });
  wave.addEventListener("click", (e) => {
    const total = audio.duration || duration;
    if (!total || !isFinite(total)) return;
    const rect = wave.getBoundingClientRect();
    audio.currentTime = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)) * total;
  });
  volume.addEventListener("input", () => {
    audio.volume = volume.value / 100;
    audio.muted = Number(volume.value) === 0;
    volume.style.setProperty("--p", `${volume.value}%`);
    muteBtn.querySelector("use").setAttribute("href", audio.muted ? "#i-mute" : "#i-volume");
  });
  muteBtn.addEventListener("click", () => {
    audio.muted = !audio.muted;
    volume.value = audio.muted ? 0 : Math.round(audio.volume * 100);
    volume.style.setProperty("--p", `${volume.value}%`);
    muteBtn.querySelector("use").setAttribute("href", audio.muted ? "#i-mute" : "#i-volume");
  });

  renderBars(fakePeaks(WAVE_BARS, 11), true);
  computePeaks(audioUrl, WAVE_BARS).then((peaks) => { if (peaks) renderBars(peaks, false); });

  return {
    node: card,
    audio,
    seek(seconds, play = true) {
      audio.currentTime = seconds;
      if (play) audio.play().catch(() => {});
    },
    destroy() { audio.pause(); audio.removeAttribute("src"); },
  };
}
