// Единственная точка обращения к backend. Все вьюхи ходят только сюда.

const USER_KEY = "callbrief.user_id";

export function currentUserId() {
  try { return localStorage.getItem(USER_KEY) || ""; } catch { return ""; }
}

export function setCurrentUserId(id) {
  try { localStorage.setItem(USER_KEY, String(id)); } catch { /* приватный режим */ }
}

async function request(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  const userId = currentUserId();
  if (userId) headers["X-User-Id"] = userId;
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  let res;
  try {
    res = await fetch(url, { ...options, headers });
  } catch {
    throw Object.assign(new Error("Сервер недоступен. Проверьте, что приложение запущено."), { code: "offline" });
  }
  let data = null;
  try { data = await res.json(); } catch { /* пустой ответ */ }
  if (!res.ok) {
    throw Object.assign(new Error((data && data.message) || `Ошибка сервера (${res.status}).`), {
      code: data && data.error,
      status: res.status,
    });
  }
  return data;
}

const qs = (params) => {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "" && v !== false) search.set(k, v);
  });
  const str = search.toString();
  return str ? `?${str}` : "";
};

export const api = {
  health: () => request("/api/health"),
  session: () => request("/api/session"),
  example: (n) => request(`/api/examples/${n}`),

  calls: (params) => request(`/api/calls${qs(params)}`),
  call: (id) => request(`/api/calls/${id}`),
  createCall: (payload) => request("/api/calls", { method: "POST", body: payload }),
  updateTranscript: (id, text) => request(`/api/calls/${id}/transcript`, { method: "PUT", body: { text } }),
  analyzeCall: (id) => request(`/api/calls/${id}/analyze`, { method: "POST" }),
  deleteCall: (id) => request(`/api/calls/${id}`, { method: "DELETE" }),
  uploadAudio: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/api/calls/upload", { method: "POST", body: form });
  },
  audioUrl: (id) => `/api/calls/${id}/audio`,

  stats: (params) => request(`/api/stats${qs(params)}`),
  team: (params) => request(`/api/team${qs(params)}`),
  insights: (params) => request(`/api/insights${qs(params)}`),
  coach: (params) => request(`/api/coach${qs(params)}`),
  best: (params) => request(`/api/best${qs(params)}`),
  clients: () => request("/api/clients"),
  client: (id) => request(`/api/clients/${id}`),
  actions: (params) => request(`/api/actions${qs(params)}`),
  updateAction: (id, payload) => request(`/api/actions/${id}`, { method: "PUT", body: { payload } }),
  skipAction: (id) => request(`/api/actions/${id}/skip`, { method: "POST" }),

  crmStatus: () => request("/api/crm/status"),
  crmDeals: (q) => request(`/api/crm/deals${qs({ q })}`),
  crmLink: (payload) => request("/api/crm/link", { method: "POST", body: payload }),
  crmApplyCall: (callId, dealId) => request(`/api/crm/apply-call/${callId}${qs({ deal_id: dealId })}`, { method: "POST" }),
  crmApplyAction: (actionId) => request(`/api/crm/apply/${actionId}`, { method: "POST" }),
  crmJournal: () => request("/api/crm/journal"),

  crmPlacement: () => request("/api/crm/placement"),
  crmBindPlacement: (url) => request("/api/crm/placement/bind", { method: "POST", body: { url } }),

  embedDeal: (dealId) => request(`/api/embed/deal/${dealId}`),

  seedDemo: () => request("/api/demo/seed", { method: "POST" }),
  clearDemo: () => request("/api/demo", { method: "DELETE" }),
};
