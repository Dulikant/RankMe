import functools
import logging
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select, func, update

from app.config import settings
from app.db import async_session
from app.models import User, Scan

logger = logging.getLogger(__name__)
router = Router()


def admin_only(handler):
    @functools.wraps(handler)
    async def wrapper(message: Message, *args, **kwargs):
        if message.from_user.id != settings.admin_tg_id:
            return
        return await handler(message, *args, **kwargs)
    return wrapper


@router.message(Command("grant"))
@admin_only
async def cmd_grant(message: Message) -> None:
    """
    /grant <tg_id> <pro|lifetime|free>
    Пример: /grant 123456789 pro
    """
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Использование: /grant <tg_id> <pro|lifetime|free>")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("tg_id должен быть числом")
        return

    plan = parts[2].lower()
    if plan not in ("pro", "lifetime", "free"):
        await message.answer("plan: pro / lifetime / free")
        return

    expires_at = datetime.utcnow() + timedelta(days=30) if plan == "pro" else None

    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == target_id))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer(f"Юзер {target_id} не найден")
            return
        await session.execute(
            update(User).where(User.tg_id == target_id).values(plan=plan, plan_expires_at=expires_at)
        )
        await session.commit()

    await message.answer(f"✅ Юзеру {target_id} выдан тариф <b>{plan}</b>", parse_mode="HTML")

    # Уведомляем юзера
    try:
        texts = {
            "pro": "💎 Pro-доступ активирован на 30 дней! Лимиты сняты — кидай вакансии.",
            "lifetime": "💎 Lifetime активирован! Безлимит навсегда. Спасибо!",
            "free": "Тариф изменён на Free.",
        }
        await message.bot.send_message(target_id, texts[plan])
    except Exception:
        pass


@router.message(Command("stats"))
@admin_only
async def cmd_stats(message: Message) -> None:
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    async with async_session() as session:
        total_users = (await session.execute(select(func.count(User.id)))).scalar()
        users_today = (await session.execute(
            select(func.count(User.id)).where(User.created_at >= today)
        )).scalar()
        total_scans = (await session.execute(
            select(func.count(Scan.id)).where(Scan.status == "done")
        )).scalar()
        scans_today = (await session.execute(
            select(func.count(Scan.id)).where(Scan.status == "done", Scan.created_at >= today)
        )).scalar()
        paid_users = (await session.execute(
            select(func.count(User.id)).where(User.plan.in_(["pro", "lifetime"]))
        )).scalar()

    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"Юзеров: <b>{total_users}</b> (+{users_today} сегодня)\n"
        f"Анализов: <b>{total_scans}</b> (+{scans_today} сегодня)\n"
        f"Платящих: <b>{paid_users}</b>\n"
        f"Конверсия: <b>{round(paid_users / total_users * 100, 1) if total_users else 0}%</b>",
        parse_mode="HTML",
    )


@router.message(Command("broadcast"))
@admin_only
async def cmd_broadcast(message: Message) -> None:
    """
    /broadcast Текст сообщения
    Отправляет всем юзерам.
    """
    text = message.text.removeprefix("/broadcast").strip()
    if not text:
        await message.answer("Использование: /broadcast <текст>")
        return

    async with async_session() as session:
        result = await session.execute(select(User.tg_id))
        tg_ids = [row[0] for row in result.fetchall()]

    sent, failed = 0, 0
    for tg_id in tg_ids:
        try:
            await message.bot.send_message(tg_id, text)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(f"Рассылка завершена. Отправлено: {sent}, ошибок: {failed}")
