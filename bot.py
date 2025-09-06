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
username_to_id = {}  # username: user_id
awaiting_admin_reply = set()
user_orders = {}
chat_logs = {}
message_ids = {}  # user_id: [message_ids]
unanswered_clients = set()  # Множество пользователей без ответа

# Create directories
os.makedirs('chat_logs', exist_ok=True)
os.makedirs('chat_logs/photos', exist_ok=True)


class OrderState(StatesGroup):
    waiting_for_product = State()
    waiting_for_quantity = State()
    waiting_for_quality = State()
    confirming_order = State()
    waiting_for_comment = State()


class RulesState(StatesGroup):
    waiting_for_accept = State()


# Products and photos configuration
PRODUCTS = {
    "Мефедрон": {1: 2790, 2: 4790, 3: 5990},
    "Марихуана": {1: 1690, 2: 1990, 3: 2490},
    "Амфетамин": {1: 1290, 2: 2190, 3: 2990},
}

PHOTOS = {
    "Мефедрон": "data/photos/fedya.jpg",
    "Марихуана": "data/photos/boby.jpg",
    "Амфетамин": "data/photos/metall.jpg",
}

# Rules text
RULES_TEXT = """
📜 <b>Правила использования телеграм-бота @ElysiumOneBot</b>

1. <b>Пользователь</b> - лицо, запустившее бота @ElysiumOneBot через команду /start или любую другую команду для продолжения использования.

2. Продолжая использование бота @ElysiumOneBot, пользователь принимает все последующие правила безоговорочно.

3. Данный телеграм-бот @ElysiumOneBot создан исключительно для тестирования функционала и возможностей Telegram API.

4. Совершая перевод денежных средств по ссылкам и/или номерам телефонов и/или реквизитам, отправленным пользователю в этом телеграм-боте @ElysiumOneBot, пользователь совершает добровольное пожертвование на личные нужды Администрации @ElysiumOneBot без каких-либо обязательств со стороны Администрации.

5. Весь контент (включая фотографии, тексты, описания), отправляемый в чате с @ElysiumOneBot со стороны администрации, является сгенерированным нейросетью или вымышленным. Любые совпадения с реальностью случайны и непреднамеренны.

6. Администрация @ElysiumOneBot сохраняет за собой право вести логирование активности пользователя для внутренних целей без передачи третьим лицам.

7. Переходя по любым ссылкам, отправленным телеграм-ботом @ElysiumOneBot, пользователь принимает всю ответственность за свои действия исключительно на себя.

8. Администрация телеграм-бота @ElysiumOneBot не несёт ответственности за любую активность пользователя.

9. Все сообщения, отправленные Администрацией телеграм-бота @ElysiumOneBot, являются вымышленными.

10. Администрация оставляет за собой право блокировать доступ к боту без объяснения причин.

11. Все товары, упомянутые в боте, являются вымыслом. Реальная возможность приобретения отсутствует.

12. Пользователь соглашается с тем, что любые действия совершаются им на свой собственный риск.

13. Администрация не гарантирует бесперебойную работу бота.

14. Использование бота означает полное согласие со всеми пунктами правил.

15. Администрация оставляет за собой право изменять правила в любое время.
"""

# Keyboards
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("🛒 Оформить заказ")
main_kb.add("📦 Фото со склада", "📩 Связаться с админом")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅️ На главную")

rules_kb = ReplyKeyboardMarkup(resize_keyboard=True)
rules_kb.add(KeyboardButton("✅ Принимаю"))
rules_kb.add(KeyboardButton("📄 Правила использования"))


def format_welcome():
    return f"""
Добро пожаловать в наш магазин Elysium One — где каждый грамм удовольствия становится искусством.
🍬 Наш актуальный ассортимент премиальных веществ:

<b>Марихуана</b>
1г — 1 690₽
2г — 1 990₽ 
3г — 2 490₽ 

<b>Мефедрон</b>
1г — 2 790₽
2г — 4 790₽ 
3г — 5 990₽

<b>Амфетамин</b>
1г — 1 290₽
2г — 2 190₽ 
3г — 2 990₽ 

🎯 <b>Специальное предложение:</b>
Вы можете приобрести товар высшего качества, добавив всего 10% к стоимости заказа.

Если вас интересуют другие вещества или граммовки — мы готовы обсудить индивидуальное предложение специально для Вас.

📍 Сейчас шоп работает во многих городах России, для уточнения адреса доставки просто укажите город и район при заказе.

📅 Актуализировано {get_time_stamp()} (по МСК)
🔒 Все заказы перед доставкой проходят контроль качества.
🚀 Доставка — быстрая и надёжная. Скорее всего, клад уже ждёт Вас в вашем районе.
Ваш <b>Elysium One</b> — где сладости становятся эксклюзивом.
"""


def get_time_stamp():
    msk_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(msk_tz)
    rounded = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
    return rounded.strftime("%d.%m.%Y в %H:%M")


async def save_photo(photo: types.PhotoSize, user_id: int) -> str:
    file_ext = photo.file_unique_id[-4:]
    filename = f"{user_id}_{uuid.uuid4().hex[:8]}_{file_ext}.jpg"
    file_path = f"chat_logs/photos/{filename}"
    await photo.download(destination_file=file_path)
    return filename


def log_message(user_id: int, message: str, is_admin: bool = False, is_photo: bool = False):
    if user_id not in chat_logs:
        chat_logs[user_id] = []

    if is_admin and is_photo:
        return

    timestamp = datetime.now().strftime("%d.%m.%y %H:%M:%S")
    username = "admin" if is_admin else f"{username_to_id.get(f'@{user_id}', 'user')}({user_id})"

    if is_photo:
        log_entry = f"{timestamp} @{username}: [фото_{message}]"
    else:
        log_entry = f"{timestamp} @{username}: {message}"

    chat_logs[user_id].append(log_entry)

    filename = f"chat_logs/user_{user_id}.txt"
    try:
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(log_entry + "\n")
    except Exception as e:
        logging.error(f"Error saving chat log: {e}")


def load_chat_logs(user_id: int):
    filename = f"chat_logs/user_{user_id}.txt"
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read().splitlines()
        except Exception as e:
            logging.error(f"Error loading chat log: {e}")
    return []


async def delete_user_messages(user_id: int):
    try:
        if user_id in message_ids:
            for msg_id in message_ids[user_id]:
                try:
                    await bot.delete_message(chat_id=user_id, message_id=msg_id)
                except Exception as e:
                    logging.error(f"Error deleting message {msg_id}: {e}")
            message_ids[user_id] = []
    except Exception as e:
        logging.error(f"Error deleting messages: {e}")


async def resolve_user(target: str):
    if target.startswith("@"):
        user_id = username_to_id.get(target)
        if not user_id:
            return None, "Пользователь с таким username не найден"
        return user_id, None
    try:
        return int(target), None
    except ValueError:
        return None, "Некорректный ID пользователя"


async def check_banned(user_id: int):
    if user_id in banned_users:
        return True
    return False


def update_unanswered_clients(user_id: int, is_admin_reply: bool = False):
    if is_admin_reply:
        unanswered_clients.discard(user_id)
    else:
        unanswered_clients.add(user_id)


@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    if await check_banned(message.from_user.id):
        return

    if message.from_user.username:
        username_to_id[f"@{message.from_user.username}"] = message.from_user.id

    log_message(message.from_user.id, "/start")

    # Для администратора - особый случай
    if message.from_user.id == ADMIN_ID:
        await message.answer("🔐 Администраторский доступ активирован", reply_markup=main_kb)
        return

    await message.answer("🔒 Для начала работы примите правила использования данного телеграм-бота",
                         reply_markup=rules_kb)
    await RulesState.waiting_for_accept.set()


@dp.message_handler(lambda m: m.text == "📄 Правила использования", state="*")
async def show_rules(message: types.Message):
    await message.answer(RULES_TEXT, parse_mode='HTML')


@dp.message_handler(lambda m: m.text == "✅ Принимаю", state=RulesState.waiting_for_accept)
async def accept_rules(message: types.Message, state: FSMContext):
    log_message(message.from_user.id, "Принял правила")
    await state.finish()
    await message.answer(format_welcome(), reply_markup=main_kb)


@dp.message_handler(commands=['клиенты'])
async def show_unanswered_clients(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    if not unanswered_clients:
        await message.reply("Нет неотвеченных клиентов.")
        return

    clients_list = []
    for user_id in unanswered_clients:
        username = username_to_id.get(f"@{user_id}", f"ID:{user_id}")
        clients_list.append(f"👤 {username}")

    response = "📋 Список неотвеченных клиентов:\n\n" + "\n".join(clients_list)
    await message.reply(response)


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


@dp.message_handler(commands=['ban'])
async def ban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /ban @username или /ban user_id")
        return

    user_id, error = await resolve_user(parts[1])
    if error:
        await message.reply(f"❗ {error}")
        return

    banned_users.add(user_id)
    await message.reply(f"🚫 Пользователь {parts[1]} ({user_id}) заблокирован.")
    log_message(message.from_user.id, f"/ban {parts[1]}", is_admin=True)


@dp.message_handler(commands=['unban'])
async def unban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /unban @username или /unban user_id")
        return

    user_id, error = await resolve_user(parts[1])
    if error:
        await message.reply(f"❗ {error}")
        return

    banned_users.discard(user_id)
    await message.reply(f"✅ Пользователь {parts[1]} ({user_id}) разблокирован.")
    log_message(message.from_user.id, f"/unban {parts[1]}", is_admin=True)


@dp.message_handler(commands=['очистить'])
async def clear_chat(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /очистить @username или /очистить user_id")
        return

    user_id, error = await resolve_user(parts[1])
    if error:
        await message.reply(f"❗ {error}")
        return

    try:
        chat_logs[user_id] = []
        filename = f"chat_logs/user_{user_id}.txt"
        if os.path.exists(filename):
            os.remove(filename)

        await delete_user_messages(user_id)

        await message.reply(f"✅ Чат с пользователем {parts[1]} ({user_id}) полностью очищен.")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {str(e)}")

    log_message(message.from_user.id, f"/очистить {parts[1]}", is_admin=True)


@dp.message_handler(commands=['история'])
async def view_chat_history(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❗ Формат: /история @username или /история user_id")
        return

    user_id, error = await resolve_user(parts[1])
    if error:
        await message.reply(f"❗ {error}")
        return

    history = load_chat_logs(user_id)
    if history:
        chunks = [history[i:i + 20] for i in range(0, len(history), 20)]
        for chunk in chunks:
            await message.answer("\n".join(chunk))
    else:
        await message.reply(f"История переписки с {parts[1]} ({user_id}) пуста.")

    log_message(message.from_user.id, f"/история {parts[1]}", is_admin=True)


@dp.message_handler(commands=['оплата'])
async def send_payment(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.reply("❗ Формат: /оплата @username ссылка_на_оплату")
        return

    user_id, error = await resolve_user(parts[1])
    if error:
        await message.reply(f"❗ {error}")
        return

    order_data = user_orders.get(user_id)
    if not order_data:
        await message.reply(f"❗ У пользователя {parts[1]} ({user_id}) нет активного заказа.")
        return

    username = f"@{message.from_user.username}" if message.from_user.username else f"ID:{message.from_user.id}"
    payment_msg = f"""💳 Подтверждение оплаты заказа

Здравствуйте!
Ваш заказ принят:

🔹 Товар: {order_data['product']}
🔹 Граммовка: {order_data['quantity']} г
🔹 Качество: {'улучшенное' if order_data['quality'] else 'стандартное'}
🔹 Стоимость: {order_data['price']}₽

💰 Реквизиты/ссылка для оплаты:
{parts[2]}

После оплаты пришлите скриншот через связь с админом."""

    try:
        await bot.send_message(user_id, payment_msg)
        await message.reply(f"✅ Сообщение об оплате отправлено пользователю {parts[1]} ({user_id})")
    except Exception as e:
        error_msg = f"❌ Ошибка: {str(e)}"
        if "bot was blocked by the user" in str(e).lower():
            error_msg = "❌ Пользователь заблокировал бота"
        await message.reply(error_msg)

    log_message(message.from_user.id, f"/оплата {parts[1]}", is_admin=True)


@dp.message_handler(commands=['ответ'], content_types=types.ContentTypes.ANY)
async def reply_to_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    if message.text:
        parts = message.text.split(maxsplit=2)
    elif message.caption:
        parts = message.caption.split(maxsplit=2)
    else:
        await message.reply("❗ Некорректный формат сообщения")
        return

    if len(parts) < 2:
        await message.reply("❗ Формат: /ответ @username текст ИЛИ /ответ user_id текст")
        return

    target = parts[1]
    reply_text = parts[2] if len(parts) > 2 else None
    user_id, error = await resolve_user(target)

    if error:
        await message.reply(f"❗ {error}")
        return

    try:
        admin_reply_prefix = "📬 Ответ администратора:\n\n"

        if message.photo:
            photo_caption = admin_reply_prefix + (reply_text if reply_text else "[фото]")
            sent_msg = await bot.send_photo(
                user_id,
                message.photo[-1].file_id,
                caption=photo_caption
            )
            await message.reply(f"✅ Фото отправлено пользователю {target} ({user_id})")
        elif reply_text:
            sent_msg = await bot.send_message(
                user_id,
                admin_reply_prefix + reply_text
            )
            await message.reply(f"✅ Ответ отправлен пользователю {target} ({user_id})")
        else:
            await message.reply("❗ Нет контента для отправки (текст или фото)")
            return

        if user_id not in message_ids:
            message_ids[user_id] = []
        message_ids[user_id].append(sent_msg.message_id)

        update_unanswered_clients(user_id, is_admin_reply=True)

        if reply_text:
            log_message(user_id, f"Ответ админа: {reply_text}", is_admin=True)

    except Exception as e:
        error_msg = f"❌ Ошибка: {str(e)}"
        if "bot was blocked by the user" in str(e).lower():
            error_msg = "❌ Пользователь заблокировал бота"
        await message.reply(error_msg)


@dp.message_handler(lambda m: m.text == "⬅️ На главную", state="*")
async def back_to_main(message: types.Message, state: FSMContext):
    if await check_banned(message.from_user.id):
        return

    log_message(message.from_user.id, "На главную")
    await state.finish()
    await message.answer(format_welcome(), reply_markup=main_kb)


@dp.message_handler(lambda m: m.text == "📦 Фото со склада", state="*")
async def show_photos(message: types.Message, state: FSMContext):
    if await check_banned(message.from_user.id):
        return

    current_state = await state.get_state()
    if current_state in [RulesState.waiting_for_accept.state]:
        await message.answer("Сначала примите правила использования бота", reply_markup=rules_kb)
        return

    log_message(message.from_user.id, "Просмотр фото товаров")
    kb = InlineKeyboardMarkup()
    for product in PHOTOS:
        kb.add(InlineKeyboardButton(text=product, callback_data=f"photo:{product}"))
    await message.answer("Выберите товар:", reply_markup=kb)
    await state.update_data(last_photo_id=None)


@dp.callback_query_handler(lambda c: c.data.startswith("photo:"), state="*")
async def send_product_photo(call: types.CallbackQuery, state: FSMContext):
    if await check_banned(call.from_user.id):
        await call.answer("Вы заблокированы", show_alert=True)
        return

    product = call.data.split(":")[1]
    photo_path = PHOTOS.get(product)

    data = await state.get_data()
    last_photo_id = data.get("last_photo_id")

    if last_photo_id:
        try:
            await bot.delete_message(chat_id=call.message.chat.id, message_id=last_photo_id)
        except:
            pass

    if photo_path:
        sent = await call.message.answer_photo(InputFile(photo_path))
        await state.update_data(last_photo_id=sent.message_id)
    else:
        await call.message.answer("Фото не найдено")
    await call.answer()


@dp.message_handler(lambda m: m.text == "🛒 Оформить заказ", state="*")
async def start_order(message: types.Message):
    if await check_banned(message.from_user.id):
        return

    current_state = await dp.current_state().get_state()
    if current_state in [RulesState.waiting_for_accept.state]:
        await message.answer("Сначала примите правила использования бота", reply_markup=rules_kb)
        return

    log_message(message.from_user.id, "Начало оформления заказа")
    kb = InlineKeyboardMarkup()
    for product in PRODUCTS:
        kb.add(InlineKeyboardButton(text=product, callback_data=f"order:{product}"))
    await message.answer("Выберите товар:", reply_markup=kb)
    await OrderState.waiting_for_product.set()


@dp.callback_query_handler(lambda c: c.data.startswith("order:"), state=OrderState.waiting_for_product)
async def choose_quantity(call: types.CallbackQuery, state: FSMContext):
    if await check_banned(call.from_user.id):
        await call.answer("Вы заблокированы", show_alert=True)
        return

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
    if await check_banned(call.from_user.id):
        await call.answer("Вы заблокированы", show_alert=True)
        return

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
    if await check_banned(call.from_user.id):
        await call.answer("Вы заблокированы", show_alert=True)
        return

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
    if await check_banned(call.from_user.id):
        await call.answer("Вы заблокированы", show_alert=True)
        return

    await call.message.answer("Укажите город и район для доставки:")
    await OrderState.waiting_for_comment.set()
    await call.answer()


@dp.message_handler(state=OrderState.waiting_for_comment)
async def process_comment(message: types.Message, state: FSMContext):
    if await check_banned(message.from_user.id):
        return

    comment = message.text
    data = await state.get_data()
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else f"ID:{user_id}"

    # Save order
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
        order_text = f"""🛒 Новый заказ от {username} ({user_id}):
Товар: {data['product']} {data['quantity']} г
Качество: {"улучшенное" if data['quality'] else "стандартное"}
Цена: {data['price']}₽
Комментарий: {comment}"""

        await bot.send_message(ADMIN_ID, order_text)

    await message.answer("✅ Заказ оформлен! С вами свяжутся для уточнения деталей.", reply_markup=main_kb)
    await state.finish()


@dp.callback_query_handler(lambda c: c.data == "restart_order", state="*")
async def restart_order(call: types.CallbackQuery, state: FSMContext):
    if await check_banned(call.from_user.id):
        await call.answer("Вы заблокированы", show_alert=True)
        return

    await state.finish()
    await start_order(call.message)
    await call.answer()


@dp.message_handler(lambda m: m.text == "📩 Связаться с админом", state="*")
async def contact_admin(message: types.Message):
    if await check_banned(message.from_user.id):
        return

    current_state = await dp.current_state().get_state()
    if current_state in [RulesState.waiting_for_accept.state]:
        await message.answer("Сначала примите правила использования бота", reply_markup=rules_kb)
        return

    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else f"ID:{user_id}"

    if message.from_user.username:
        username_to_id[f"@{message.from_user.username}"] = user_id

    user_contacting_admin[user_id] = username
    awaiting_admin_reply.add(user_id)

    await message.answer("Напишите ваше сообщение администратору:", reply_markup=back_kb)
    log_message(user_id, "Запрос связи с админом")


@dp.message_handler(content_types=types.ContentTypes.ANY, state="*")
async def handle_messages(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        return

    if await check_banned(message.from_user.id):
        return

    current_state = await dp.current_state().get_state()
    if current_state in [RulesState.waiting_for_accept.state]:
        await message.answer("Сначала примите правила использования бота", reply_markup=rules_kb)
        return

    if message.from_user.id in awaiting_admin_reply:
        user_id = message.from_user.id
        username = f"@{message.from_user.username}" if message.from_user.username else f"ID:{user_id}"

        if user_id not in message_ids:
            message_ids[user_id] = []
        message_ids[user_id].append(message.message_id)

        if message.photo:
            photo = message.photo[-1]
            photo_name = await save_photo(photo, user_id)

            caption = f"📸 Фото от {username} ({user_id})"
            if message.caption:
                caption += f"\n\n{message.caption}"

            sent_msg = await bot.send_photo(
                ADMIN_ID,
                photo.file_id,
                caption=caption
            )
            log_message(user_id, photo_name, is_photo=True)
            if message.caption:
                log_message(user_id, message.caption)
        elif message.text:
            sent_msg = await bot.send_message(
                ADMIN_ID,
                f"📩 Сообщение от {username} ({user_id}):\n{message.text}"
            )
            log_message(user_id, message.text)
        else:
            await message.answer("❌ Поддерживаются только текст и фото")
            return

        update_unanswered_clients(user_id)

        sent_notification = await message.answer("✅ Сообщение отправлено администратору. Ожидайте ответа.")
        if user_id not in message_ids:
            message_ids[user_id] = []
        message_ids[user_id].append(sent_notification.message_id)

        awaiting_admin_reply.discard(user_id)
    else:
        await message.answer("Используйте кнопки меню для навигации.", reply_markup=main_kb)


if __name__ == '__main__':
    print("🚀 Бот запускается...")
    # Load existing logs
    for filename in os.listdir('chat_logs'):
        if filename.startswith('user_') and filename.endswith('.txt'):
            user_id = int(filename[5:-4])
            chat_logs[user_id] = load_chat_logs(user_id)

    executor.start_polling(dp, skip_updates=True)