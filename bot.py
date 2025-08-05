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
            if msg.from_user.id == int(BOT_TOKEN.split(':')[0]):
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


# New command to send photo from logs
@dp.message_handler(commands=['фото'])
async def send_photo_from_logs(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /фото id_фото")
        return

    photo_id = parts[1]
    photo_path = f"chat_logs/photos/{photo_id}"

    if os.path.exists(photo_path):
        try:
            await message.reply_photo(InputFile(photo_path))
        except Exception as e:
            await message.reply(f"❌ Ошибка при отправке фото: {str(e)}")
    else:
        await message.reply("❗ Фото не найдено. Проверьте ID.")


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


@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    if message.from_user.id in banned_users:
        return
    log_message(message.from_user.id, "/start")
    await message.answer("Добро пожаловать в магазин!", reply_markup=main_kb)


@dp.message_handler(lambda m: m.text == "⬅️ На главную")
async def back_to_main(message: types.Message):
    log_message(message.from_user.id, "На главную")
    await message.answer("Главное меню:", reply_markup=main_kb)


@dp.message_handler(lambda m: m.text == "📦 Фото со склада")
async def show_photos(message: types.Message, state: FSMContext):
    log_message(message.from_user.id, "Просмотр фото товаров")
    kb = InlineKeyboardMarkup()
    for product in PHOTOS:
        kb.add(InlineKeyboardButton(text=product, callback_data=f"photo:{product}"))
    await message.answer("Выберите товар:", reply_markup=kb)
    await state.update_data(last_photo_id=None)


@dp.callback_query_handler(lambda c: c.data.startswith("photo:"))
async def send_product_photo(call: types.CallbackQuery, state: FSMContext):
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
        await call.message.answer("Фото не найдено")
    await call.answer()


@dp.message_handler(lambda m: m.text == "🛒 Оформить заказ")
async def start_order(message: types.Message):
    log_message(message.from_user.id, "Начало оформления заказа")
    kb = InlineKeyboardMarkup()
    for product in PRODUCTS:
        kb.add(InlineKeyboardButton(text=product, callback_data=f"order:{product}"))
    await message.answer("Выберите товар:", reply_markup=kb)
    await OrderState.waiting_for_product.set()


@dp.callback_query_handler(lambda c: c.data.startswith("order:"), state=OrderState.waiting_for_product)
async def choose_quantity(call: types.CallbackQuery, state: FSMContext):
    product = call.data.split(":")[1]
    await state.update_data(product=product)
    kb = InlineKeyboardMarkup()
    for qty in PRODUCTS[product]:
        kb.add(InlineKeyboardButton(text=f"{qty} г", callback_data=f"qty:{qty}"))
    await call.message.answer("Выберите количество:", reply_markup=kb)
    await OrderState.waiting_for_quantity.set()
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("qty:"), state=OrderState.waiting_for_quantity)
async def choose_quality(call: types.CallbackQuery, state: FSMContext):
    quantity = int(call.data.split(":")[1])
    await state.update_data(quantity=quantity)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Да, улучшенное качество (+10%)", callback_data="quality:yes"))
    kb.add(InlineKeyboardButton("Нет, стандартное", callback_data="quality:no"))
    await call.message.answer("Выберите качество:", reply_markup=kb)
    await OrderState.waiting_for_quality.set()
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("quality:"), state=OrderState.waiting_for_quality)
async def confirm_order(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    quality = call.data.split(":")[1] == "yes"
    product = data['product']
    quantity = data['quantity']
    price = PRODUCTS[product][quantity]

    if quality:
        price = int(price * 1.1)

    await state.update_data(price=price, quality=quality)

    text = f"""<b>Ваш заказ:</b>
Товар: {product}
Количество: {quantity} г
Качество: {"улучшенное (+10%)" if quality else "стандартное"}
Цена: {price}₽

Подтверждаете?"""

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_order"))
    kb.add(InlineKeyboardButton("🔄 Изменить", callback_data="restart_order"))

    await call.message.answer(text, reply_markup=kb)
    await OrderState.confirming_order.set()
    await call.answer()


@dp.callback_query_handler(lambda c: c.data == "confirm_order", state=OrderState.confirming_order)
async def process_confirmation(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Укажите город и район для доставки:")
    await OrderState.waiting_for_comment.set()
    await call.answer()


@dp.message_handler(state=OrderState.waiting_for_comment)
async def process_comment(message: types.Message, state: FSMContext):
    comment = message.text
    data = await state.get_data()

    # Save order
    user_id = message.from_user.id
    user_orders[user_id] = {
        'product': data['product'],
        'quantity': data['quantity'],
        'quality': data['quality'],
        'price': data['price'],
        'comment': comment,
        'timestamp': datetime.now().strftime("%d.%m.%y %H:%M:%S")
    }

    # Notify admin
    if ADMIN_ID:
        order_text = f"""🛒 Новый заказ!
Пользователь: @{message.from_user.username or message.from_user.id}
Товар: {data['product']} {data['quantity']} г
Качество: {"улучшенное" if data['quality'] else "стандартное"}
Цена: {data['price']}₽
Комментарий: {comment}"""

        await bot.send_message(ADMIN_ID, order_text)

    await message.answer("✅ Заказ оформлен! С вами свяжутся для уточнения деталей.", reply_markup=main_kb)
    await state.finish()


@dp.callback_query_handler(lambda c: c.data == "restart_order", state="*")
async def restart_order(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await start_order(call.message)
    await call.answer()


@dp.message_handler(lambda m: m.text == "📩 Связаться с админом")
async def contact_admin(message: types.Message):
    if message.from_user.id in banned_users:
        return

    user_contacting_admin[message.from_user.id] = message.from_user.username or ""
    username_to_id[f"@{message.from_user.username}"] = message.from_user.id
    awaiting_admin_reply.add(message.from_user.id)

    await message.answer("Напишите ваше сообщение администратору:", reply_markup=back_kb)
    log_message(message.from_user.id, "Запрос связи с админом")


@dp.message_handler(content_types=['text', 'photo'])
async def handle_messages(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        # Handle admin replies
        if message.text and message.text.startswith("/ответ"):
            parts = message.text.split(maxsplit=2)
            if len(parts) < 3:
                await message.reply("Используйте: /ответ @username сообщение")
                return

            user_id = await resolve_user_id(parts[1])
            if user_id:
                try:
                    # Delete "message sent" notification
                    async for msg in bot.iter_history(user_id, limit=10):
                        if msg.text == "✅ Сообщение отправлено администратору. Ожидайте ответа.":
                            await bot.delete_message(user_id, msg.message_id)
                            break

                    await bot.send_message(user_id, f"📬 Ответ администратора:\n\n{parts[2]}")
                    await message.reply("✅ Ответ отправлен.")
                    log_message(user_id, f"Ответ админа: {parts[2]}", is_admin=True)
                except Exception as e:
                    await message.reply(f"Ошибка: {str(e)}")
            else:
                await message.reply("Пользователь не найден")
            return

    if message.from_user.id in awaiting_admin_reply:
        if message.photo:
            photo = message.photo[-1]
            photo_name = await save_photo(photo, message.from_user.id)
            await bot.send_photo(
                ADMIN_ID,
                photo.file_id,
                caption=f"📸 Фото от @{message.from_user.username or message.from_user.id}"
            )
            log_message(message.from_user.id, photo_name, is_photo=True)
        else:
            await bot.send_message(
                ADMIN_ID,
                f"📩 Сообщение от @{message.from_user.username or message.from_user.id}:\n{message.text}"
            )
            log_message(message.from_user.id, message.text)

        await message.answer("✅ Сообщение отправлено администратору. Ожидайте ответа.")
        awaiting_admin_reply.discard(message.from_user.id)
    else:
        await message.answer("Используйте кнопки меню", reply_markup=main_kb)


if __name__ == '__main__':
    print("🚀 Бот запускается...")
    # Load existing logs
    for filename in os.listdir('chat_logs'):
        if filename.startswith('user_') and filename.endswith('.txt'):
            user_id = int(filename[5:-4])
            chat_logs[user_id] = load_chat_logs(user_id)

    executor.start_polling(dp, skip_updates=True)