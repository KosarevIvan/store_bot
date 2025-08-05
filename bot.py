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

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, parse_mode='HTML')
dp = Dispatcher(bot, storage=MemoryStorage())

# Структуры данных
banned_users = set()
user_contacting_admin = {}  # user_id: username
username_to_id = {}  # username: user_id
awaiting_admin_reply = set()
user_orders = {}  # user_id: order_data
chat_logs = {}  # user_id: [messages]

# Создаем папки для логов и фото, если их нет
if not os.path.exists('chat_logs'):
    os.makedirs('chat_logs')
if not os.path.exists('chat_logs/photos'):
    os.makedirs('chat_logs/photos')


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

# Клавиатуры
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("🛒 Оформить заказ")
main_kb.add("📦 Фото со склада", "📩 Связаться с админом")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅️ На главную")


# Вспомогательные функции
def get_time_stamp():
    msk_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(msk_tz)
    return now.strftime("%d.%m.%y %H:%M:%S")


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


async def save_photo(photo: types.PhotoSize, user_id: int) -> str:
    """Сохраняет фото на диск и возвращает имя файла"""
    # Создаем уникальное имя файла
    file_ext = photo.file_unique_id[-4:]  # используем часть уникального ID
    filename = f"{user_id}_{uuid.uuid4().hex[:8]}_{file_ext}.jpg"
    file_path = f"chat_logs/photos/{filename}"

    # Скачиваем фото
    await photo.download(destination_file=file_path)
    return filename


def log_message(user_id: int, message: str, is_admin: bool = False, is_photo: bool = False):
    """Логирование сообщений в чате"""
    if user_id not in chat_logs:
        chat_logs[user_id] = []

    timestamp = datetime.now().strftime("%d.%m.%y %H:%M:%S")
    username = "admin" if is_admin else f"{username_to_id.get(f'@{user_id}', 'user')}({user_id})"

    if is_photo:
        log_entry = f"{timestamp} @{username}: [фото_{message}]"
    else:
        log_entry = f"{timestamp} @{username}: {message}"

    chat_logs[user_id].append(log_entry)

    # Сохраняем в файл
    filename = f"chat_logs/user_{user_id}.txt"
    try:
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(log_entry + "\n")
    except Exception as e:
        logging.error(f"Error saving chat log: {e}")


def load_chat_logs(user_id: int):
    """Загрузка истории чата из файла"""
    filename = f"chat_logs/user_{user_id}.txt"
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read().splitlines()
        except Exception as e:
            logging.error(f"Error loading chat log: {e}")
    return []


# Обработчики команд
@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    if message.from_user.id in banned_users:
        return
    log_message(message.from_user.id, "/start")
    await message.answer(format_welcome(), reply_markup=main_kb)


@dp.message_handler(lambda m: m.text == "⬅️ На главную")
async def back_to_main(message: types.Message):
    log_message(message.from_user.id, "На главную")
    await message.answer(format_welcome(), reply_markup=main_kb)


@dp.message_handler(commands=['ban'])
async def ban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /ban user_id или /ban @username")
        return
    arg = parts[1]
    if arg.startswith("@"):  # бан по нику
        uid = username_to_id.get(arg)
        if uid:
            banned_users.add(uid)
            await message.reply(f"🚫 Пользователь {arg} ({uid}) заблокирован.")
        else:
            await message.reply("❗ Пользователь не найден.")
    else:
        try:
            uid = int(arg)
            banned_users.add(uid)
            await message.reply(f"🚫 Пользователь {uid} заблокирован.")
        except:
            await message.reply("❗ Неверный ID.")
    log_message(message.from_user.id, f"/ban {arg}", is_admin=True)


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
    except:
        await message.reply("❗ Неверный ID.")
    log_message(message.from_user.id, f"/unban {parts[1]}", is_admin=True)


@dp.message_handler(commands=['очистить'])
async def clear_chat(message: types.Message):
    """Очистка чата с пользователем (только для админа)"""
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /очистить @username или /очистить user_id")
        return

    target = parts[1]
    user_id = None

    if target.startswith("@"):
        user_id = username_to_id.get(target)
    else:
        try:
            user_id = int(target)
        except ValueError:
            pass

    if user_id:
        try:
            # Очищаем логи
            chat_logs[user_id] = []
            filename = f"chat_logs/user_{user_id}.txt"
            if os.path.exists(filename):
                os.remove(filename)

            # Удаляем фото пользователя
            photo_dir = f"chat_logs/photos/"
            for photo_file in os.listdir(photo_dir):
                if photo_file.startswith(f"{user_id}_"):
                    os.remove(os.path.join(photo_dir, photo_file))

            await message.reply(f"✅ Чат с пользователем {target} очищен. Логи удалены.")
        except Exception as e:
            await message.reply(f"❌ Ошибка при очистке чата: {str(e)}")
    else:
        await message.reply("❗ Пользователь не найден.")

    log_message(message.from_user.id, f"/очистить {target}", is_admin=True)


@dp.message_handler(commands=['история'])
async def view_chat_history(message: types.Message):
    """Просмотр истории переписки с пользователем (только для админа)"""
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /история @username или /история user_id")
        return

    target = parts[1]
    user_id = None

    if target.startswith("@"):
        user_id = username_to_id.get(target)
    else:
        try:
            user_id = int(target)
        except ValueError:
            pass

    if user_id:
        history = load_chat_logs(user_id)
        if history:
            # Разбиваем на части, если история большая
            chunks = [history[i:i + 20] for i in range(0, len(history), 20)]
            for chunk in chunks:
                text = f"📝 История переписки с {target} (ID: {user_id}):\n\n" + "\n".join(chunk)
                await message.answer(text)
        else:
            await message.reply(f"История переписки с {target} пуста.")
    else:
        await message.reply("❗ Пользователь не найден.")

    log_message(message.from_user.id, f"/история {target}", is_admin=True)


@dp.message_handler(commands=['оплата'])
async def send_payment(message: types.Message):
    """Отправка ссылки на оплату (только для админа)"""
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.reply("❗ Формат: /оплата @username ссылка_на_оплату")
        return

    target = parts[1]
    payment_link = parts[2]
    user_id = None

    if target.startswith("@"):
        user_id = username_to_id.get(target)
    else:
        try:
            user_id = int(target)
        except ValueError:
            pass

    if user_id:
        order_data = user_orders.get(user_id)
        if order_data:
            payment_message = f"""💳 Подтверждение оплаты заказа

Здравствуйте!
Ваш заказ принят:

🔹 Товар: {order_data['product']}
🔹 Граммовка: {order_data['quantity']} г
🔹 Качество: {'улучшенное' if order_data['quality'] else 'стандартное'}
🔹 Стоимость: {order_data['price']}₽

💰 Для оплаты перейдите по ссылке:
{payment_link}

После оплаты пришлите скриншот или чек в ответ на это сообщение.
Как только платеж будет подтверждён, мы приступим к доставке.

🚀 Спасибо за заказ!
Если остались вопросы — пишите сюда."""

            try:
                await bot.send_message(user_id, payment_message)
                await message.reply(f"✅ Сообщение об оплате отправлено пользователю {target}")
            except Exception as e:
                await message.reply(f"❌ Не удалось отправить сообщение: {str(e)}")
        else:
            await message.reply("❗ У этого пользователя нет активного заказа.")
    else:
        await message.reply("❗ Пользователь не найден.")

    log_message(message.from_user.id, f"/оплата {target}", is_admin=True)


@dp.message_handler(lambda m: m.text == "📦 Фото со склада")
async def show_photos(message: types.Message, state: FSMContext):
    log_message(message.from_user.id, "Просмотр фото")
    kb = InlineKeyboardMarkup()
    for product in PHOTOS:
        kb.add(InlineKeyboardButton(text=product, callback_data=f"photo:{product}"))
    await message.answer("📸 Выберите товар для просмотра фото:", reply_markup=kb)
    await state.update_data(last_photo_id=None)


@dp.callback_query_handler(lambda c: c.data.startswith("photo:"))
async def send_photo(call: types.CallbackQuery, state: FSMContext):
    product = call.data.split(":")[1]
    photo_path = PHOTOS.get(product)

    data = await state.get_data()
    last_photo_id = data.get("last_photo")

    # Удаляем предыдущее фото, если есть
    if last_photo_id:
        try:
            await bot.delete_message(call.message.chat.id, last_photo_id)
        except:
            pass

    if photo_path:
        sent = await call.message.answer_photo(InputFile(photo_path))
        await state.update_data(last_photo=sent.message_id)
    else:
        await call.message.answer("⚠️ Фото не найдено.")
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
    await call.message.answer("Выберите граммовку:", reply_markup=kb)
    await OrderState.waiting_for_quantity.set()
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("qty:"), state=OrderState.waiting_for_quantity)
async def choose_quality(call: types.CallbackQuery, state: FSMContext):
    quantity = int(call.data.split(":")[1])
    await state.update_data(quantity=quantity)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Да, хочу улучшеное качество", callback_data="quality:yes"))
    kb.add(InlineKeyboardButton("Нет, спасибо", callback_data="quality:no"))
    await call.message.answer("Добавить улучшенное качество за +10%?", reply_markup=kb)
    await OrderState.waiting_for_quality.set()
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("quality:"), state=OrderState.waiting_for_quality)
async def confirm_order(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    quality = call.data.split(":")[1] == "yes"
    product, qty = data['product'], data['quantity']
    price = PRODUCTS[product][qty]
    if quality:
        price = int(price * 1.1)
    await state.update_data(quality=quality, price=price)
    text = f"<b>Ваш заказ:</b>\nТовар: {product}\nГраммовка: {qty} г\nКачество: {'Улучшенное (+10%)' if quality else 'Стандартное'}\n\n<b>Итого: {price}₽</b>\n\nНажмите кнопку ниже, чтобы подтвердить заказ."
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Подтверждаю, оплатить", callback_data="confirm"))
    kb.add(InlineKeyboardButton("🔄 Перевыбрать товар", callback_data="restart"))
    await call.message.answer(text, reply_markup=kb)
    await OrderState.confirming_order.set()
    await call.answer()


@dp.callback_query_handler(lambda c: c.data == "confirm", state=OrderState.confirming_order)
async def ask_comment(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer(
        "📍 Уточните город и район для доставки. Например: Санкт-Петербург, Василеостровский район")
    await OrderState.waiting_for_comment.set()
    await call.answer()


@dp.callback_query_handler(lambda c: c.data == "restart", state="*")
async def restart_order(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await start_order(call.message)
    await call.answer()


@dp.message_handler(state=OrderState.waiting_for_comment)
async def finish_order(message: types.Message, state: FSMContext):
    comment = message.text.strip()
    data = await state.get_data()
    user_id = message.from_user.id
    username = message.from_user.username
    user_ref = f"@{username}" if username else f"ID: {user_id}"

    # Сохраняем заказ
    user_orders[user_id] = {
        'product': data['product'],
        'quantity': data['quantity'],
        'quality': data['quality'],
        'price': data['price'],
        'comment': comment,
        'timestamp': datetime.now().strftime("%d.%m.%y %H:%M:%S")
    }

    order_text = f"🛒 Новый заказ от {user_ref} (ID: {user_id}):\n" \
                 f"Товар: {data['product']}\nГраммовка: {data['quantity']} г\n" \
                 f"Качество: {'Улучшенное' if data['quality'] else 'Стандартное'}\nЦена: {data['price']}₽\n\nКомментарий: {comment}"

    if ADMIN_ID:
        await bot.send_message(ADMIN_ID, order_text)

    await message.answer("✅ Ваш заказ принят! Скоро с вами свяжутся. Спасибо за покупку!", reply_markup=main_kb)
    await state.finish()
    log_message(user_id, f"Оформлен заказ: {order_text}")


@dp.message_handler(lambda m: m.text == "📩 Связаться с админом")
async def contact_admin(message: types.Message):
    if message.from_user.id in banned_users:
        return
    user_contacting_admin[message.from_user.id] = message.from_user.username or ""
    username_to_id[f"@{message.from_user.username}"] = message.from_user.id
    awaiting_admin_reply.add(message.from_user.id)
    await message.answer(
        "📝 Напишите ваше сообщение для администратора, имейте ввиду, что фото и сообщение следует отправлять отдельными запросами",
        reply_markup=back_kb)
    log_message(message.from_user.id, "Запрос связи с админом")


@dp.message_handler(content_types=['text', 'photo'])
async def handle_message(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        if message.text and message.text.startswith("/ответ"):
            parts = message.text.split(maxsplit=2)
            if len(parts) < 3:
                await message.reply("❗ Формат: /ответ @username сообщение")
                return
            recipient = parts[1]
            reply = parts[2]
            uid = username_to_id.get(recipient)
            if uid:
                # Удаляем предыдущее сообщение бота у клиента
                try:
                    async for msg in bot.iter_history(uid, limit=10):
                        if msg.text == "✅ Сообщение отправлено администратору. Ожидайте ответа.":
                            await bot.delete_message(uid, msg.message_id)
                            break
                except:
                    pass

                await bot.send_message(uid, f"📬 Сообщение от администратора:\n\n{reply}")
                await message.reply("✅ Ответ отправлен.")
                log_message(uid, f"Ответ админа: {reply}", is_admin=True)
            else:
                await message.reply("❗ Пользователь не найден.")
            return

        # Логируем сообщения админа
        if message.text and not message.text.startswith("/"):
            log_message(message.from_user.id, message.text, is_admin=True)

    if message.from_user.id in awaiting_admin_reply:
        text = f"📩 Сообщение от @{message.from_user.username or 'без ника'} (ID: {message.from_user.id}):"
        if message.photo:
            photo = message.photo[-1]
            photo_filename = await save_photo(photo, message.from_user.id)
            await bot.send_photo(ADMIN_ID, photo.file_id, caption=text)
            log_message(message.from_user.id, photo_filename, is_photo=True)
        else:
            await bot.send_message(ADMIN_ID, f"{text}\n{message.text}")
            log_message(message.from_user.id, message.text)
        await message.answer("✅ Сообщение отправлено администратору. Ожидайте ответа.")
        awaiting_admin_reply.discard(message.from_user.id)
    else:
        await message.answer("Нажмите ⬅️ На главную или воспользуйтесь меню.")


if __name__ == '__main__':
    print("🚀 Бот запускается...")
    # Загружаем существующие логи при старте
    for filename in os.listdir('chat_logs'):
        if filename.startswith('user_') and filename.endswith('.txt'):
            user_id = int(filename[5:-4])
            chat_logs[user_id] = load_chat_logs(user_id)

    executor.start_polling(dp, skip_updates=True)