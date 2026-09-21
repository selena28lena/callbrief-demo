"""Агрегаты для дашбордов, команды, тренера и инсайтов. Считаются по базе, без AI."""

from collections import Counter, defaultdict

from .. import db, store

SEVERITIES = ("ok", "attention", "critical")

OBJECTION_LABELS = {
    "цена": "Дорого",
    "конкурент": "Ушёл к конкуренту",
    "полномочия": "Нет выхода на ЛПР",
    "время": "Нет времени",
    "доверие": "Не понял ценность",
    "потребность": "Продукт не нужен",
    "бюджет": "Нет бюджета",
    "модель": "Не устроили условия",
}

# Причина отказа для звонков без структурированных возражений — по словам из рисков
REASON_KEYWORDS = [
    ("цена", ("дорог", "цена", "цену", "стоимост", "скидк")),
    ("конкурент", ("конкурент", "другой поставщик", "уже работа", "у других")),
    ("полномочия", ("лпр", "директор", "руководител", "не принимает решени", "посоветова")),
    ("бюджет", ("бюджет", "нет денег", "нет средств", "финанс")),
    ("потребность", ("не нужн", "не интересн", "не подходит", "не наш профиль", "не связан")),
    ("модель", ("франшиз", "услови", "договор", "схем", "модел")),
    ("время", ("некогда", "нет времени", "занят", "позже", "перезвон")),
    ("доверие", ("не понял", "не понимает", "не разобрал", "сомнева")),
]


def _reason_key(row: dict) -> str:
    """Определяет причину отказа: сначала по возражениям, иначе по тексту рисков."""
    data = row.get("data") or {}
    objections = data.get("objections") or []
    if objections:
        return objections[0].get("type", "другое")
    text = " ".join([
        *(r.get("text", "") for r in data.get("risks", [])),
        row.get("severity_reason") or "",
        data.get("summary", ""),
    ]).lower()
    for key, words in REASON_KEYWORDS:
        if any(w in text for w in words):
            return key
    return "другое"


REJECTION_COLORS = ["#f87171", "#fbbf24", "#818cf8", "#34d399", "#22d3ee", "#a78bfa"]


def _analyses(days: int, user_id: int | None = None) -> list[dict]:
    where = ["k.started_at >= datetime('now', ?)"]
    params: list = [f"-{int(days)} days"]
    if user_id:
        where.append("k.user_id = ?")
        params.append(user_id)
    rows = db.query(
        "SELECT a.data, k.id AS call_id, k.user_id, k.severity, k.severity_reason, k.outcome, k.score, "
        "k.started_at, k.has_next_step, u.name AS user_name "
        "FROM analyses a JOIN calls k ON k.id = a.call_id LEFT JOIN users u ON u.id = k.user_id "
        f"WHERE {' AND '.join(where)}",
        params,
    )
    for row in rows:
        row["data"] = db.loads(row["data"], {})
    return rows


def overview(days: int = 30, user_id: int | None = None) -> dict:
    """Плитки, причины отказов, динамика и проблемные менеджеры."""
    where = ["started_at >= datetime('now', ?)"]
    params: list = [f"-{int(days)} days"]
    if user_id:
        where.append("user_id = ?")
        params.append(user_id)
    clause = " AND ".join(where)

    rows = db.query(f"SELECT severity, COUNT(*) AS n FROM calls WHERE {clause} GROUP BY severity", params)
    counts = {r["severity"] or "new": r["n"] for r in rows}
    total = sum(counts.values())

    prev_total = db.scalar(
        "SELECT COUNT(*) FROM calls WHERE started_at >= datetime('now', ?) AND started_at < datetime('now', ?)"
        + (" AND user_id = ?" if user_id else ""),
        [f"-{days * 2} days", f"-{days} days"] + ([user_id] if user_id else []),
        0,
    )
    trend = round(((total - prev_total) / prev_total) * 100) if prev_total else 0

    analyses = _analyses(days, user_id)
    reasons = Counter()
    objections = Counter()
    questions = Counter()
    for row in analyses:
        data = row["data"]
        for obj in data.get("objections", []):
            objections[obj.get("type", "другое")] += 1
        if (row.get("outcome") or "").startswith("отказ") or row.get("severity") == "critical":
            reasons[_reason_key(row)] += 1
        for q in data.get("open_questions", []):
            questions[q] += 1

    reason_rows = []
    for i, (key, n) in enumerate(reasons.most_common(6)):
        reason_rows.append({
            "label": OBJECTION_LABELS.get(key, key.capitalize()),
            "value": n,
            "percent": round(n / max(1, sum(reasons.values())) * 100),
            "color": REJECTION_COLORS[i % len(REJECTION_COLORS)],
        })

    by_day = db.query(
        f"SELECT date(started_at) AS day, COUNT(*) AS n, "
        "SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS critical "
        f"FROM calls WHERE {clause} GROUP BY day ORDER BY day",
        params,
    )

    managers = db.query(
        "SELECT u.id, u.name, u.avatar, u.color, COUNT(k.id) AS calls, "
        "SUM(CASE WHEN k.severity = 'critical' THEN 1 ELSE 0 END) AS critical, "
        "SUM(CASE WHEN k.severity = 'attention' THEN 1 ELSE 0 END) AS attention, "
        "ROUND(AVG(k.score), 1) AS score "
        "FROM users u JOIN calls k ON k.user_id = u.id "
        "WHERE u.role = 'manager' AND k.started_at >= datetime('now', ?) "
        "GROUP BY u.id ORDER BY critical DESC, attention DESC",
        (f"-{int(days)} days",),
    )

    # Главная проблема каждого менеджера — самый частый навык в разборах
    skills = db.query(
        "SELECT ci.user_id, ci.skill, COUNT(*) AS n FROM coach_items ci "
        "JOIN calls k ON k.id = ci.call_id WHERE k.started_at >= datetime('now', ?) "
        "GROUP BY ci.user_id, ci.skill ORDER BY n DESC",
        (f"-{int(days)} days",),
    )
    top_skill: dict[int, str] = {}
    for row in skills:
        top_skill.setdefault(row["user_id"], row["skill"])
    for m in managers:
        m["problem"] = top_skill.get(m["id"], "Без повторяющихся ошибок")

    return {
        "total": total,
        "counts": {s: counts.get(s, 0) for s in SEVERITIES},
        "trend": trend,
        "no_next_step": db.scalar(f"SELECT COUNT(*) FROM calls WHERE {clause} AND has_next_step = 0 AND status IN ('analyzed', 'saved')", params, 0),
        "avg_score": db.scalar(f"SELECT ROUND(AVG(score), 1) FROM calls WHERE {clause} AND score IS NOT NULL", params, 0),
        "rejections": reason_rows,
        "objections": [{"label": OBJECTION_LABELS.get(k, k), "value": v} for k, v in objections.most_common(6)],
        "by_day": by_day,
        "managers": managers,
        "open_questions": [{"text": q, "count": n} for q, n in questions.most_common(5)],
    }


def team(days: int = 30) -> dict:
    data = overview(days)
    return {"managers": data["managers"], "counts": data["counts"], "total": data["total"],
            "avg_score": data["avg_score"],
            "problem_calls": store.calls(severity="critical", days=days, limit=12)}


def coach_summary(user_id: int, days: int = 30) -> dict:
    """Повторяющиеся ошибки, сильные стороны и прогресс менеджера."""
    items = store.coach_items(user_id=user_id, days=days, limit=400)
    by_skill = defaultdict(list)
    for item in items:
        by_skill[item["skill"]].append(item)

    patterns = []
    for skill, group in sorted(by_skill.items(), key=lambda kv: -len(kv[1])):
        patterns.append({
            "skill": skill,
            "count": len(group),
            "title": f"{skill}: повторяется в {len(group)} звонках",
            "description": group[0]["why_problem"],
            "better_action": group[0]["better_action"],
            "sample_phrase": group[0]["sample_phrase"],
            "evidence": [{"call_id": g["call_id"], "time_sec": g["time_sec"], "quote": g["quote"],
                          "call_title": g["call_title"]} for g in group[:4]],
        })

    criteria = defaultdict(list)
    for row in db.query(
        "SELECT s.data FROM scorecards s JOIN calls k ON k.id = s.call_id "
        "WHERE k.user_id = ? AND k.started_at >= datetime('now', ?)",
        (user_id, f"-{int(days)} days"),
    ):
        for item in db.loads(row["data"], {}).get("criteria", []):
            criteria[item["name"]].append(item["score"])

    skills = [{"name": name, "score": round(sum(v) / len(v), 1), "count": len(v)}
              for name, v in criteria.items()]
    skills.sort(key=lambda s: s["score"])

    strengths = db.query(
        "SELECT b.skill, COUNT(*) AS n FROM best_moments b JOIN calls k ON k.id = b.call_id "
        "WHERE b.user_id = ? AND k.started_at >= datetime('now', ?) GROUP BY b.skill ORDER BY n DESC",
        (user_id, f"-{int(days)} days"),
    )

    def avg_score(offset_from: int, offset_to: int) -> float:
        return db.scalar(
            "SELECT ROUND(AVG(score), 1) FROM calls WHERE user_id = ? AND score IS NOT NULL "
            "AND started_at >= datetime('now', ?) AND started_at < datetime('now', ?)",
            (user_id, f"-{offset_from} days", f"-{offset_to} days"), 0,
        ) or 0

    return {
        "patterns": patterns,
        "skills": skills,
        "strengths": [dict(s) for s in strengths],
        "progress": {"current": avg_score(days, 0), "previous": avg_score(days * 2, days)},
        "calls_analyzed": db.scalar(
            "SELECT COUNT(*) FROM calls WHERE user_id = ? AND status IN ('analyzed', 'saved') AND started_at >= datetime('now', ?)",
            (user_id, f"-{int(days)} days"), 0),
    }


def insights(days: int = 30) -> list[dict]:
    """Ответы на вопросы руководителя по всему массиву звонков."""
    rows = _analyses(days)
    result: list[dict] = []
    if not rows:
        return result

    objections = Counter()
    risks = Counter()
    questions = Counter()
    lost_by_manager = Counter()
    calls_by_manager = Counter()
    no_step = []
    evidence = defaultdict(list)

    for row in rows:
        data = row["data"]
        calls_by_manager[row["user_name"]] += 1
        for obj in data.get("objections", []):
            key = obj.get("type", "другое")
            objections[key] += 1
            if len(evidence[f"obj:{key}"]) < 3:
                evidence[f"obj:{key}"].append({"call_id": row["call_id"], "quote": obj.get("quote", "")})
        for risk in data.get("risks", []):
            if risk.get("level") == "high":
                risks[risk["text"]] += 1
                if len(evidence[f"risk:{risk['text']}"]) < 3:
                    evidence[f"risk:{risk['text']}"].append({"call_id": row["call_id"], "quote": risk.get("quote", "")})
        for q in data.get("open_questions", []):
            questions[q] += 1
        if (row.get("outcome") or "").startswith("отказ"):
            lost_by_manager[row["user_name"]] += 1
        if not row["has_next_step"]:
            no_step.append(row["call_id"])

    total = len(rows)
    if objections:
        top, count = objections.most_common(1)[0]
        result.append({
            "kind": "objections",
            "title": f"Чаще всего мешает продажам: {OBJECTION_LABELS.get(top, top).lower()}",
            "body": f"Возражение «{OBJECTION_LABELS.get(top, top).lower()}» прозвучало в {count} из {total} разговоров "
                    f"({round(count / total * 100)}%). Это главный барьер отдела за период.",
            "evidence": evidence[f"obj:{top}"],
            "accent": "warn",
        })
    if no_step:
        result.append({
            "kind": "funnel",
            "title": "Воронка ломается на следующем шаге",
            "body": f"В {len(no_step)} из {total} звонков ({round(len(no_step) / total * 100)}%) менеджер не назначил "
                    f"дату следующего контакта. Это самая частая причина, по которой сделки зависают.",
            "evidence": [{"call_id": cid, "quote": ""} for cid in no_step[:3]],
            "accent": "bad",
        })
    if lost_by_manager:
        name, count = lost_by_manager.most_common(1)[0]
        share = round(count / max(1, calls_by_manager[name]) * 100)
        result.append({
            "kind": "losing",
            "title": f"Чаще других теряет клиентов: {name}",
            "body": f"{count} отказов из {calls_by_manager[name]} звонков ({share}%). Стоит послушать два-три разговора "
                    f"и разобрать их вместе с менеджером.",
            "evidence": [],
            "accent": "bad",
        })
    if risks:
        text, count = risks.most_common(1)[0]
        result.append({
            "kind": "repeats",
            "title": "Повторяющийся риск у разных менеджеров",
            "body": f"«{text}» встретился в {count} звонках. Это уже не ошибка одного человека, а системная проблема скрипта.",
            "evidence": evidence[f"risk:{text}"],
            "accent": "violet",
        })
    if questions:
        text, count = questions.most_common(1)[0]
        result.append({
            "kind": "questions",
            "title": "Что менеджеры регулярно забывают выяснить",
            "body": f"«{text}» — не выяснено в {count} разговорах. Добавьте этот пункт в скрипт квалификации.",
            "evidence": [],
            "accent": "accent",
        })

    best = db.query(
        "SELECT b.quote, b.why_good, b.skill, u.name AS user_name, b.call_id FROM best_moments b "
        "LEFT JOIN users u ON u.id = b.user_id JOIN calls k ON k.id = b.call_id "
        "WHERE k.started_at >= datetime('now', ?) ORDER BY b.score DESC LIMIT 3",
        (f"-{int(days)} days",),
    )
    if best:
        result.append({
            "kind": "best_phrases",
            "title": "Формулировки, которые работают у лучших",
            "body": f"«{best[0]['quote']}» — {best[0]['why_good']}. Добавьте такие фразы в скрипт и в обучение новичков.",
            "evidence": [{"call_id": b["call_id"], "quote": b["quote"]} for b in best],
            "accent": "ok",
        })
    return result
