from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.config import settings


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔍 Новый анализ", callback_data="new_scan")
    kb.button(text="📄 Обновить резюме", callback_data="update_resume")
    kb.button(text="💎 Pro-доступ", callback_data="show_pricing")
    kb.adjust(1)
    return kb.as_markup()


def paywall_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Я перевёл — активируйте", callback_data="payment_done")
    kb.adjust(1)
    return kb.as_markup()


def cancel_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="cancel")
    return kb.as_markup()


def paywall_text(tg_id: int) -> str:
    return (
        f"💎 <b>Закончились бесплатные анализы</b>\n\n"
        f"<b>Pro</b> — {settings.pro_price_kzt} ₸/мес (30 анализов)\n"
        f"<b>Lifetime</b> — {settings.lifetime_price_kzt} ₸ навсегда\n\n"
        f"<b>Как оплатить:</b>\n"
        f"1. Переведи на Kaspi: <code>{settings.kaspi_phone}</code> ({settings.kaspi_name})\n"
        f"2. В комментарии напиши: <code>tg{tg_id}</code>\n"
        f"3. Нажми кнопку ниже\n"
        f"4. Активирую вручную в течение 1-2 часов"
    )
