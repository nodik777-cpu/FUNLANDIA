import os
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, CallbackQueryHandler, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")

ADMIN_PHONE = "+998 93 381 00 55"
CALL_CENTER = "+998 555 127 337"
ADDRESS = "Ташкент, ул. Тимур Малика, 3"
INSTAGRAM = "https://www.instagram.com/funlandiauz/"
TELEGRAM = "https://t.me/Funlandia_Tashkent"

def menu(lang="ru"):
    if lang == "uz":
        return ReplyKeyboardMarkup([
            ["🎟️ Narxlar", "🎂 Tug‘ilgan kun"],
            ["🎠 Ko‘ngilochar", "📍 Manzil"],
            ["🎉 Tug‘ilgan kunni bron qilish"],
            ["🕐 Ish vaqti", "📞 Kontakt"],
        ["👨‍💼 Kotib"],
            ["📸 Instagram", "📱 Telegram"],
            ["🇷🇺 Русский"],
        ], resize_keyboard=True)
    return ReplyKeyboardMarkup([
        ["🎟️ Цены", "🎂 День рождения"],
        ["🎠 Развлечения", "📍 Адрес"],
            ["🎉 Забронировать день рождения"],
        ["🕐 Время работы", "📞 Контакт"],
        ["👨‍💼 Секретарь"],
        ["📸 Instagram", "📱 Telegram"],
        ["🇺🇿 O‘zbekcha"],
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["lang"] = "ru"
    await update.message.reply_text(
        "🎉 ДОБРО ПОЖАЛОВАТЬ В FUNLANDIA! 🎉\n\n"
        "Место, где дети играют, веселятся и получают яркие эмоции, "
        "а родители отдыхают! ❤️\n\n"
        "🛝 Лабиринты • 🤸 Батуты • 🎢 Горки • 🎯 Пневмопушки • 🧗 Тарзанка\n\n"
        "Выберите интересующий раздел ниже 👇",
        reply_markup=menu("ru")
    )

async def uz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["lang"] = "uz"
    await update.message.reply_text(
        "🎉 FUNLANDIA'GA XUSH KELIBSIZ! 🎉\n\n"
        "Bu yerda bolalar o‘ynaydi, quvonadi va yorqin taassurotlar oladi, "
        "ota-onalar esa maroqli dam oladi! ❤️\n\n"
        "🛝 Labirintlar • 🤸 Batutlar • 🎢 Tepaliklar • 🎯 Pnevmatik to‘plar • 🧗 Tarzanka\n\n"
        "Kerakli bo‘limni tanlang 👇",
        reply_markup=menu("uz")
    )

async def prices(update: Update, lang):
    if lang == "uz":
        text = (
            "🎟️ FUNLANDIA NARXLARI\n\n"
            "🛝 BOLALAR ZONASI\n"
            "🏰 Labirintlar\n🎪 Puflanadigan batutlar\n🎢 Tepaliklar\n🎯 Pnevmatik to‘plar\n\n"
            "💰 1 soat — 80 000 so‘m\n"
            "💰 2 soat — 90 000 so‘m\n"
            "♾️ Cheksiz — 100 000 so‘m\n\n"
            "👧👦 1 yoshdan 16 yoshgacha bo‘lgan bolalar uchun kirish pullik.\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "🤸 BATUT ZONASI\n"
            "🤸 Professional batutlar\n🧗 Tarzanka\n🛝 17 metrlik tepalik\n\n"
            "💰 1 soat — 80 000 so‘m\n💰 2 soat — 90 000 so‘m\n♾️ Cheksiz — 100 000 so‘m\n\n"
            "⚠️ Batut zonasiga 7 yoshdan boshlab bolalar qo‘yiladi va ular ota-ona yoki katta yoshli hamroh nazoratida bo‘lishi kerak.\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "🎉 IKKALA ZONA — KO‘PROQ QUVONCH!\n"
            "🔥 2 zona — 120 000 so‘m\n"
            "♾️ Ikkala zonaga cheksiz kirish!\n\n"
            "🎊 O‘YNA • KUL • FUNLANDIA'DA YORQIN TAASSUROTLAR OL!"
        )
    else:
        text = (
            "🎟️ ЦЕНЫ FUNLANDIA\n\n"
            "🛝 ДЕТСКАЯ ЗОНА\n"
            "🏰 Лабиринты\n🎪 Надувные батуты\n🎢 Горки\n🎯 Пневмопушки\n\n"
            "💰 1 час — 80 000 сум\n"
            "💰 2 часа — 90 000 сум\n"
            "♾️ Безлимит — 100 000 сум\n\n"
            "👧👦 Детям от 1 года до 16 лет — вход платный.\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "🤸 БАТУТНАЯ ЗОНА\n"
            "🤸 Профессиональные батуты\n🧗 Тарзанка\n🛝 17-метровая горка\n\n"
            "💰 1 час — 80 000 сум\n💰 2 часа — 90 000 сум\n♾️ Безлимит — 100 000 сум\n\n"
            "⚠️ На батутную зону допускаются дети от 7 лет и только под присмотром родителей или сопровождающего взрослого.\n\n"
            "━━━━━━━━━━━━━━\n\n"
            "🎉 ДВЕ ЗОНЫ — БОЛЬШЕ ВЕСЕЛЬЯ!\n"
            "🔥 Две зоны — 120 000 сум\n♾️ Безлимитное посещение обеих зон!\n\n"
            "🎊 ИГРАЙ • ВЕСЕЛИСЬ • ПОЛУЧАЙ ЭМОЦИИ В FUNLANDIA!"
        )
    await update.message.reply_text(text, reply_markup=menu(lang))

async def hours(update: Update, lang):
    text = (
        "🕐 ВРЕМЯ РАБОТЫ FUNLANDIA\n\n"
        "🗓 Каждый день: 10:00–22:00\n\n"
        "🧹 Каждый понедельник — санитарный день до 14:00.\n"
        "🎉 Ждём вас с 14:00 до 22:00!"
        if lang == "ru" else
        "🕐 FUNLANDIA ISH VAQTI\n\n"
        "🗓 Har kuni: 10:00–22:00\n\n"
        "🧹 Har dushanba — 14:00 gacha sanitariya kuni.\n"
        "🎉 Sizni 14:00 dan 22:00 gacha kutamiz!"
    )
    await update.message.reply_text(text, reply_markup=menu(lang))

async def contacts(update: Update, lang):
    if lang == "uz":
        text = (
            "📞 FUNLANDIA ALOQA\n\n"
            "📞 Kontakt: +998933810055\n"
            "☎️ Call-markaz: +998555127337\n\n"
            "📱 Telegram: @Funlandia_Tashkent\n"
            "📸 Instagram: @funlandiauz"
        )
    else:
        text = (
            "📞 КОНТАКТЫ FUNLANDIA\n\n"
            "📞 Контакт: +998933810055\n"
            "☎️ Колл-центр: +998555127337\n\n"
            "📱 Telegram: @Funlandia_Tashkent\n"
            "📸 Instagram: @funlandiauz"
        )
    await update.message.reply_text(text, reply_markup=menu(lang))

async def direct_contact(update: Update, lang, kind):
    if kind == "call":
        text = (
            "☎️ CALL-MARKAZ\n\n📞 +998555127337"
            if lang == "uz" else
            "☎️ КОЛЛ-ЦЕНТР\n\n📞 +998555127337"
        )
    else:
        text = (
            "📞 KONTAKT\n\n📞 +998933810055"
            if lang == "uz" else
            "📞 КОНТАКТ\n\n📞 +998933810055"
        )
    await update.message.reply_text(text, reply_markup=menu(lang))

async def simple(update: Update, lang, kind):
    if kind == "address":
        text = f"📍 FUNLANDIA\n\n{ADDRESS}\n\n" + ("Sizni kutamiz! 🎉" if lang == "uz" else "Будем рады видеть вас! 🎉")
        map_button = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🗺️ Xaritada ochish" if lang == "uz" else "🗺️ Открыть на карте",
                url="https://yandex.uz/maps/-/CTT~uR0N"
            )
        ]])
        await update.message.reply_text(text, reply_markup=map_button)
        return
    elif kind == "instagram":
        text = f"📸 Instagram FUNLANDIA\n\n{INSTAGRAM}"
    else:
        text = f"📱 Telegram FUNLANDIA\n\n{TELEGRAM}"
    await update.message.reply_text(text, reply_markup=menu(lang))

async def attractions(update: Update, lang):
    text = (
        "🎠 BIZNING KO‘NGILOCHARLAR\n\n"
        "🛝 4 qavatli labirintlar\n🎪 Puflanadigan batutlar\n🤸 Professional batutlar\n"
        "🎢 Tepaliklar\n🛝 17 metrlik tepalik\n🧗 Tarzanka\n🎯 Pnevmatik to‘plar\n"
        "🧸 Kichkintoylar zonasi\n🏖️ Kinetik qum\n🎠 Karusellar"
        if lang == "uz" else
        "🎠 НАШИ РАЗВЛЕЧЕНИЯ\n\n"
        "🛝 4-этажные лабиринты\n🎪 Надувные батуты\n🤸 Профессиональные батуты\n"
        "🎢 Горки\n🛝 17-метровая горка\n🧗 Тарзанка\n🎯 Пневмопушки\n"
        "🧸 Зона для малышей\n🏖️ Кинетический песок\n🎠 Карусели"
    )
    await update.message.reply_text(text, reply_markup=menu(lang))

async def birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "ru")
    context.user_data["birthday_step"] = 1
    context.user_data["birthday"] = {}
    text = (
        "🎂 FUNLANDIA'DA TUG‘ILGAN KUN!\n\n"
        "🎁 TUG‘ILGAN KUN EGASI UCHUN AKSIYA\n\n"
        "Bayram bitta tanlangan zonada o‘tkaziladi:\n🛝 Bolalar maydonchasi\n🤸 Batut zonasi\n\n"
        "👧 5 bola — 450 000 so‘m\n👦 10 bola — 900 000 so‘m\n\n"
        "🍽️ STOL BUYURTMA QILISH\n🪑 3 soatga stol — 200 000 so‘m\n"
        "➕ Qo‘shimcha vaqt — har bir soat uchun 50 000 so‘m\n\n"
        "🪑 O‘TIRISH ZONASINI TANLASH\n1️⃣ Zona 1\n2️⃣ Zona 2\n3️⃣ Zona 3\n\n"
        "💰 Bronni tasdiqlash uchun kamida 100 000 so‘m avans kerak.\n\n"
         "Ariza qoldirish uchun tug‘ilgan kun egasining ismini yozing:"
        if lang == "uz" else
        "🎂 ДЕНЬ РОЖДЕНИЯ В FUNLANDIA!\n\n"
        "🎁 АКЦИЯ ДЛЯ ИМЕНИННИКА\n\n"
        "Празднование проходит в одной выбранной зоне:\n🛝 Детская площадка\n🤸 Батутная зона\n\n"
        "👧 5 детей — 450 000 сум\n👦 10 детей — 900 000 сум\n\n"
        "🍽️ ЗАКАЗ СТОЛА\n🪑 Стол на 3 часа — 200 000 сум\n"
        "➕ Дополнительное время — 50 000 сум за каждый час\n\n"
        "🪑 ВЫБОР ЗОНЫ ПОСАДКИ\n1️⃣ Зона 1\n2️⃣ Зона 2\n3️⃣ Зона 3\n\n"
        "💰 Для подтверждения бронирования необходим аванс — минимум 100 000 сум.\n\n"
         "Чтобы оставить заявку, напишите имя именинника:"
    )
    await update.message.reply_text(text, reply_markup=menu(lang))

async def birthday_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "ru")
    step = context.user_data["birthday_step"]
    value = update.message.text.strip()
    data = context.user_data["birthday"]
    prompts = (
        [
            ("name", "📅 Bayram qaysi sanada bo‘ladi?"),
            ("date", "👧👦 Nechta bola bo‘ladi?"),
            ("children", "🕐 Qaysi vaqt sizga qulay?"),
            ("time", "📞 Bog‘lanish uchun telefon raqamingizni yozing:"),
            ("phone", "🪑 O‘tirish zonasini tanlang: 1-zona, 2-zona yoki 3-zona."),
        ] if lang == "uz" else [
            ("name", "📅 На какую дату планируете праздник?"),
            ("date", "👧👦 Сколько будет детей?"),
            ("children", "🕐 Какое время вас интересует?"),
            ("time", "📞 Оставьте номер телефона для связи."),
            ("phone", "🪑 Выберите зону посадки: Зона 1, Зона 2 или Зона 3."),
        ]
    )
    key, prompt = prompts[step - 1]
    data[key] = value
    if step < 5:
        context.user_data["birthday_step"] = step + 1
        await update.message.reply_text(prompt)
    else:
        context.user_data["birthday_step"] = 6
        await update.message.reply_text(prompt)

async def finish_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "ru")
    data = context.user_data["birthday"]
    data["seat_zone"] = update.message.text.strip()
    username = update.effective_user.username or "нет username"
    msg = (
        "🎂 НОВАЯ ЗАЯВКА FUNLANDIA\n\n"
        f"Именинник: {data['name']}\nДата: {data['date']}\nДетей: {data['children']}\n"
        f"Время: {data['time']}\nТелефон: {data['phone']}\nЗона посадки: {data['seat_zone']}\nTelegram: @{username}"
    )
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg)
        except Exception:
            pass
    context.user_data.clear()
    await update.message.reply_text(
        "✅ Arizangiz qabul qilindi!\nAdministrator FUNLANDIA siz bilan bog‘lanadi."
        if lang == "uz" else
        "✅ Заявка принята!\n\n💰 Для подтверждения бронирования необходим аванс — минимум 100 000 сум.\nАдминистратор FUNLANDIA свяжется с вами.",
        reply_markup=menu(lang)
    )


SECRETARY_REPLY_TO = {}

async def secretary_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "ru")
    context.user_data["secretary_mode"] = True
    await update.message.reply_text(
        "👨‍💼 СЕКРЕТАРЬ FUNLANDIA\n\n"
        "Напишите ваш вопрос или сообщение. Я передам его администратору.\n"
        "После ответа администратора вы получите сообщение здесь.\n\n"
        "Для выхода нажмите /stop."
        if lang == "ru" else
        "👨‍💼 FUNLANDIA KOTIBI\n\n"
        "Savolingiz yoki xabaringizni yozing. Men uni administratorga yuboraman.\n"
        "Administrator javobi shu yerga keladi.\n\n"
        "Chiqish uchun /stop ni bosing.",
        reply_markup=menu(lang)
    )

async def secretary_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("secretary_mode", None)
    lang = context.user_data.get("lang", "ru")
    await update.message.reply_text(
        "✅ Режим секретаря выключен."
        if lang == "ru" else "✅ Kotib rejimi o‘chirildi.",
        reply_markup=menu(lang)
    )

async def secretary_client_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("secretary_mode"):
        return False

    user = update.effective_user
    username = f"@{user.username}" if user.username else "нет username"
    name = user.full_name or "Без имени"
    text = update.message.text or ""

    admin_text = (
        "👨‍💼 НОВОЕ СООБЩЕНИЕ ОТ КЛИЕНТА\n\n"
        f"👤 {name}\n"
        f"📱 {username}\n"
        f"🆔 ID: {user.id}\n\n"
        f"💬 {text}"
    )

    if ADMIN_CHAT_ID:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "↩️ Ответить клиенту",
                    callback_data=f"secretary_reply:{user.id}"
                )
            ]])
        )

    await update.message.reply_text(
        "✅ Сообщение отправлено администратору. Ожидайте ответа."
        if context.user_data.get("lang", "ru") == "ru"
        else "✅ Xabaringiz administratorga yuborildi. Javobni kuting.",
        reply_markup=menu(context.user_data.get("lang", "ru"))
    )
    return True

async def secretary_reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if str(query.from_user.id) != str(ADMIN_CHAT_ID):
        return

    user_id = int(query.data.split(":", 1)[1])
    SECRETARY_REPLY_TO[query.from_user.id] = user_id
    await query.message.reply_text("✍️ Напишите ответ клиенту одним сообщением.")

async def secretary_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID):
        return False

    user_id = SECRETARY_REPLY_TO.get(update.effective_user.id)
    if not user_id:
        return False

    text = update.message.text or ""
    await context.bot.send_message(
        chat_id=user_id,
        text=f"👨‍💼 Ответ FUNLANDIA:\n\n{text}"
    )
    SECRETARY_REPLY_TO.pop(update.effective_user.id, None)
    await update.message.reply_text("✅ Ответ отправлен клиенту.")
    return True

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if text in ("👨‍💼 Секретарь", "👨‍💼 Kotib"):
        return await secretary_start(update, context)
    if text == "/stop":
        return await secretary_stop(update, context)
    if context.user_data.get("secretary_mode"):
        if await secretary_client_message(update, context):
            return
    if str(update.effective_user.id) == str(ADMIN_CHAT_ID):
        if await secretary_admin_reply(update, context):
            return


    text = (update.message.text or "").strip()
    lang = context.user_data.get("lang", "ru")

    if text in ("🇺🇿 O‘zbekcha", "UZ O‘zbekcha"):
        return await uz_start(update, context)
    if text == "🇷🇺 Русский":
        return await start(update, context)

    # Contact buttons: one contact and one call-center button.
    if text in ("📞 Контакт", "📞 Kontakt", "📞 Контакты", "📞 Aloqa"):
        return await contacts(update, lang)
    if text in ("☎️ Колл-центр", "☎️ Call-markaz"):
        return await direct_contact(update, lang, "call")

    if text in ("🎟️ Цены", "🎟️ Narxlar"):
        return await prices(update, lang)
    if text in ("🎂 День рождения", "🎂 Tug‘ilgan kun", "🎉 Забронировать день рождения", "🎉 Tug‘ilgan kunni bron qilish"):
        return await birthday(update, context)
    if text in ("🎠 Развлечения", "🎠 Ko‘ngilochar"):
        return await attractions(update, lang)
    if text in ("📍 Адрес", "📍 Manzil"):
        return await simple(update, lang, "address")
    if text in ("🕐 Время работы", "🕐 Ish vaqti"):
        return await hours(update, lang)
    if text == "📸 Instagram":
        return await simple(update, lang, "instagram")
    if text == "📱 Telegram":
        return await simple(update, lang, "telegram")

    if context.user_data.get("birthday_step") == 6:
        return await finish_birthday(update, context)
    if context.user_data.get("birthday_step"):
        return await birthday_form(update, context)

    await update.message.reply_text(
        "😊 Menyudan kerakli bo‘limni tanlang." if lang == "uz" else
        "😊 Пожалуйста, выберите нужный раздел.",
        reply_markup=menu(lang)
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(secretary_reply_button, pattern=r"^secretary_reply:\d+$"))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))
    app.run_polling()

if __name__ == "__main__":
    main()
