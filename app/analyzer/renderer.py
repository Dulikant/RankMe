from app.analyzer.schema import GapAnalysisReport

TELEGRAM_LIMIT = 4000


def _score_bar(score: int) -> str:
    filled = round(score / 10)
    if score >= 75:
        block = "🟩"
    elif score >= 60:
        block = "🟨"
    elif score >= 40:
        block = "🟧"
    else:
        block = "🟥"
    return block * filled + "⬜" * (10 - filled)


def _verdict_emoji(score: int) -> str:
    if score >= 75:
        return "✅"
    if score >= 60:
        return "👍"
    if score >= 40:
        return "⚠️"
    return "❌"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _split(text: str) -> list[str]:
    """Режет длинное сообщение по абзацам."""
    if len(text) <= TELEGRAM_LIMIT:
        return [text]

    chunks, current = [], ""
    for para in text.split("\n\n"):
        if len(current) + len(para) + 2 <= TELEGRAM_LIMIT:
            current += para + "\n\n"
        else:
            if current:
                chunks.append(current.strip())
            current = para + "\n\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text[:TELEGRAM_LIMIT]]


def render_report(report: GapAnalysisReport) -> list[str]:
    messages: list[str] = []

    # === Сообщение 1: вердикт ===
    msg1 = "\n".join([
        f"{_verdict_emoji(report.match_score)} <b>Match score: {report.match_score}/100</b>",
        _score_bar(report.match_score),
        "",
        f"<i>{_escape(report.one_line_verdict)}</i>",
        "",
        "<b>Разбивка:</b>",
        f"• Hard skills: {report.score_breakdown.hard_skills}/100",
        f"• Опыт и роль: {report.score_breakdown.experience}/100",
        f"• Доменная область: {report.score_breakdown.domain}/100",
        f"• Soft skills + образование: {report.score_breakdown.soft_and_education}/100",
    ])
    messages.append(msg1)

    # === Сообщение 2: что есть / чего нет ===
    lines: list[str] = []

    if report.matching_skills:
        lines.append("✅ <b>Что у тебя есть и совпадает</b>\n")
        for item in report.matching_skills:
            lines.append(f"• <b>{_escape(item.skill)}</b>")
            lines.append(f"  {_escape(item.detail)}\n")

    if report.missing_critical:
        lines.append("\n🚨 <b>Чего не хватает (критично)</b>\n")
        for item in report.missing_critical:
            lines.append(f"• <b>{_escape(item.skill)}</b>")
            lines.append(f"  💬 <i>«{_escape(item.evidence)}»</i>")
            lines.append(f"  {_escape(item.why_matters)}\n")

    if report.missing_nice_to_have:
        lines.append("\n⚡ <b>Желательно</b>\n")
        for item in report.missing_nice_to_have:
            lines.append(f"• <b>{_escape(item.skill)}</b>")
            lines.append(f"  💬 <i>«{_escape(item.evidence)}»</i>")
            lines.append(f"  {_escape(item.why_matters)}\n")

    if lines:
        messages.append("\n".join(lines).strip())

    # === Сообщение 3: что делать ===
    lines3: list[str] = []

    if report.weak_presentation:
        lines3.append("📝 <b>Есть, но плохо подано</b>\n")
        for item in report.weak_presentation:
            lines3.append(f"• <b>{_escape(item.skill)}</b>")
            lines3.append(f"  Сейчас: <i>«{_escape(item.original_text)}»</i>")
            lines3.append(f"  Лучше: <i>«{_escape(item.improved_text)}»</i>\n")

    if report.development_plan:
        total = sum(s.estimated_hours for s in report.development_plan)
        lines3.append(f"\n🎯 <b>План на 2 недели (~{total} часов)</b>\n")
        for i, step in enumerate(report.development_plan, 1):
            line = f"{i}. {_escape(step.action)} <i>(~{step.estimated_hours} ч)</i>"
            if step.resource:
                line += f"\n   📚 {_escape(step.resource)}"
            lines3.append(line + "\n")

    if report.rewritten_bullets:
        lines3.append("\n✍️ <b>Готовые формулировки для резюме</b>\n")
        labels = {"experience": "В раздел «Опыт»", "skills": "В раздел «Навыки»", "summary": "В раздел «О себе»"}
        for bullet in report.rewritten_bullets:
            lines3.append(f"<b>{labels.get(bullet.section, bullet.section)}:</b>")
            lines3.append(f"<pre>{_escape(bullet.text)}</pre>\n")

    if lines3:
        messages.append("\n".join(lines3).strip())

    # Защита от лимита 4096
    result: list[str] = []
    for msg in messages:
        result.extend(_split(msg))
    return result
