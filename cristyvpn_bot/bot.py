import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

from db import DB

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL = os.getenv("CHANNEL", "@CristyVPN")
SUPPORT = os.getenv("SUPPORT", "@fymce")

DEFAULT_ADMINS = {7894051808, 8477431361}
env_admins = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
ADMIN_IDS = DEFAULT_ADMINS | env_admins

logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
db = DB("cristyvpn.sqlite3")

MSK = timezone(timedelta(hours=3))


def fmt(dt):
    return dt.strftime("%d.%m.%Y, %H:%M (МСК)")


def fmt_date(dt):
    return dt.strftime("%d.%m.%Y")


async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False


def subscribe_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 ПОДПИСАТЬСЯ 💵", url=f"https://t.me/{CHANNEL.lstrip('@')}")],
        [InlineKeyboardButton(text="ПРОВЕРИТЬ ПОДПИСКУ ✅", callback_data="check_sub")]
    ])


def main_kb(user_id: int = 0):
    buttons = [
        [InlineKeyboardButton(text="💰 Забрать подписку", callback_data="trial")],
        [InlineKeyboardButton(text="💳 Купить/продлить", callback_data="plans")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="👥 Пригласить друга", callback_data="ref")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo")],
        [InlineKeyboardButton(text="🆘 Поддержка", url=f"https://t.me/{SUPPORT.lstrip('@')}")],
    ]
    if user_id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton(text="🛠 Админка", callback_data="adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu")]
    ])


def admin_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В админку", callback_data="adm:home")]
    ])


def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="adm:users")],
        [InlineKeyboardButton(text="🔎 Найти пользователя", callback_data="adm:search")],
        [InlineKeyboardButton(text="📈 Покупки", callback_data="adm:purchases")],
        [InlineKeyboardButton(text="📣 Рассылка", callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="ℹ️ Информация", callback_data="adm:info")],
        [InlineKeyboardButton(text="➕ Пробные ссылки", callback_data="adm:add:trial")],
        [InlineKeyboardButton(text="➕ Ссылки 30 дней", callback_data="adm:add:30")],
        [InlineKeyboardButton(text="➕ Ссылки 90 дней", callback_data="adm:add:90")],
        [InlineKeyboardButton(text="💸 Выводы", callback_data="adm:withdraws")],
        [InlineKeyboardButton(text="🎁 Промокоды", callback_data="adm:promo")],
    ])


def menu_text(user, active, exp):
    display_name = user.username or user.first_name or "Пользователь"
    return (
        "🦈 Cristy | Главное меню\n\n"
        f"👤 {display_name}\n"
        f"ID: {user.id}\n\n"
        f"{'🟢 Подписка активна' if active else '🔴 Подписка не активна'}\n\n"
        f"⏳ Истекает: {exp}\n\n"
        "▸ Выберите действие ниже:"
    )


def get_user_view(user):
    u = db.user(user.id, user.username or "")
    active = bool(u["expires_at"]) and datetime.fromisoformat(u["expires_at"]) > datetime.now(timezone.utc)
    if u["expires_at"]:
        exp = fmt(datetime.fromisoformat(u["expires_at"]).astimezone(MSK))
    else:
        exp = "—"
    return u, active, exp


async def send_menu_from_user(user, chat_id: int):
    u, active, exp = get_user_view(user)
    await bot.send_message(chat_id, menu_text(user, active, exp), reply_markup=main_kb(user.id))


async def edit_menu_from_user(c: CallbackQuery):
    u, active, exp = get_user_view(c.from_user)
    try:
        await c.message.edit_text(menu_text(c.from_user, active, exp), reply_markup=main_kb(c.from_user.id))
    except Exception:
        await bot.send_message(c.from_user.id, menu_text(c.from_user, active, exp), reply_markup=main_kb(c.from_user.id))


# ----------------- START -----------------

@dp.message(CommandStart())
async def start(m: Message):
    args = m.text.split(maxsplit=1)
    ref = int(args[1]) if len(args) == 2 and args[1].isdigit() else None
    db.user(m.from_user.id, m.from_user.username or "", ref)
    if not await is_subscribed(m.from_user.id):
        await m.answer(
            "Для использования сервиса необходимо\nподписаться на канал:\n\n"
            "📢 @CristyVPN\n\n"
            "Подпишитесь и нажмите кнопку ниже 👇",
            reply_markup=subscribe_kb()
        )
        return
    await send_menu_from_user(m.from_user, m.chat.id)


# ----------------- ПОДПИСКА -----------------

@dp.callback_query(F.data == "check_sub")
async def check_sub(c: CallbackQuery):
    if not await is_subscribed(c.from_user.id):
        await c.answer("Сначала подпишитесь на канал.", show_alert=True)
        return
    trial = db.activate_trial(c.from_user.id)
    if trial:
        exp = fmt(datetime.fromisoformat(trial).astimezone(MSK))
        await c.message.edit_text(
            "✅ Подписка подтверждена\n\n"
            "🎁 Пробный период активирован!\n\n"
            "Вы получили 3 дня бесплатного доступа.\n\n"
            f"📅 Действует до: {exp}\n\n"
            "Теперь добавим ваше устройство 👇",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💰 Забрать подписку", callback_data="trial")],
                [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu")]
            ])
        )
    else:
        await c.message.edit_text(
            "✅ Подписка подтверждена\n\nПробный период уже использован.",
            reply_markup=back_kb()
        )


# ----------------- МЕНЮ -----------------

@dp.callback_query(F.data == "menu")
async def menu(c: CallbackQuery):
    await edit_menu_from_user(c)


# ----------------- ПРОБНАЯ ПОДПИСКА -----------------

@dp.callback_query(F.data == "trial")
async def trial(c: CallbackQuery):
    link = db.take_link("trial", c.from_user.id)
    if link:
        db.add_device(c.from_user.id, link)
        text = (
            "✅ Устройство добавлено\n\n"
            "💻 Windows/Android/apple • Hiddify / V2RayTun / happ\n\n"
            "🔗 Ссылка для подключения:\n\n"
            f"{link}\n\n"
            "Скопируйте ссылку и вставьте в приложение\n\n"
            "📲 Как подключить:\n"
            "1. Скопируйте ссылку\n"
            "2. Приложение → Добавить → Вставить\n"
            "3. Выберите сервер"
        )
    else:
        text = "⏳ Ссылки закончились. Ожидайте, скоро будет выдана."
    await c.message.edit_text(text, reply_markup=back_kb())


# ----------------- ТАРИФЫ -----------------

@dp.callback_query(F.data == "plans")
async def plans(c: CallbackQuery):
    await c.message.edit_text(
        "⚡️ Покупка подписки CristyVPN\n\n"
        "Что вы получаете:\n\n"
        "▸ 🚀 Безлимитный трафик\n"
        "▸ 🌐 8 стран на выбор\n"
        "▸ 🔒 Защищённое шифрование Reality\n"
        "▸ ⚙️ Работает на всех устройствах\n"
        "▸ 🎮 YouTube, TikTok, Telegram — без лагов\n\n"
        "↓ Выберите срок подписки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="30 дней — 199₽", callback_data="buy:30")],
            [InlineKeyboardButton(text="90 дней — 500₽", callback_data="buy:90")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")]
        ])
    )


@dp.callback_query(F.data.startswith("buy:"))
async def buy(c: CallbackQuery):
    days = int(c.data.split(":")[1])
    rub = 199 if days == 30 else 500
    stars = 150 if days == 30 else 400
    await c.message.edit_text(
        "💳 Оформление подписки\n\n"
        f"📦 Тариф: {days} дней\n"
        f"💰 К оплате: {rub}₽\n\n"
        "▸ Выберите способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏦 СБП", callback_data=f"pay:sbp:{days}")],
            [InlineKeyboardButton(text=f"⭐ Stars — {stars}", callback_data=f"pay:stars:{days}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="plans")]
        ])
    )


@dp.callback_query(F.data.startswith("pay:"))
async def pay(c: CallbackQuery):
    _, method, days_s = c.data.split(":")
    days = int(days_s)
    rub = 199 if days == 30 else 500
    stars = 150 if days == 30 else 400
    order_id = db.create_order(c.from_user.id, days, method, rub, stars)
    if method == "stars":
        text = (
            "⭐ Оплата Stars\n\n"
            f"Тариф: {days} дней\n"
            f"Сумма: {stars} Stars\n\n"
            f"Напишите {SUPPORT} и отправьте сообщение:\n"
            f"«ВПН {days} дней, заказ #{order_id}»\n\n"
            "После подтверждения администратор активирует подписку."
        )
    else:
        text = (
            "🏦 Оплата через СБП\n\n"
            f"Тариф: {days} дней\n"
            f"К оплате: {rub}₽\n\n"
            "Реквизиты для СБП добавляются администратором в настройках бота.\n"
            f"После оплаты отправьте чек в {SUPPORT} и укажите заказ #{order_id}."
        )
    await c.message.edit_text(text, reply_markup=back_kb())
    for admin in ADMIN_IDS:
        try:
            await bot.send_message(
                admin,
                f"🛒 Новый заказ #{order_id}\nПользователь: {c.from_user.id}\n"
                f"Тариф: {days} дней\nМетод: {method}"
            )
        except Exception:
            pass


# ----------------- ПРОФИЛЬ -----------------

@dp.callback_query(F.data == "profile")
async def profile(c: CallbackQuery):
    user = c.from_user
    u = db.user(user.id, user.username or "")
    active = bool(u["expires_at"]) and datetime.fromisoformat(u["expires_at"]) > datetime.now(timezone.utc)
    exp = fmt(datetime.fromisoformat(u["expires_at"]).astimezone(MSK)) if u["expires_at"] else "—"
    reg = datetime.fromisoformat(u["created_at"]).astimezone(MSK) if u["created_at"] else None
    reg_s = fmt_date(reg) if reg else "—"
    bal = float(u["balance"] or 0)
    devices = db.device_count(u["id"])
    display_name = user.username or user.first_name or "Пользователь"

    text = (
        "👤 Ваш профиль\n\n"
        f"🆔 ID: {user.id}\n"
        f"📛 Имя: {display_name}\n"
        f"📅 Регистрация: {reg_s}\n\n"
        f"{'🟢 Подписка активна' if active else '🔴 Подписка не активна'}\n"
        f"⏳ Истекает: {exp}\n"
        f"📱 Устройств: {devices}/3\n\n"
        f"💰 Баланс: {bal:.2f}₽"
    )
    await c.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu")]
        ])
    )


# ----------------- РЕФЕРАЛЫ + ВЫВОД -----------------

@dp.callback_query(F.data == "ref")
async def ref(c: CallbackQuery):
    bal = db.balance(c.from_user.id)
    link = f"https://t.me/{(await bot.me()).username}?start={c.from_user.id}"
    await c.message.edit_text(
        "👥 Пригласить друга\n\n"
        "Получайте 10% от покупок приглашённых друзей.\n"
        "Баланс можно потратить на подписку или вывести от 1000₽.\n\n"
        f"🔗 Ваша ссылка:\n{link}\n\n"
        f"💰 Баланс: {bal:.2f}₽",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu")]
        ])
    )


@dp.callback_query(F.data == "withdraw")
async def withdraw(c: CallbackQuery):
    bal = db.balance(c.from_user.id)
    if bal < 1000:
        await c.answer(f"❌ Минимум для вывода — 1000₽.\nВаш баланс: {bal:.2f}₽", show_alert=True)
        return
    db.set_state(c.from_user.id, "withdraw_card")
    await c.message.edit_text(
        "💸 Вывод средств\n\n"
        f"💰 Ваш баланс: {bal:.2f}₽\n"
        "Минимум для вывода: 1000₽\n\n"
        "Отправьте номер карты (или реквизиты) одним сообщением:",
        reply_markup=back_kb()
    )


# ----------------- ПРОМОКОД -----------------

@dp.callback_query(F.data == "promo")
async def promo(c: CallbackQuery):
    await c.message.edit_text(
        "🎁 Промокод\n\nОтправьте промокод следующим сообщением.",
        reply_markup=back_kb()
    )
    db.set_state(c.from_user.id, "promo")


# ----------------- КОМАНДА /admin -----------------

@dp.message(Command("admin"))
async def admin(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer(f"Нет доступа. Ваш ID: {m.from_user.id}")
        return
    await m.answer("🛠 Админка CristyVPN", reply_markup=admin_kb())


# ----------------- АДМИН CALLBACK -----------------

async def admin_only(c: CallbackQuery) -> bool:
    if c.from_user.id not in ADMIN_IDS:
        await c.answer("Нет доступа", show_alert=True)
        return False
    return True


@dp.callback_query(F.data.startswith("adm:"))
async def admin_cb(c: CallbackQuery):
    if not await admin_only(c):
        return
    parts = c.data.split(":")
    action = parts[1]

    if action == "add":
        kind = parts[2]
        db.set_state(c.from_user.id, f"addlink:{kind}")
        await c.message.edit_text(
            f"➕ Добавление ссылок: {kind}\n\n"
            "Отправьте ссылку подключения. Можно отправлять несколько сообщений.",
            reply_markup=admin_back_kb()
        )
    elif action == "stats":
        await c.message.edit_text(db.stats_detailed(), reply_markup=admin_back_kb())
    elif action == "users":
        await c.message.edit_text(db.users_page(), reply_markup=admin_back_kb())
    elif action == "search":
        db.set_state(c.from_user.id, "search_user")
        await c.message.edit_text(
            "🔎 Поиск пользователя\n\n"
            "Отправьте Telegram ID или @username.",
            reply_markup=admin_back_kb()
        )
    elif action == "purchases":
        await c.message.edit_text(db.purchases_stats(), reply_markup=admin_back_kb())
    elif action == "broadcast":
        db.set_state(c.from_user.id, "broadcast")
        await c.message.edit_text(
            "📣 Рассылка\n\nОтправьте текст сообщения, которое нужно отправить всем пользователям.",
            reply_markup=admin_back_kb()
        )
    elif action == "info":
        await c.message.edit_text(
            "ℹ️ Информация\n\n"
            "CristyVPN — управление подписками, ссылками, покупками и рефералами.\n\n"
            "Проверка подписки выполняется через канал @CristyVPN.\n"
            "Пользователю можно выдать до 3 устройств.",
            reply_markup=admin_back_kb()
        )
    elif action == "withdraws":
        await c.message.edit_text(db.withdraws_text(), reply_markup=admin_back_kb())
    elif action == "promo":
        db.set_state(c.from_user.id, "newpromo")
        await c.message.edit_text(
            "🎁 Создание промокода\n\n"
            "Формат:\nКОД сумма количество_использований\n\n"
            "Пример: 67 100 5",
            reply_markup=admin_back_kb()
        )
    elif action == "home":
        await c.message.edit_text("🛠 Админка CristyVPN", reply_markup=admin_kb())


# ----------------- ОБЩИЙ ОБРАБОТЧИК СООБЩЕНИЙ -----------------

@dp.message()
async def all_messages(m: Message):
    if m.from_user.id in ADMIN_IDS:
        state = db.get_state(m.from_user.id)
        if state and state.startswith("addlink:"):
            kind = state.split(":")[1]
            db.add_link(kind, m.text.strip())
            await m.answer(f"✅ Ссылка добавлена в очередь «{kind}».")
            return
        if state == "search_user":
            db.clear_state(m.from_user.id)
            query = m.text.strip().lstrip("@")
            result = db.find_user(query)
            await m.answer(result, reply_markup=admin_back_kb())
            return
        if state == "broadcast":
            db.clear_state(m.from_user.id)
            users = db.all_user_ids()
            sent = failed = 0
            for uid in users:
                try:
                    await bot.send_message(uid, m.text)
                    sent += 1
                except Exception:
                    failed += 1
            await m.answer(
                f"📣 Рассылка завершена.\n\n✅ Отправлено: {sent}\n❌ Не доставлено: {failed}",
                reply_markup=admin_back_kb()
            )
            return
        if state == "newpromo":
            try:
                parts = m.text.strip().split()
                if len(parts) != 3:
                    raise ValueError
                code, amount, uses = parts
                db.add_promo(code, float(amount), int(uses))
                db.clear_state(m.from_user.id)
                await m.answer("✅ Промокод создан.", reply_markup=admin_back_kb())
            except ValueError:
                await m.answer("Формат: КОД сумма количество_использований\nПример: 67 100 5")
            return
        return

    state = db.get_state(m.from_user.id)

    if state == "promo":
        db.clear_state(m.from_user.id)
        result = db.use_promo(m.from_user.id, m.text.strip())
        await m.answer(result, reply_markup=back_kb())
        return

    if state == "withdraw_card":
        db.clear_state(m.from_user.id)
        card = m.text.strip()
        bal = db.balance(m.from_user.id)
        if bal < 1000:
            await m.answer(f"❌ Минимум для вывода — 1000₽.\nВаш баланс: {bal:.2f}₽", reply_markup=back_kb())
            return
        await m.answer(
            "✅ Заявка на вывод создана!\n\n"
            f"💰 Сумма: {bal:.2f}₽\n"
            f"💳 Реквизиты: {card}\n\n"
            "Ожидайте обработки администратором.",
            reply_markup=back_kb()
        )
        for admin in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin,
                    f"💸 Новая заявка на вывод\n\n"
                    f"👤 ID: {m.from_user.id}\n"
                    f"💰 Сумма: {bal:.2f}₽\n"
                    f"💳 Реквизиты: {card}"
                )
            except Exception:
                pass
        return


# ----------------- ЗАПУСК -----------------

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Укажите BOT_TOKEN в .env")
    print("ADMIN_IDS =", ADMIN_IDS)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())