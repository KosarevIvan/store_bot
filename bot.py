import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from dotenv import load_dotenv
from datetime import datetime
import pytz

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, parse_mode='HTML')
dp = Dispatcher(bot, storage=MemoryStorage())

banned_users = set()
user_contacting_admin = {}
awaiting_admin_reply = set()

class OrderState(StatesGroup):
    waiting_for_product = State()
    waiting_for_quantity = State()
    waiting_for_quality = State()
    confirming_order = State()
    waiting_for_comment = State()

PRODUCTS = {
    "Федя": {1: 2790, 2: 4790, 3: 7990},
    "Бобы": {1: 2190, 2: 2990, 3: 3990},
    "Металл": {1: 1490, 2: 2490, 3: 3490},
}

PHOTOS = {
    "Федя": "data/photos/fedya.jpg",
    "Бобы": "data/photos/boby.jpg",
    "Металл": "data/photos/metall.jpg",
}

main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("🛒 Оформить заказ")
main_kb.add("📦 Фото со склада", "📩 Связаться с админом")

def get_time_stamp():
    msk_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(msk_tz)
    rounded = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
    return rounded.strftime("%d.%m.%Y в %H:%M")

def format_welcome():
    return f"""
Добро пожаловать в наш магазин Elysium One — где каждый грамм удовольствия становится искусством.
🍬 Наш актуальный ассортимент премиальных веществ:

<b>Федя</b>
1г — 2 790₽
2г — 4 790₽ (выгода 15%)
3г — 7 990₽ (самое выгодное предложение)

<b>Бобы</b>
1г — 2 190₽
2г — 2 990₽ (📉 выгода 32%!)
3г — 3 990₽ (🎁 лучший выбор)

<b>Металл</b>
1г — 1 490₽
2г — 2 490₽ (💰 выгода 17%)
3г — 3 490₽ (🚀 топ-предложение)

🎯 <b>Специальное предложение:</b>
Вы можете приобрести товар высшего качества, добавив всего 10% к стоимости заказа.

Если вас интересуют другие вещества или граммовки — мы готовы обсудить индивидуальное предложение специально для Вас.

📍 Сейчас сервис работает в: Санкт-Петербурге, Москве, Екатеринбурге, Владивостоке, Челябинске, Иркутске и Казани.

📅 Актуализировано {get_time_stamp()} (по МСК)
🔒 Все заказы перед доставкой проходят контроль качества.
🚀 Доставка — быстрая и надёжная. Скорее всего, клад уже ждёт Вас в вашем районе.
Ваш <b>Elysium One</b> — где сладости становятся эксклюзивом.
"""

@dp.message_handler(commands=['ban'])
async def ban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /ban user_id")
        return
    try:
        uid = int(parts[1])
        banned_users.add(uid)
        await message.reply(f"🚫 Пользователь {uid} заблокирован.")
    except ValueError:
        await message.reply("❗ Неверный ID пользователя.")

@dp.message_handler(commands=['unban'])
async def unban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /unban user_id")
        return
    try:
        uid = int(parts[1])
        banned_users.discard(uid)
        await message.reply(f"✅ Пользователь {uid} разблокирован.")
    except ValueError:
        await message.reply("❗ Неверный ID пользователя.")

@dp.message_handler(commands=['ответ'])
async def reply_to_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.reply("❗ Используйте формат: /ответ @username сообщение")
            return
        username = parts[1].lstrip('@')
        text = parts[2]
        for uid, uname in user_contacting_admin.items():
            if uname == username:
                await bot.send_message(uid, f"📩 Ответ от администратора:\n{text}")
                await message.reply("✅ Сообщение отправлено.")
                return
        await message.reply("❗ Пользователь не найден или не писал администратору.")
    except Exception as e:
        await message.reply(f"Ошибка: {e}")

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    if message.from_user.id in banned_users:
        return
    await message.answer(format_welcome(), reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "📦 Фото со склада")
async def photos_handler(message: types.Message, state: FSMContext):
    kb = InlineKeyboardMarkup()
    for name in PRODUCTS:
        kb.add(InlineKeyboardButton(name, callback_data=f"photo:{name}"))
    await message.answer("Выберите товар:", reply_markup=kb)
    await state.update_data(last_photo=None)

@dp.callback_query_handler(lambda c: c.data.startswith("photo:"))
async def send_photo(call: types.CallbackQuery, state: FSMContext):
    product = call.data.split(":")[1]
    photo_path = PHOTOS.get(product)

    data = await state.get_data()
    last_photo_id = data.get("last_photo")
    if last_photo_id:
        try:
            await bot.delete_message(call.message.chat.id, last_photo_id)
        except:
            pass

    if photo_path:
        sent = await call.message.answer_photo(InputFile(photo_path))
        await state.update_data(last_photo=sent.message_id)
    else:
        await call.message.answer("Фото не найдено.")
    await call.answer()

@dp.message_handler(lambda m: m.text == "📩 Связаться с админом")
async def contact_admin(message: types.Message):
    if message.from_user.id in banned_users:
        return
    user_contacting_admin[message.from_user.id] = message.from_user.username or f"id{message.from_user.id}"
    awaiting_admin_reply.add(message.from_user.id)
    await message.answer("✏️ Напишите ваше сообщение администратору:")

@dp.message_handler()
async def handle_admin_message(message: types.Message):
    if message.from_user.id in banned_users:
        return
    if message.from_user.id not in awaiting_admin_reply:
        return  # не пересылаем обычные сообщения
    username = message.from_user.username or f"id{message.from_user.id}"
    user_contacting_admin[message.from_user.id] = username
    msg = f"📩 Сообщение от @{username} (ID: {message.from_user.id}):\n{message.text}"
    await bot.send_message(ADMIN_ID, msg)
    await message.answer("Ваше сообщение передано администратору. Он свяжется с вами в ближайшее время.")
    awaiting_admin_reply.discard(message.from_user.id)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
