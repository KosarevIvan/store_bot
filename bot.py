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
user_contacting_admin = {}  # user_id: username
username_to_id = {}  # username: user_id
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

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅️ На главную")

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

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    if message.from_user.id in banned_users:
        return
    await message.answer(format_welcome(), reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "⬅️ На главную")
async def back_to_main(message: types.Message):
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

@dp.message_handler(lambda m: m.text == "📦 Фото со склада")
async def show_photos(message: types.Message):
    kb = InlineKeyboardMarkup()
    for product in PHOTOS:
        kb.add(InlineKeyboardButton(text=product, callback_data=f"photo:{product}"))
    await message.answer("📸 Выберите товар для просмотра фото:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("photo:"))
async def send_photo(call: types.CallbackQuery):
    product = call.data.split(":")[1]
    photo_path = PHOTOS.get(product)
    if photo_path:
        await call.message.answer_photo(InputFile(photo_path))
    else:
        await call.message.answer("⚠️ Фото не найдено.")
    await call.answer()

@dp.message_handler(lambda m: m.text == "🛒 Оформить заказ")
async def start_order(message: types.Message):
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
    await call.message.answer("📍 Уточните город и район для доставки. Например: Санкт-Петербург, Василеостровский район")
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
    order_text = f"🛒 Новый заказ от {user_ref} (ID: {user_id}):\n" \
                 f"Товар: {data['product']}\nГраммовка: {data['quantity']} г\n" \
                 f"Качество: {'Улучшенное' if data['quality'] else 'Стандартное'}\nЦена: {data['price']}₽\n\nКомментарий: {comment}"
    if ADMIN_ID:
        await bot.send_message(ADMIN_ID, order_text)
    await message.answer("✅ Ваш заказ принят! Скоро с вами свяжутся. Спасибо за покупку!", reply_markup=main_kb)
    await state.finish()

@dp.message_handler(lambda m: m.text == "📩 Связаться с админом")
async def contact_admin(message: types.Message):
    if message.from_user.id in banned_users:
        return
    user_contacting_admin[message.from_user.id] = message.from_user.username or ""
    username_to_id[f"@{message.from_user.username}"] = message.from_user.id
    awaiting_admin_reply.add(message.from_user.id)
    await message.answer("📝 Напишите ваше сообщение для администратора:", reply_markup=back_kb)
    await bot.send_message(ADMIN_ID, f"📩 Сообщение от @{message.from_user.username} (ID: {message.from_user.id}): \nСвязаться с админом")

@dp.message_handler(content_types=['text', 'photo'])
async def handle_message(message: types.Message):
    if message.from_user.id == ADMIN_ID and message.text and message.text.startswith("/ответ"):
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.reply("❗ Формат: /ответ @username сообщение")
            return
        recipient = parts[1]
        reply = parts[2]
        uid = username_to_id.get(recipient)
        if uid:
            await bot.send_message(uid, f"📬 Сообщение от администратора:\n\n{reply}")
            await message.reply("✅ Ответ отправлен.")
        else:
            await message.reply("❗ Пользователь не найден.")
        return

    if message.from_user.id in awaiting_admin_reply:
        text = f"📩 Сообщение от @{message.from_user.username or 'без ника'} (ID: {message.from_user.id}):"
        if message.photo:
            photo = message.photo[-1]
            await bot.send_photo(ADMIN_ID, photo.file_id, caption=text)
        else:
            await bot.send_message(ADMIN_ID, f"{text}\n{message.text}")
        await message.answer("✅ Сообщение отправлено администратору. Ожидайте ответа.")
        awaiting_admin_reply.discard(message.from_user.id)
    else:
        await message.answer("Нажмите ⬅️ На главную или воспользуйтесь меню.")

if __name__ == '__main__':
    print("🚀 Бот запускается...")
    executor.start_polling(dp, skip_updates=True)
