-- CallBrief: схема базы. Создаётся идемпотентно при старте приложения.

CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'manager',   -- manager | head
    color        TEXT NOT NULL DEFAULT '#8f9bff',
    avatar       TEXT,
    title        TEXT,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clients (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    company      TEXT,
    phone        TEXT,
    crm_id       TEXT,                              -- id лида/сделки в CRM
    crm_kind     TEXT,                              -- lead | deal | contact
    stage        TEXT,
    industry     TEXT,
    status       TEXT,
    owner_id     INTEGER REFERENCES users(id),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone);

CREATE TABLE IF NOT EXISTS calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id    INTEGER REFERENCES clients(id),
    user_id      INTEGER REFERENCES users(id),
    title        TEXT NOT NULL DEFAULT 'Разговор',
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    duration     REAL,
    source       TEXT NOT NULL DEFAULT 'upload',    -- upload | text | example | crm | demo
    audio_path   TEXT,
    transcript   TEXT NOT NULL DEFAULT '',
    model        TEXT,
    outcome      TEXT,                              -- интерес | отказ | думает | встреча | ...
    risk_level   TEXT,                              -- high | medium | low | none
    severity     TEXT,                              -- ok | attention | critical
    severity_reason TEXT,
    score        REAL,                              -- общий балл scorecard
    has_next_step INTEGER NOT NULL DEFAULT 0,
    shared       INTEGER NOT NULL DEFAULT 1,        -- виден коллегам для обучения
    is_demo      INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'new',       -- new | transcribing | analyzing | analyzed | saved | failed
    job          TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_calls_user ON calls(user_id, started_at);
CREATE INDEX IF NOT EXISTS idx_calls_severity ON calls(severity);

CREATE TABLE IF NOT EXISTS analyses (
    call_id      INTEGER PRIMARY KEY REFERENCES calls(id) ON DELETE CASCADE,
    data         TEXT NOT NULL,                     -- json: резюме, потребности, возражения, риски и т.д.
    confirmed    INTEGER NOT NULL DEFAULT 0,
    total        INTEGER NOT NULL DEFAULT 0,
    model        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scorecards (
    call_id      INTEGER PRIMARY KEY REFERENCES calls(id) ON DELETE CASCADE,
    data         TEXT NOT NULL,                     -- json: критерии, сильные стороны, зона роста
    total        REAL NOT NULL DEFAULT 0,
    model        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS coach_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id      INTEGER NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    user_id      INTEGER REFERENCES users(id),
    time_sec     REAL,
    skill        TEXT NOT NULL,                     -- выявление потребности | работа с ценой | ...
    what_happened TEXT NOT NULL,
    why_problem  TEXT NOT NULL,
    better_action TEXT NOT NULL,
    sample_phrase TEXT,
    quote        TEXT,
    verified     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_coach_user ON coach_items(user_id, skill);

CREATE TABLE IF NOT EXISTS best_moments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id      INTEGER NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    user_id      INTEGER REFERENCES users(id),
    skill        TEXT NOT NULL,
    score        REAL,
    time_sec     REAL,
    quote        TEXT NOT NULL,
    why_good     TEXT,
    pinned       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS patterns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    skill        TEXT NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL,
    evidence     TEXT NOT NULL DEFAULT '[]',        -- json: [{call_id, time_sec, quote}]
    period_days  INTEGER NOT NULL DEFAULT 30,
    status       TEXT NOT NULL DEFAULT 'open',      -- open | improving | closed
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trainings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    pattern_id   INTEGER REFERENCES patterns(id),
    call_id      INTEGER REFERENCES calls(id),
    kind         TEXT NOT NULL DEFAULT 'reply',     -- reply | roleplay
    scenario     TEXT NOT NULL,                     -- json
    dialog       TEXT NOT NULL DEFAULT '[]',        -- json
    score        REAL,
    feedback     TEXT,                              -- json
    status       TEXT NOT NULL DEFAULT 'new',       -- new | done
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS actions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id      INTEGER NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    type         TEXT NOT NULL,                     -- crm_comment | task | next_contact | follow_up | tags | deal_update | escalate
    payload      TEXT NOT NULL,                     -- json
    status       TEXT NOT NULL DEFAULT 'draft',     -- draft | applied | failed | skipped
    external_id  TEXT,
    error        TEXT,
    applied_at   TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_actions_call ON actions(call_id);

CREATE TABLE IF NOT EXISTS insights (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scope        TEXT NOT NULL DEFAULT 'team',      -- team | user
    user_id      INTEGER REFERENCES users(id),
    period_days  INTEGER NOT NULL DEFAULT 30,
    kind         TEXT NOT NULL,                     -- blockers | objections | losing | questions | funnel | best_phrases | promises | repeats
    title        TEXT NOT NULL,
    body         TEXT NOT NULL,
    evidence     TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key          TEXT PRIMARY KEY,
    value        TEXT NOT NULL
);
