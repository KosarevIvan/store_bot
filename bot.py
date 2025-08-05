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

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

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
    now = datetime.now()
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

📅 Актуализировано {get_time_stamp()}
🔒 Все заказы перед доставкой проходят контроль качества.
🚀 Доставка — быстрая и надёжная. Скорее всего, клад уже ждёт Вас в вашем районе.
Ваш <b>Elysium One</b> — где сладости становятся эксклюзивом.
"""

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    await message.answer(format_welcome(), parse_mode='HTML', reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "📦 Фото со склада")
async def photos_handler(message: types.Message):
    kb = InlineKeyboardMarkup()
    for name in PRODUCTS:
        kb.add(InlineKeyboardButton(name, callback_data=f"photo:{name}"))
    await message.answer("Выберите товар:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "📩 Связаться с админом")
async def contact_admin(message: types.Message):
    await message.answer("Введите ваше сообщение, мы передадим его администратору.")

@dp.message_handler(lambda m: m.text == "🛒 Оформить заказ")
async def order_start(message: types.Message):
    kb = InlineKeyboardMarkup()
    for name in PRODUCTS:
        kb.add(InlineKeyboardButton(name, callback_data=f"order:{name}"))
    await message.answer("Выберите товар:", reply_markup=kb)
    await OrderState.waiting_for_product.set()

@dp.callback_query_handler(lambda c: c.data.startswith("photo:"))
async def send_photo(call: types.CallbackQuery):
    product = call.data.split(":")[1]
    photo_path = PHOTOS.get(product)
    if photo_path:
        await call.message.answer_photo(InputFile(photo_path))
    else:
        await call.message.answer("Фото не найдено.")
    await call.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("order:"), state=OrderState.waiting_for_product)
async def choose_quantity(call: types.CallbackQuery, state: FSMContext):
    product = call.data.split(":")[1]
    await state.update_data(product=product)
    kb = InlineKeyboardMarkup()
    for qty in PRODUCTS[product]:
        kb.add(InlineKeyboardButton(f"{qty} г", callback_data=f"qty:{qty}"))
    await call.message.answer("Выберите граммовку:", reply_markup=kb)
    await OrderState.waiting_for_quantity.set()
    await call.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("qty:"), state=OrderState.waiting_for_quantity)
async def choose_quality(call: types.CallbackQuery, state: FSMContext):
    qty = int(call.data.split(":")[1])
    await state.update_data(quantity=qty)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Да, улучшить качество (+10%)", callback_data="quality:yes"))
    kb.add(InlineKeyboardButton("❌ Нет, оставить как есть", callback_data="quality:no"))
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

    text = f"<b>Ваш заказ:</b>\nТовар: {product}\nГраммовка: {qty} г\nКачество: {'Улучшенное (+10%)' if quality else 'Стандартное'}\n\n<b>Итого: {price}₽</b>\n\nДля оформления заказа напишите 'Подтверждаю'."
    await state.update_data(price=price, quality=quality)
    await call.message.answer(text, parse_mode='HTML')
    await OrderState.confirming_order.set()
    await call.answer()

@dp.message_handler(lambda m: m.text.lower() == "подтверждаю", state=OrderState.confirming_order)
async def finish_order(message: types.Message, state: FSMContext):
    await message.answer("📍 Уточните город и район для доставки. Например: Москва, САО")
    await OrderState.waiting_for_comment.set()

@dp.message_handler(state=OrderState.waiting_for_comment)
async def receive_comment(message: types.Message, state: FSMContext):
    comment = message.text.strip()
    data = await state.get_data()
    user_id = message.from_user.id
    username = message.from_user.username
    user_ref = f"@{username}" if username else f"ID: {user_id}"
    order_text = f"🛒 Новый заказ от {user_ref} (ID: {user_id}):\n" \
                 f"Товар: {data['product']}\nГраммовка: {data['quantity']} г\nКачество: {'Улучшенное' if data['quality'] else 'Стандартное'}\nЦена: {data['price']}₽\n\nКомментарий: {comment}"
    if ADMIN_ID:
        await bot.send_message(ADMIN_ID, order_text)
    await message.answer("✅ Ваш заказ принят! Скоро с вами свяжутся. Спасибо за покупку!", reply_markup=main_kb)
    await state.finish()

@dp.message_handler()
async def relay_to_admin(message: types.Message):
    if message.from_user.id == ADMIN_ID and message.text.startswith("/ответ"):
        parts = message.text.split(' ', 2)
        if len(parts) < 3:
            await message.reply("❗ Формат: /ответ user_id сообщение")
            return
        target = parts[1]
        response = parts[2]

        if target.startswith("@"):  # ответ по username не поддерживается Telegram API
            await message.reply("❌ Нельзя отправить сообщение только по username. Используй user_id.")
            return

        try:
            await bot.send_message(target, f"📬 Сообщение от администратора:\n\n{response}")
            await message.reply("✅ Ответ отправлен пользователю.")
        except Exception as e:
            await message.reply(f"❌ Ошибка отправки: {e}")
    else:
        username = message.from_user.username
        user_ref = f"@{username}" if username else f"ID: {message.from_user.id}"
        if ADMIN_ID:
            await bot.send_message(ADMIN_ID, f"📩 Сообщение от {user_ref} (ID: {message.from_user.id}): {message.text}")
            await message.answer("Ваше сообщение передано администратору. Он свяжется с вами в ближайшее время.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)