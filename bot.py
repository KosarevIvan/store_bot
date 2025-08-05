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
import json
import os.path
import uuid

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, parse_mode='HTML')
dp = Dispatcher(bot, storage=MemoryStorage())

# Data structures
banned_users = set()
user_contacting_admin = {}
username_to_id = {}
awaiting_admin_reply = set()
user_orders = {}
chat_logs = {}

# Create directories
os.makedirs('chat_logs', exist_ok=True)
os.makedirs('chat_logs/photos', exist_ok=True)


class OrderState(StatesGroup):
    waiting_for_product = State()
    waiting_for_quantity = State()
    waiting_for_quality = State()
    confirming_order = State()
    waiting_for_comment = State()


# Products and photos configuration
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

# Keyboards
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("🛒 Оформить заказ")
main_kb.add("📦 Фото со склада", "📩 Связаться с админом")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅️ На главную")


# Helper functions
def get_time_stamp():
    msk_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(msk_tz)
    return now.strftime("%d.%m.%y %H:%M:%S")


async def save_photo(photo: types.PhotoSize, user_id: int) -> str:
    """Save photo to disk and return filename"""
    file_ext = photo.file_unique_id[-4:]
    filename = f"{user_id}_{uuid.uuid4().hex[:8]}_{file_ext}.jpg"
    file_path = f"chat_logs/photos/{filename}"
    await photo.download(destination_file=file_path)
    return filename


def log_message(user_id: int, message: str, is_admin: bool = False, is_photo: bool = False):
    """Log message to chat history"""
    if user_id not in chat_logs:
        chat_logs[user_id] = []

    timestamp = get_time_stamp()
    username = "admin" if is_admin else f"{username_to_id.get(f'@{user_id}', 'user')}({user_id})"

    if is_photo:
        log_entry = f"{timestamp} @{username}: [фото_{message}]"
    else:
        log_entry = f"{timestamp} @{username}: {message}"

    chat_logs[user_id].append(log_entry)

    # Save to file
    filename = f"chat_logs/user_{user_id}.txt"
    try:
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(log_entry + "\n")
    except Exception as e:
        logging.error(f"Error saving chat log: {e}")


def load_chat_logs(user_id: int):
    """Load chat history from file"""
    filename = f"chat_logs/user_{user_id}.txt"
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read().splitlines()
        except Exception as e:
            logging.error(f"Error loading chat log: {e}")
    return []


async def delete_user_messages(user_id: int):
    """Delete all messages from bot to user"""
    try:
        async for msg in bot.iter_history(user_id, limit=100):
            if msg.from_user.id == BOT_TOKEN.split(':')[0]:
                await bot.delete_message(user_id, msg.message_id)
    except Exception as e:
        logging.error(f"Error deleting messages: {e}")


async def resolve_user_id(target: str) -> int:
    """Resolve user ID from username or ID string"""
    if target.startswith("@"):
        return username_to_id.get(target)
    try:
        return int(target)
    except ValueError:
        return None


# Admin commands
@dp.message_handler(commands=['ban'])
async def ban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /ban user_id или /ban @username")
        return

    user_id = await resolve_user_id(parts[1])
    if user_id:
        banned_users.add(user_id)
        await message.reply(f"🚫 Пользователь {parts[1]} заблокирован.")
    else:
        await message.reply("❗ Пользователь не найден.")
    log_message(message.from_user.id, f"/ban {parts[1]}", is_admin=True)


@dp.message_handler(commands=['unban'])
async def unban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /unban user_id или /unban @username")
        return

    user_id = await resolve_user_id(parts[1])
    if user_id:
        banned_users.discard(user_id)
        await message.reply(f"✅ Пользователь {parts[1]} разблокирован.")
    else:
        await message.reply("❗ Пользователь не найден.")
    log_message(message.from_user.id, f"/unban {parts[1]}", is_admin=True)


@dp.message_handler(commands=['очистить'])
async def clear_chat(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /очистить @username или /очистить user_id")
        return

    user_id = await resolve_user_id(parts[1])
    if user_id:
        try:
            # Clear logs
            chat_logs[user_id] = []
            filename = f"chat_logs/user_{user_id}.txt"
            if os.path.exists(filename):
                os.remove(filename)

            # Delete user messages
            await delete_user_messages(user_id)

            await message.reply(f"✅ Чат с пользователем {parts[1]} полностью очищен.")
        except Exception as e:
            await message.reply(f"❌ Ошибка: {str(e)}")
    else:
        await message.reply("❗ Пользователь не найден.")
    log_message(message.from_user.id, f"/очистить {parts[1]}", is_admin=True)


@dp.message_handler(commands=['история'])
async def view_chat_history(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /история @username или /история user_id")
        return

    user_id = await resolve_user_id(parts[1])
    if user_id:
        history = load_chat_logs(user_id)
        if history:
            chunks = [history[i:i + 20] for i in range(0, len(history), 20)]
            for chunk in chunks:
                await message.answer("\n".join(chunk))
        else:
            await message.reply("История переписки пуста.")
    else:
        await message.reply("❗ Пользователь не найден.")
    log_message(message.from_user.id, f"/история {parts[1]}", is_admin=True)


@dp.message_handler(commands=['оплата'])
async def send_payment(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.reply("❗ Формат: /оплата @username ссылка_на_оплату")
        return

    user_id = await resolve_user_id(parts[1])
    if user_id:
        order_data = user_orders.get(user_id)
        if order_data:
            payment_msg = f"""💳 Подтверждение оплаты заказа

Здравствуйте!
Ваш заказ принят:

🔹 Товар: {order_data['product']}
🔹 Граммовка: {order_data['quantity']} г
🔹 Качество: {'улучшенное' if order_data['quality'] else 'стандартное'}
🔹 Стоимость: {order_data['price']}₽

💰 Для оплаты перейдите по ссылке:
{parts[2]}

После оплаты пришлите скриншот."""

            try:
                await bot.send_message(user_id, payment_msg)
                await message.reply(f"✅ Сообщение об оплате отправлено пользователю {parts[1]}")
            except Exception as e:
                await message.reply(f"❌ Ошибка: {str(e)}")
        else:
            await message.reply("❗ У пользователя нет активного заказа.")
    else:
        await message.reply("❗ Пользователь не найден.")
    log_message(message.from_user.id, f"/оплата {parts[1]}", is_admin=True)


@dp.message_handler(commands=['ответ'])
async def reply_to_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.reply("❗ Формат: /ответ @username сообщение")
        return

    user_id = await resolve_user_id(parts[1])
    if user_id:
        try:
            # Delete bot's "message sent" notification
            async for msg in bot.iter_history(user_id, limit=10):
                if msg.text == "✅ Сообщение отправлено администратору. Ожидайте ответа.":
                    await bot.delete_message(user_id, msg.message_id)
                    break

            await bot.send_message(user_id, f"📬 Ответ администратора:\n\n{parts[2]}")
            await message.reply("✅ Ответ отправлен.")
            log_message(user_id, f"Ответ админа: {parts[2]}", is_admin=True)
        except Exception as e:
            await message.reply(f"❌ Ошибка: {str(e)}")
    else:
        await message.reply("❗ Пользователь не найден.")


# ... (остальные обработчики остаются без изменений, как в предыдущей версии)

if __name__ == '__main__':
    print("🚀 Бот запускается...")
    # Load existing logs
    for filename in os.listdir('chat_logs'):
        if filename.startswith('user_') and filename.endswith('.txt'):
            user_id = int(filename[5:-4])
            chat_logs[user_id] = load_chat_logs(user_id)

    executor.start_polling(dp, skip_updates=True)