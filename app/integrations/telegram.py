"""
Telegram Bot integration — sending messages and inline keyboards.
All interaction with the user flows through a single personal chat.
"""
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from app.config import settings

_bot: Bot | None = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    return _bot


async def send_message(text: str, reply_markup=None) -> None:
    bot = get_bot()
    await bot.send_message(
        chat_id=settings.TELEGRAM_CHAT_ID,
        text=text,
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def send_alert(text: str, buttons: list[list[dict]]) -> None:
    """
    Send a message with an inline keyboard.
    buttons is a list of rows; each row is a list of {text, callback_data} dicts.
    """
    keyboard = [
        [InlineKeyboardButton(b["text"], callback_data=b["callback_data"]) for b in row]
        for row in buttons
    ]
    await send_message(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def answer_callback(callback_query_id: str, text: str = "") -> None:
    """Acknowledge a button tap (removes the loading spinner on Telegram's side)."""
    bot = get_bot()
    await bot.answer_callback_query(callback_query_id, text=text)


async def setup_webhook(webhook_url: str) -> None:
    bot = get_bot()
    await bot.set_webhook(url=webhook_url)


async def delete_webhook() -> None:
    bot = get_bot()
    await bot.delete_webhook()
