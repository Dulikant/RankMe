import asyncio
import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, update

from app.config import settings
from app.db import async_session
from app.models import User, Resume, Scan
from app.bot.states import UserFlow
from app.bot.keyboards import main_menu, paywall_menu, cancel_menu, paywall_text
from app.analyzer.pdf import extract_pdf_text
from app.analyzer.client import analyze_gap
from app.analyzer.renderer import render_report

logger = logging.getLogger(__name__)
router = Router()


# ──────────────────────────────────────────────
# Утилиты
# ──────────────────────────────────────────────

async def get_or_create_user(session, message: Message) -> User:
    result = await session.execute(select(User).where(User.tg_id == message.from_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            tg_id=message.from_user.id,
            tg_username=message.from_user.username,
            tg_first_name=message.from_user.first_name,
        )
        session.add(user)
        await session.flush()
    else:
        user.last_active_at = datetime.utcnow()
    await session.commit()
    return user


async def get_active_resume(session, user_id: int) -> Resume | None:
    result = await session.execute(
        select(Resume)
        .where(Resume.user_id == user_id, Resume.is_active == True)
        .order_by(Resume.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def can_scan(user: User) -> bool:
    if user.plan == "lifetime":
        return True
    if user.plan == "pro":
        if user.plan_expires_at and user.plan_expires_at > datetime.utcnow():
            return True
        return False
    return user.scans_used < settings.free_scans_limit


# ──────────────────────────────────────────────
# /start
# ──────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        user = await get_or_create_user(session, message)
        resume = await get_active_resume(session, user.id)

    if resume is None:
        await message.answer(
            "👋 Привет! Я анализирую твоё резюме под конкретную вакансию:\n\n"
            "• считаю match score 0-100\n"
            "• говорю чего не хватает — с цитатами из вакансии\n"
            "• даю план что подучить за 2 недели\n\n"
            "Сначала загрузи резюме — пришли <b>PDF-файлом</b> или просто "
            "<b>скопируй текст</b> и отправь сообщением.\n\n"
            f"💎 Бесплатно: {settings.free_scans_limit} анализа. Потом — подписка."
        )
        await state.set_state(UserFlow.waiting_resume)
    else:
        scans_left = max(0, settings.free_scans_limit - user.scans_used)
        plan_info = (
            f"💎 Осталось бесплатных: {scans_left}"
            if user.plan == "free"
            else f"💎 Тариф: {user.plan.upper()}"
        )
        await message.answer(
            f"С возвращением, {message.from_user.first_name}! 👋\n\n"
            "Резюме у меня уже есть. Скинь текст вакансии — "
            "скопируй описание с hh.kz, LinkedIn или любого сайта.\n\n"
            f"{plan_info}",
            reply_markup=main_menu(),
        )
        await state.set_state(UserFlow.waiting_vacancy)


# ──────────────────────────────────────────────
# Загрузка резюме
# ──────────────────────────────────────────────

@router.message(UserFlow.waiting_resume, F.document)
@router.message(UserFlow.updating_resume, F.document)
async def handle_resume_pdf(message: Message, state: FSMContext) -> None:
    doc = message.document
    if not doc.file_name.lower().endswith(".pdf"):
        await message.answer("Принимаю только PDF. Если Word — экспортируй в PDF.")
        return

    file = await message.bot.get_file(doc.file_id)
    file_bytes = await message.bot.download_file(file.file_path)

    try:
        resume_text = extract_pdf_text(file_bytes.read())
    except ValueError as e:
        await message.answer(
            f"❌ {e}\n\nПопробуй: открой в Google Docs → Файл → Скачать → PDF. "
            "Или скопируй текст и пришли сообщением."
        )
        return
    except Exception:
        logger.exception("PDF parsing error")
        await message.answer("Не смог прочитать PDF. Пришли текст резюме сообщением.")
        return

    await _save_resume(message, state, resume_text, "pdf", doc.file_name)


@router.message(UserFlow.waiting_resume, F.text)
@router.message(UserFlow.updating_resume, F.text)
async def handle_resume_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if len(text) < 200:
        await message.answer("Слишком мало текста (нужно минимум 200 символов). Пришли полное резюме.")
        return
    await _save_resume(message, state, text, "text", None)


async def _save_resume(message: Message, state: FSMContext, raw_text: str, source: str, file_name: str | None) -> None:
    async with async_session() as session:
        user = await get_or_create_user(session, message)
        # Деактивируем старые резюме
        await session.execute(
            update(Resume).where(Resume.user_id == user.id).values(is_active=False)
        )
        resume = Resume(user_id=user.id, raw_text=raw_text, source_type=source, file_name=file_name, is_active=True)
        session.add(resume)
        await session.commit()

    await message.answer(
        "✅ Резюме сохранил!\n\n"
        "Теперь скинь текст вакансии — скопируй описание со страницы "
        "(hh.kz, LinkedIn, любой сайт) и вставь сюда.",
        reply_markup=cancel_menu(),
    )
    await state.set_state(UserFlow.waiting_vacancy)


# ──────────────────────────────────────────────
# Анализ вакансии
# ──────────────────────────────────────────────

@router.message(UserFlow.waiting_vacancy, F.text)
async def handle_vacancy(message: Message, state: FSMContext) -> None:
    vacancy_text = message.text.strip()
    if len(vacancy_text) < 200:
        await message.answer("Слишком короткий текст. Скопируй описание вакансии полностью.")
        return

    async with async_session() as session:
        user = await get_or_create_user(session, message)
        resume = await get_active_resume(session, user.id)

        if resume is None:
            await message.answer("Сначала загрузи резюме. Нажми /start.")
            await state.clear()
            return

        if not can_scan(user):
            await message.answer(paywall_text(message.from_user.id), reply_markup=paywall_menu())
            return

        scan = Scan(user_id=user.id, resume_id=resume.id, vacancy_text=vacancy_text, status="pending")
        session.add(scan)
        await session.commit()
        scan_id = scan.id
        resume_text = resume.raw_text

    progress = await message.answer("🔍 Анализирую... Это займёт 30-60 секунд.")

    try:
        report, tokens = await analyze_gap(resume_text, vacancy_text)
    except Exception as e:
        logger.exception("Analysis failed")
        async with async_session() as session:
            await session.execute(
                update(Scan).where(Scan.id == scan_id).values(status="error", error_message=str(e))
            )
            await session.commit()
        await progress.edit_text("Что-то пошло не так. Попробуй ещё раз через минуту.")
        return

    async with async_session() as session:
        await session.execute(
            update(Scan).where(Scan.id == scan_id).values(
                status="done",
                match_score=report.match_score,
                report_json=report.model_dump_json(),
                tokens_used=tokens,
                completed_at=datetime.utcnow(),
            )
        )
        await session.execute(
            update(User).where(User.tg_id == message.from_user.id).values(scans_used=User.scans_used + 1)
        )
        await session.commit()

    await progress.delete()

    # Отправляем отчёт по частям с typing-паузой
    report_messages = render_report(report)
    for i, text in enumerate(report_messages):
        if i > 0:
            await message.bot.send_chat_action(message.chat.id, "typing")
            await asyncio.sleep(0.8)
        await message.answer(text, parse_mode="HTML")

    # Footer
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == message.from_user.id))
        user = result.scalar_one()

    if user.plan == "free" and user.scans_used >= settings.free_scans_limit:
        await message.answer(paywall_text(message.from_user.id), reply_markup=paywall_menu())
    else:
        scans_left = max(0, settings.free_scans_limit - user.scans_used) if user.plan == "free" else "∞"
        await message.answer(
            f"Анализов осталось: <b>{scans_left}</b>\n\nЕщё вакансия? Просто скинь текст.",
            reply_markup=main_menu(),
        )

    await state.set_state(UserFlow.waiting_vacancy)


# ──────────────────────────────────────────────
# Callbacks
# ──────────────────────────────────────────────

@router.callback_query(F.data == "new_scan")
async def cb_new_scan(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer("Скинь текст вакансии.", reply_markup=cancel_menu())
    await state.set_state(UserFlow.waiting_vacancy)


@router.callback_query(F.data == "update_resume")
async def cb_update_resume(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer("Скинь новое резюме — PDF или текстом. Старое заменится.")
    await state.set_state(UserFlow.updating_resume)


@router.callback_query(F.data == "show_pricing")
async def cb_show_pricing(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(paywall_text(callback.from_user.id), reply_markup=paywall_menu())


@router.callback_query(F.data == "payment_done")
async def cb_payment_done(callback: CallbackQuery) -> None:
    await callback.answer("Спасибо! Активирую в течение 1-2 часов.", show_alert=True)
    await callback.bot.send_message(
        settings.admin_tg_id,
        f"💸 <b>Новый платёж заявлен!</b>\n\n"
        f"Юзер: @{callback.from_user.username or '—'} ({callback.from_user.first_name})\n"
        f"TG ID: <code>{callback.from_user.id}</code>\n\n"
        f"Активировать Pro:\n<code>/grant {callback.from_user.id} pro</code>\n\n"
        f"Активировать Lifetime:\n<code>/grant {callback.from_user.id} lifetime</code>",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Отменил")
    await state.clear()
    await callback.message.answer("Окей. /start — начать заново.", reply_markup=main_menu())


# ──────────────────────────────────────────────
# Команды
# ──────────────────────────────────────────────

@router.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Сброшено. /start — начать заново.")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Команды:</b>\n"
        "/start — начать или продолжить\n"
        "/reset — сбросить состояние\n"
        "/help — эта справка\n\n"
        "Загрузи резюме один раз, потом просто кидай вакансии.",
        parse_mode="HTML",
    )
