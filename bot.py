from aiogram import Bot, Dispatcher, executor, types
from datetime import datetime, timedelta
import os

API_TOKEN = os.getenv("BOT_TOKEN")  # Укажи здесь свой токен

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Фото (можно заменить на file_id или URL)
PHOTO_PATHS = {
    "Федя": "photos/fedya.jpg",
    "Бобы": "photos/boby.jpg",
    "Металл": "photos/metall.jpg"
}

# Ассортимент
ITEMS = {
    "Федя": [("1 г", 2790), ("2 г", 4790), ("3 г", 7990)],
    "Бобы": [("1 г", 2190), ("2 г", 2990), ("3 г", 3990)],
    "Металл": [("1 г", 1490), ("2 г", 2490), ("3 г", 3490)]
}

# Актуализация по ближайшей получасовке
def get_actual_time():
    now = datetime.now()
    rounded_minute = 30 if now.minute >= 30 else 0
    actual_time = now.replace(minute=rounded_minute, second=0, microsecond=0)
    return actual_time.strftime("%d.%m.%Y в %H:%M")

# Стартовое меню
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    text = "<b>🍬 Ассортимент:</b>\n"
    for item, variants in ITEMS.items():
        text += f"\n<b>{item}</b>\n"
        for name, price in variants:
            text += f"• {name} — {price} ₽\n"
    text += f"\n📦 Актуализация на: <i>{get_actual_time()}</i>"

    buttons = [
        [types.KeyboardButton("🛒 Оформить заказ")],
        [types.KeyboardButton("📸 Фото со склада"), types.KeyboardButton("💬 Связаться с админом")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

# Остальные хендлеры (заказ, фото, админ) можно дописать отдельно

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)