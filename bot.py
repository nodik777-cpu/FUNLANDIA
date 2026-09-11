import os
import json
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, BusinessConnectionHandler, TypeHandler, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")

ADMIN_PHONE = "+998 93 381 00 55"
CALL_CENTER = "+998 555 127 337"
ADDRESS = "Ташкент, ул. Тимур Малика, 3"
INSTAGRAM = "https://www.instagram.com/funlandiauz/"
TELEGRAM = "https://t.me/Funlandia_Tashkent"

# Photos are saved as Telegram file_id values in a persistent Railway Volume.
# Railway Volume should be mounted at /app/data.
PHOTO_DIR = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "/app/data")
os.makedirs(PHOTO_DIR, exist_ok=True)
PHOTO_FILE = os.path.join(PHOTO_DIR, "photos.json")

PHOTO_KEYS = {
    "promotion": "🎁 Акция месяца",
    "entrance": "🚪 Вход в FUNLANDIA",
    "cashier": "🎟️ Касса",
    "trampoline": "🤸 Батуты",
    "playground": "🛝 Детская площадка",
    "carousel": "🎠 Карусели",
    "arcade": "🎮 Игровые автоматы",
    "autodrome": "🏎️ Автодром",
    "ninja": "🪢 Kanat yo‘li",
    "birthday1": "🎈 Зона №1",
    "birthday2": "🎈 Зона №2",
    "birthday3": "🎈 Зона №3",
}

PHOTO_TITLES_UZ = {
    "entrance": "🚪 FUNLANDIA kirish",
    "cashier": "🎟️ Kassa",
    "trampoline": "🤸 Batutlar",
    "playground": "🛝 Bolalar maydonchasi",
    "carousel": "🎠 Karusellar",
    "arcade": "🎮 O'yin avtomatlari",
    "autodrome": "🏎️ Avtodrom",
    "ninja": "🪢 Kanat yo‘li",
    "birthday1": "🎈 1-zona",
    "birthday2": "🎈 2-zona",
    "birthday3": "🎈 3-zona",
}

def load_photos():
    try:
        with open(PHOTO_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}

def save_photos(data):
    with open(PHOTO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def normalize_photo_list(value):
    if isinstance(value, list):
        return [str(x) for x in value if x]
    if isinstance(value, str) and value:
        return [value]
    return []

def is_admin(update: Update):
    return bool(ADMIN_CHAT_ID) and str(update.effective_chat.id) == str(ADMIN_CHAT_ID)

def menu(lang="ru"):
    if lang == "uz":
        rows = [
            ["📸 FOTO-GID", "🎟️ Narxlar"],
            ["🤖 Avto-kotib", "🎁 Aksiya oyi"],
            ["🎠 Ko‘ngilochar", "📍 Manzil"],
            ["🎉 Tug‘ilgan kunni bron qilish", "🕐 Ish vaqti"],
            ["📞 Kontakt", "📸 Instagram"],
            ["📱 Telegram", "🇷🇺 Русский"],
        ]
    else:
        rows = [
            ["📸 ФОТО-ГИД", "🎟️ Цены"],
            ["🤖 Авто-секретарь", "🎁 Акция месяца"],
            ["🎠 Развлечения", "📍 Адрес"],
            ["🎉 Забронировать день рождения", "🕐 Время работы"],
            ["📞 Контакт", "📸 Instagram"],
            ["📱 Telegram", "🇺🇿 O‘zbekcha"],
        ]
    return ReplyKeyboardMarkup(two_col(rows), resize_keyboard=True)


def funlandia_menu(lang="ru"):
    if lang == "uz":
        rows = [
            ["🚪 FUNLANDIA kirish", "🎟️ Kassa"],
            ["🤸 Batutlar", "🛝 Bolalar maydonchasi"],
            ["🎠 Karusellar", "🎮 O'yin avtomatlari"],
            ["🏎️ Avtodrom", "🪢 Kanat yo‘li"],
            ["🔙 Orqaga"],
        ]
    else:
        rows = [
            ["🚪 Вход в FUNLANDIA", "🎟️ Касса"],
            ["🤸 Батуты", "🛝 Детская площадка"],
            ["🎠 Карусели", "🎮 Игровые автоматы"],
            ["🏎️ Автодром", "🪢 Канатная дорога"],
            ["🔙 Назад"],
        ]
    return ReplyKeyboardMarkup(two_col(rows), resize_keyboard=True)


def birthday_menu(lang="ru"):
    if lang == "uz":
        rows = [
            ["🎈 Zona №1", "🎈 Zona №2"],
            ["🎈 Zona №3", "📝 Tug‘ilgan kunni bron qilish"],
            ["🔙 Orqaga"],
        ]
    else:
        rows = [
            ["🎈 Зона №1", "🎈 Зона №2"],
            ["🎈 Зона №3", "📝 Забронировать день рождения"],
            ["🔙 Назад"],
        ]
    return ReplyKeyboardMarkup(two_col(rows), resize_keyboard=True)

def two_col(rows):
    out = []
    for row in rows:
        if not isinstance(row, list):
            row = [row]
        for i in range(0, len(row), 2):
            out.append(row[i:i+2])
    return out

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["lang"] = "ru"
    await update.effective_message.reply_text(
        "🎉 ДОБРО ПОЖАЛОВАТЬ В FUNLANDIA! 🎉\n\n"
        "Место, где дети играют, веселятся и получают яркие эмоции, "
        "а родители отдыхают! ❤️\n\n"
        "🛝 Лабиринты • 🤸 Батуты • 🎢 Горки • 🎯 Пневмопушки • 🧗 Тарзанка\n\n"
        "Выберите интересующий раздел ниже 👇",
        reply_markup=menu("ru")
    )

async def uz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["lang"] = "uz"
    await update.effective_message.reply_text(
        "🎉 FUNLANDIA'GA XUSH KELIBSIZ! 🎉\n\n"
        "Bu yerda bolalar o‘ynaydi, quvonadi va yorqin taassurotlar oladi, "
        "ota-onalar esa maroqli dam oladi! ❤️\n\n"
        "🛝 Labirintlar • 🤸 Batutlar • 🎢 Tepaliklar • 🎯 Pnevmatik to‘plar • 🧗 Tarzanka\n\n"
        "Kerakli bo‘limni tanlang 👇",
        reply_markup=menu("uz")
    )

async def secretary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "ru")
    text = (
        "🤖 AVTO-KOTIB FUNLANDIA\n\n"
        "Men sizga yordam beraman:\n"
        "💰 narxlar\n"
        "🎂 tug‘ilgan kun va bron\n"
        "🕐 ish vaqti va sanitariya kuni\n"
        "📍 manzil\n"
        "📞 telefon\n"
        "📸 Instagram\n"
        "📱 Telegram\n\n"
        "Savolingizni yozing — kerakli ma’lumotni beraman."
        if lang == "uz" else
        "🤖 АВТО-СЕКРЕТАРЬ FUNLANDIA\n\n"
        "Я помогу вам узнать:\n"
        "💰 цены\n"
        "🎂 день рождения и бронирование\n"
        "🕐 график работы и санитарный день\n"
        "📍 адрес\n"
        "📞 телефон\n"
        "📸 Instagram\n"
        "📱 Telegram\n\n"
        "Напишите свой вопрос — я постараюсь сразу ответить."
    )
    await update.effective_message.reply_text(text, reply_markup=menu(lang))


async def secretary_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Friendly auto-secretary: greet first, then answer; unknown questions go to admin."""
    lang = context.user_data.get("lang", "ru")
    raw = (update.effective_message.text or "").strip()
    question = raw.lower()

    # First contact: always greet and invite the client to ask a question.
    if not context.user_data.get("secretary_greeted"):
        context.user_data["secretary_greeted"] = True

        greetings = (
            "привет", "здравствуйте", "здравствуй", "добрый день",
            "добрый вечер", "доброе утро", "салом", "салом алейкум",
            "ассалому алейкум", "алейкум ассалом", "hello", "hi",
            "salom", "assalomu alaykum"
        )

        if any(word in question for word in greetings):
            await update.effective_message.reply_text(
                "👋 Здравствуйте! Добро пожаловать в FUNLANDIA!\n\n"
                "😊 Чем могу помочь?\n\n"
                "Я могу рассказать о ценах, развлечениях, возрасте детей, "
                "дне рождения, свободных зонах, адресе и режиме работы."
            )
            return

        # Even if the first message is a question rather than a greeting,
        # introduce the secretary before answering it.
        await update.effective_message.reply_text(
            "👋 Здравствуйте! Добро пожаловать в FUNLANDIA!\n\n"
            "😊 Чем могу помочь?"
        )

    # Friendly greetings at any later point.
    greetings = (
        "привет", "здравствуйте", "здравствуй", "добрый день",
        "добрый вечер", "доброе утро", "салом", "салом алейкум",
        "ассалому алейкум", "алейкум ассалом", "hello", "hi",
        "salom", "assalomu alaykum"
    )
    if any(word in question for word in greetings):
        await update.effective_message.reply_text(
            "👋 Здравствуйте! 😊 Чем могу помочь?"
            if lang == "ru" else
            "👋 Assalomu alaykum! 😊 Sizga qanday yordam bera olaman?"
        )
        return

    price_words = ("цена", "цены", "стоимость", "сколько стоит", "сколько", "price", "narx")
    birthday_words = (
        "день рождения", "день рожд", "birthday",
        "tug‘ilgan", "tugilgan", "тугилган кун"
    )
    direct_booking_words = (
        "оформить бронь", "начать бронь", "начать бронирование",
        "оформить бронирование", "заполнить заявку",
        "bronni boshlash", "bron qilishni boshlash"
    )
    monday_words = ("понедельник", "санитар", "санитарный", "уборка", "dushanba", "sanitariya")
    hours_words = ("работаете", "работа", "открыты", "открываетесь", "закрываетесь", "время работы", "режим", "soat")
    address_words = ("адрес", "где вы", "где находитесь", "как найти", "manzil", "qayerda")
    contact_words = ("телефон", "номер", "позвонить", "инстаграм", "instagram", "телеграм", "telegram", "контакт")
    age_words = ("возраст", "лет", "до скольки", "с какого возраста", "сколько лет", "yosh", "necha yosh")

    if any(word in question for word in price_words):
        return await prices(update, lang)

    if any(word in question for word in birthday_words):
        return await birthday_gallery(update, lang)

    if any(word in question for word in direct_booking_words):
        return await birthday(update, context)

    if any(word in question for word in monday_words):
        await update.effective_message.reply_text(
            "🧼 Каждый понедельник — санитарный день до 14:00.\n"
            "С 14:00 до 22:00 FUNLANDIA работает."
        )
        return

    if any(word in question for word in hours_words):
        return await hours(update, lang)

    if any(word in question for word in address_words):
        return await simple(update, "address", lang)

    if any(word in question for word in contact_words):
        return await contacts(update, lang)

    if any(word in question for word in age_words):
        if "батут" in question or "trampoline" in question:
            await update.effective_message.reply_text(
                "🤸 Батуты: с 7 лет, под присмотром родителей/взрослого."
            )
        elif "площад" in question or "playground" in question:
            await update.effective_message.reply_text(
                "🛝 Детская площадка: до 1 года — бесплатно; от 1 до 16 лет — вход платный."
            )
        else:
            await update.effective_message.reply_text(
                "🛝 Детская площадка: до 1 года — бесплатно; от 1 до 16 лет — вход платный.\n"
                "🤸 Батуты: с 7 лет, под присмотром родителей/взрослого."
            )
        return

    # Do NOT send every first/unknown phrase straight to admin without context.
    # Ask for clarification first; only escalate when the client confirms they
    # need help with something the secretary cannot answer.
    if not context.user_data.get("secretary_clarification_asked"):
        context.user_data["secretary_clarification_asked"] = True
        await update.effective_message.reply_text(
            "😊 Конечно. Уточните, пожалуйста, что именно вас интересует?\n\n"
            "Например: цены, день рождения, развлечения, возраст, адрес или время работы."
        )
        return

    user = update.effective_user
    name = user.full_name or "Без имени"
    username = user.username or "без username"

    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    "🤖 ВОПРОС ОТ КЛИЕНТА\n\n"
                    f"👤 {name}\n"
                    f"📱 @{username}\n"
                    f"🌐 Язык: {lang}\n\n"
                    f"❓ {raw}"
                )
            )
        except Exception as exc:
            print(f"Secretary admin notification error: {exc}")

    await update.effective_message.reply_text(
        "Спасибо! Я передал ваш вопрос администратору FUNLANDIA. "
        "С вами свяжутся."
        if lang == "ru" else
        "Rahmat! Savolingizni FUNLANDIA administratoriga yubordim. "
        "Siz bilan bog‘lanishadi."
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
            "🔥 Две зоны — 120 000 сум\n"
            "♾️ Безлимитное посещение обеих зон!\n\n"
            "🎊 ИГРАЙ • ВЕСЕЛИСЬ • ПОЛУЧАЙ ЭМОЦИИ В FUNLANDIA!"
        )
    await update.effective_message.reply_text(text, reply_markup=menu(lang))

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
    await update.effective_message.reply_text(text, reply_markup=menu(lang))

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
    await update.effective_message.reply_text(text, reply_markup=menu(lang))

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
    await update.effective_message.reply_text(text, reply_markup=menu(lang))

async def simple(update: Update, lang, kind):
    if kind == "address":
        text = f"📍 FUNLANDIA\n\n{ADDRESS}\n\n" + ("Sizni kutamiz! 🎉" if lang == "uz" else "Будем рады видеть вас! 🎉")
        map_button = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🗺️ Xaritada ochish" if lang == "uz" else "🗺️ Открыть на карте",
                url="https://yandex.uz/maps/-/CTT~uR0N"
            )
        ]])
        await update.effective_message.reply_text(text, reply_markup=map_button)
        return
    if kind == "instagram":
        text = f"📸 Instagram FUNLANDIA\n\n{INSTAGRAM}"
    else:
        text = f"📱 Telegram FUNLANDIA\n\n{TELEGRAM}"
    await update.effective_message.reply_text(text, reply_markup=menu(lang))

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
    await update.effective_message.reply_text(text, reply_markup=menu(lang))

async def funlandia(update: Update, lang):
    text = "🎡 FUNLANDIA\n\nTanlang:" if lang == "uz" else "🎡 FUNLANDIA\n\nВыберите раздел:"
    await update.effective_message.reply_text(text, reply_markup=funlandia_menu(lang))

async def birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "ru")
    context.user_data["birthday_step"] = 1
    context.user_data["birthday"] = {}
    text = (
        "🎂 FUNLANDIA'DA TUG‘ILGAN KUN!\n\n"
        "🎁 TUG‘ILGAN KUN EGASI UCHUN AKSIYA\n\n"
        "Bayram bitta tanlangan zonada:\n🛝 Bolalar maydonchasi\n🤸 Batut zonasi\n\n"
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
    await update.effective_message.reply_text(text, reply_markup=menu(lang))

async def september_promo(update: Update, context: ContextTypes.DEFAULT_TYPE, lang):
    key = "promotion"
    photos = load_photos()
    file_ids = normalize_photo_list(photos.get(key))

    if file_ids:
        title = "🎁 АКЦИЯ МЕСЯЦА" if lang == "ru" else "🎁 OY AKSIYASI"
        for index, file_id in enumerate(file_ids):
            await update.effective_message.reply_photo(
                photo=file_id,
                caption=title if index == 0 else None,
                reply_markup=menu(lang) if index == len(file_ids) - 1 else None
            )
    else:
        text = (
            "🎁 АКЦИЯ МЕСЯЦА\n\n"
            "Фото акции пока не загружены."
            if lang == "ru" else
            "🎁 OY AKSIYASI\n\n"
            "Aksiya fotosuratlari hali yuklanmagan."
        )
        await update.effective_message.reply_text(text, reply_markup=menu(lang))


async def birthday_gallery(update: Update, lang):
    """Show birthday-zone photos first, then the zone/booking buttons."""
    intro = (
        "🎂 FUNLANDIA'DA TUG‘ILGAN KUN!\n\n"
        "🎈 Bayram zonalari fotosuratlari:\n"
        "🪑 1️⃣ Zona 1\n"
        "🪑 2️⃣ Zona 2\n"
        "🪑 3️⃣ Zona 3"
        if lang == "uz" else
        "🎂 ДЕНЬ РОЖДЕНИЯ В FUNLANDIA!\n\n"
        "🎈 Фотографии зон для празднования:\n"
        "🪑 1️⃣ Зона 1\n"
        "🪑 2️⃣ Зона 2\n"
        "🪑 3️⃣ Зона 3"
    )
    await update.effective_message.reply_text(intro)

    photos = load_photos()
    zone_keys = (
        ("birthday1", "🎈 Зона №1", "🎈 Zona №1"),
        ("birthday2", "🎈 Зона №2", "🎈 Zona №2"),
        ("birthday3", "🎈 Зона №3", "🎈 Zona №3"),
    )

    shown = 0
    for key, title_ru, title_uz in zone_keys:
        file_ids = normalize_photo_list(photos.get(key))
        title = title_uz if lang == "uz" else title_ru

        for index, file_id in enumerate(file_ids):
            caption = title if index == 0 else None
            await update.effective_message.reply_photo(
                photo=file_id,
                caption=caption
            )
            shown += 1

    if shown == 0:
        await update.effective_message.reply_text(
            "📸 Фото зон пока не загружены. Ниже можно выбрать зону или оформить бронь."
            if lang == "ru" else
            "📸 Zona fotosuratlari hali yuklanmagan. Quyida zonani tanlashingiz yoki bron qilishingiz mumkin."
        )
    else:
        await update.effective_message.reply_text(
            "👇 Выберите нужную зону или сразу оформите бронирование:"
            if lang == "ru" else
            "👇 Kerakli zonani tanlang yoki bronni boshlang:"
        )

    # Keep the existing working zone buttons and booking button.
    await update.effective_message.reply_text(
        "👇",
        reply_markup=birthday_menu(lang)
    )

async def send_photo_key(update: Update, context: ContextTypes.DEFAULT_TYPE, key):
    lang = context.user_data.get("lang", "ru")
    photos = load_photos()
    file_ids = normalize_photo_list(photos.get(key))
    title = PHOTO_TITLES_UZ.get(key, key) if lang == "uz" else PHOTO_KEYS.get(key, key)
    if not file_ids:
        await update.effective_message.reply_text(
            f"📸 {title}\n\nФото пока не подключено. Администратор добавит его после загрузки."
            if lang == "uz" else
            f"📸 {title}\n\nФото пока не подключено. Мы добавим его на следующем этапе.",
            reply_markup=funlandia_menu(lang) if key not in ("birthday1", "birthday2", "birthday3") else birthday_menu(lang)
        )
        return
    reply_markup = funlandia_menu(lang) if key not in ("birthday1", "birthday2", "birthday3") else birthday_menu(lang)
    for index, file_id in enumerate(file_ids):
        await update.effective_message.reply_photo(
            photo=file_id,
            caption=title if index == 0 else None,
            reply_markup=reply_markup if index == len(file_ids) - 1 else None
        )

async def setphoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    args = context.args
    if not args or args[0] not in PHOTO_KEYS:
        keys = "\n".join(f"/setphoto {k}" for k in PHOTO_KEYS)
        await update.effective_message.reply_text(
            "Использование:\n"
            "/setphoto entrance\n\n"
            "После этого отправляйте сколько угодно фотографий подряд.\n"
            "Когда закончите, отправьте /donephoto.\n\n"
            "Доступные ключи:\n" + keys
        )
        return
    key = args[0]
    context.user_data["setting_photo"] = key
    photos = load_photos()
    count = len(normalize_photo_list(photos.get(key)))
    if key == "promotion":
        # Starting a new monthly promotion replaces the previous promotion photos.
        photos["promotion"] = []
        save_photos(photos)
        context.user_data["promotion_new"] = True
        await update.effective_message.reply_text(
            "📸 Раздел: 🎁 Акция месяца\n\n"
            "Старая акция очищена.\n\n"
            "Теперь отправьте 2 новые фотографии акции подряд.\n"
            "После второй фотографии отправьте /donephoto."
        )
    else:
        await update.effective_message.reply_text(
            f"📸 Раздел: {PHOTO_KEYS[key]}\n\n"
            f"Уже сохранено: {count} фото.\n\n"
            "Теперь отправляйте фотографии подряд — 2, 5, 10 и больше.\n"
            "Когда закончите, отправьте /donephoto.\n\n"
            "Новые фото будут ДОБАВЛЯТЬСЯ, старые не удаляются."
        )

async def setpromo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    key = "promotion"
    context.user_data["setting_photo"] = key
    photos = load_photos()
    photos["promotion"] = []
    save_photos(photos)

    await update.effective_message.reply_text(
        "📸 АКЦИЯ МЕСЯЦА\n\n"
        "Старая акция очищена.\n\n"
        "Теперь отправьте 2 новые фотографии подряд.\n"
        "После этого отправьте /donephoto."
    )


async def donephoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    key = context.user_data.pop("setting_photo", None)
    if not key:
        await update.effective_message.reply_text("ℹ️ Сейчас нет активной загрузки фотографий.")
        return
    photos = load_photos()
    count = len(normalize_photo_list(photos.get(key)))
    await update.effective_message.reply_text(
        f"✅ Готово! Для «{PHOTO_KEYS[key]}» сохранено: {count} фото.\n\n"
        "Теперь можно выбрать следующий раздел через /setphoto key."
    )

async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    key = context.user_data.get("setting_photo")
    if not key:
        return
    photo = update.effective_message.photo[-1]
    photos = load_photos()
    file_ids = normalize_photo_list(photos.get(key))
    file_ids.append(photo.file_id)
    photos[key] = file_ids
    save_photos(photos)
    await update.effective_message.reply_text(
        f"✅ Фото №{len(file_ids)} сохранено для: {PHOTO_KEYS[key]}\n"
        "Можешь отправить следующее фото. Когда закончишь — /donephoto"
    )

async def birthday_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step-by-step birthday booking form."""
    lang = context.user_data.get("lang", "ru")
    step = context.user_data.get("birthday_step", 1)
    value = (update.effective_message.text or "").strip()
    data = context.user_data.setdefault("birthday", {})

    # The current step is the field we are receiving.
    fields_ru = [
        ("name", "🎂 Как зовут именинника?"),
        ("age", "🎈 Сколько лет исполнится имениннику?"),
        ("date", "📅 На какую дату планируете праздник?"),
        ("children", "👧👦 Сколько будет детей?"),
        ("time", "🕐 На какое время планируете праздник?"),
        ("phone", "📞 Оставьте номер телефона для связи:"),
        ("seat_zone", "🪑 Какую зону посадки выбираете: Зона 1, Зона 2 или Зона 3?"),
        ("extras", "🎁 Дополнительные услуги\n\n🎈 Оформление шарами\n🫧 Мыльные пузыри\n🎭 Оформление стены с героями\n\nНапишите, что хотите добавить: «шары», «мыльные пузыри», «стена с героями», несколько услуг сразу или «без доп. услуг»."),
        ("advance", "💰 Аванс — минимум 100 000 сум после подтверждения заявки. Готовы внести аванс после подтверждения? Напишите: да / нет."),
    ]
    fields_uz = [
        ("name", "🎂 Ismalochining ismi nima?"),
        ("age", "🎈 Ismalochining yoshi nechaga to‘ladi?"),
        ("date", "📅 Bayram qaysi sanada bo‘ladi?"),
        ("children", "👧👦 Nechta bola bo‘ladi?"),
        ("time", "🕐 Bayram uchun qaysi vaqt qulay?"),
        ("phone", "📞 Bog‘lanish uchun telefon raqamingizni yozing:"),
        ("seat_zone", "🪑 Qaysi o‘tirish zonasini tanlaysiz: 1-zona, 2-zona yoki 3-zona?"),
        ("extras", "🎁 Qo‘shimcha xizmatlar\n\n🎈 Sharlar bilan bezatish\n🫧 Sovun pufaklari\n🎭 Qahramonlar bilan devor bezagi\n\nNimani xohlashingizni yozing: «sharlar», «sovun pufaklari», «qahramonlar bilan devor», bir nechta xizmat yoki «qo‘shimcha xizmatlarsiz»."),
        ("advance", "💰 Avans — ariza tasdiqlangandan keyin kamida 100 000 so‘m. Tasdiqlangandan keyin avans to‘lashga tayyormisiz? Ha / yo‘q."),
    ]

    fields = fields_uz if lang == "uz" else fields_ru

    if not value:
        await update.effective_message.reply_text(
            "Пожалуйста, напишите ответ."
            if lang == "ru" else
            "Iltimos, javobingizni yozing."
        )
        return

    key, next_prompt = fields[step - 1]
    data[key] = value

    if step < len(fields):
        context.user_data["birthday_step"] = step + 1
        await update.effective_message.reply_text(next_prompt)
        return

    # All fields collected: show a confirmation summary instead of sending
    # immediately to the administrator.
    context.user_data["birthday_step"] = 10
    summary = (
        "🎂 ПРОВЕРЬТЕ ЗАЯВКУ НА ДЕНЬ РОЖДЕНИЯ\n\n"
        f"👤 Именинник: {data['name']}\n"
        f"🎈 Возраст: {data['age']}\n"
        f"📅 Дата: {data['date']}\n"
        f"👧👦 Детей: {data['children']}\n"
        f"🕐 Время: {data['time']}\n"
        f"📞 Телефон: {data['phone']}\n"
        f"🪑 Зона посадки: {data['seat_zone']}\n"
        f"🎁 Дополнительные услуги: {data['extras']}\n"
        f"💰 Аванс: {data['advance']}\n\n"
        "Нажмите «Подтвердить заявку», чтобы отправить её администратору."
        if lang == "ru" else
        "🎂 TUG‘ILGAN KUN BRONI ARIZASINI TEKSHIRING\n\n"
        f"👤 Ismalochi: {data['name']}\n"
        f"🎈 Yosh: {data['age']}\n"
        f"📅 Sana: {data['date']}\n"
        f"👧👦 Bolalar: {data['children']}\n"
        f"🕐 Vaqt: {data['time']}\n"
        f"📞 Telefon: {data['phone']}\n"
        f"🪑 O‘tirish zonasi: {data['seat_zone']}\n"
        f"🎁 Qo‘shimcha xizmatlar: {data['extras']}\n"
        f"💰 Avans: {data['advance']}\n\n"
        "Arizani administratorga yuborish uchun «Arizani tasdiqlash» tugmasini bosing."
    )
    keyboard = (
        ReplyKeyboardMarkup(two_col([["✅ Подтвердить заявку", "✏️ Изменить"], ["🔙 Назад"]]), resize_keyboard=True)
        if lang == "ru" else
        ReplyKeyboardMarkup(two_col([["✅ Arizani tasdiqlash", "✏️ O‘zgartirish"], ["🔙 Orqaga"]]), resize_keyboard=True)
    )
    await update.effective_message.reply_text(summary, reply_markup=keyboard)


async def finish_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the completed birthday booking to the administrator."""
    lang = context.user_data.get("lang", "ru")
    data = context.user_data.get("birthday", {})
    username = update.effective_user.username or "нет username"

    msg = (
        "🎂 НОВАЯ ЗАЯВКА FUNLANDIA\n\n"
        f"👤 Именинник: {data.get('name', '')}\n"
        f"🎈 Возраст: {data.get('age', '')}\n"
        f"📅 Дата: {data.get('date', '')}\n"
        f"👧👦 Детей: {data.get('children', '')}\n"
        f"🕐 Время: {data.get('time', '')}\n"
        f"📞 Телефон: {data.get('phone', '')}\n"
        f"🪑 Зона посадки: {data.get('seat_zone', '')}\n"
        f"🎁 Дополнительные услуги: {data.get('extras', '')}\n"
        f"💰 Аванс: {data.get('advance', '')}\n"
        f"Telegram: @{username}"
    )

    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg)
        except Exception as exc:
            print(f"Birthday admin notification error: {exc}")

    context.user_data.clear()
    context.user_data["lang"] = lang

    await update.effective_message.reply_text(
        "✅ Arizangiz administratorga yuborildi!\n\n"
        "💰 Bronni tasdiqlash uchun kamida 100 000 so‘m avans kerak.\n"
        "Administrator FUNLANDIA siz bilan bog‘lanadi."
        if lang == "uz" else
        "✅ Заявка отправлена администратору!\n\n"
        "💰 Для подтверждения бронирования необходим аванс — минимум 100 000 сум.\n"
        "Администратор FUNLANDIA свяжется с вами.",
        reply_markup=menu(lang)
    )


async def birthday_confirm_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "ru")
    text = (update.effective_message.text or "").strip()

    if text in ("✏️ Изменить", "✏️ O‘zgartirish"):
        context.user_data["birthday_step"] = 1
        context.user_data["birthday"] = {}
        await update.effective_message.reply_text(
            "Начнём заявку заново. 🎂\n\nКак зовут именинника?"
            if lang == "ru" else
            "Arizani boshidan boshlaymiz. 🎂\n\nIsmalochining ismi nima?"
        )
        return True

    if text in ("✅ Подтвердить заявку", "✅ Arizani tasdiqlash"):
        await finish_birthday(update, context)
        return True

    return False

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or "").strip()
    lang = context.user_data.get("lang", "ru")

    if text in ("🇺🇿 O‘zbekcha", "UZ O‘zbekcha"):
        return await uz_start(update, context)
    if text == "🇷🇺 Русский":
        return await start(update, context)

    if text in ("🔙 Назад", "🔙 Orqaga"):
        context.user_data.pop("birthday_step", None)
        context.user_data.pop("birthday", None)
        return await update.effective_message.reply_text(
            "Главное меню:" if lang == "ru" else "Asosiy menyu:",
            reply_markup=menu(lang)
        )

    if text in ("📸 ФОТО-ГИД", "📸 FOTO-GID"):
        return await funlandia(update, lang)

    if text in ("🎁 Акция месяца", "🎁 Aksiya oyi"):
        return await september_promo(update, context, lang)

    if text in ("🤖 Авто-секретарь", "🤖 Avto-kotib"):
        return await secretary(update, context)

    if text in ("🎟️ Цены", "🎟️ Narxlar"):
        return await prices(update, lang)
    if text in ("🎂 День рождения", "🎂 Tug‘ilgan kun"):
        return await birthday_gallery(update, lang)
    if text in ("🎉 Забронировать день рождения", "🎉 Tug‘ilgan kunni bron qilish"):
        return await birthday_gallery(update, lang)
    if text in ("📝 Забронировать день рождения", "📝 Tug‘ilgan kunni bron qilish"):
        return await birthday(update, context)
    if text in ("🎠 Развлечения", "🎠 Ko‘ngilochar"):
        return await attractions(update, lang)
    if text in ("📍 Адрес", "📍 Manzil"):
        return await simple(update, lang, "address")
    if text in ("🕐 Время работы", "🕐 Ish vaqti"):
        return await hours(update, lang)
    if text in ("📞 Контакт", "📞 Kontakt", "📞 Контакты", "📞 Aloqa"):
        return await contacts(update, lang)
    if text in ("📸 Instagram",):
        return await simple(update, lang, "instagram")
    if text in ("📱 Telegram",):
        return await simple(update, lang, "telegram")

    photo_map = {
        "🚪 Вход в FUNLANDIA": "entrance",
        "🎟️ Касса": "cashier",
        "🤸 Батуты": "trampoline",
        "🛝 Детская площадка": "playground",
        "🎠 Карусели": "carousel",
        "🎮 Игровые автоматы": "arcade",
        "🏎️ Автодром": "autodrome",
        "🪢 Канатная дорога": "ninja",
        "🚪 FUNLANDIA kirish": "entrance",
        "🎟️ Kassa": "cashier",
        "🤸 Batutlar": "trampoline",
        "🛝 Bolalar maydonchasi": "playground",
        "🎠 Karusellar": "carousel",
        "🎮 O'yin avtomatlari": "arcade",
        "🏎️ Avtodrom": "autodrome",
        "🪢 Канатная дорога": "ninja",
        "🎈 Зона №1": "birthday1",
        "🎈 Зона №2": "birthday2",
        "🎈 Зона №3": "birthday3",
        "🎈 Zona №1": "birthday1",
        "🎈 Zona №2": "birthday2",
        "🎈 Zona №3": "birthday3",
    }
    if text in photo_map:
        return await send_photo_key(update, context, photo_map[text])

    if context.user_data.get("birthday_step") == 10:
        if await birthday_confirm_or_edit(update, context):
            return
    if context.user_data.get("birthday_step"):
        return await birthday_form(update, context)

    return await secretary_answer(update, context)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    # Keep the bot running even if one user message causes an exception.
    print(f"Bot error: {context.error}")

async def business_connection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Telegram Business connection updates."""
    connection = getattr(update, "business_connection", None)
    if not connection:
        return

    if is_admin(update) and ADMIN_CHAT_ID:
        rights = getattr(connection, "rights", None)
        can_reply = getattr(rights, "can_reply", False)
        status = "разрешены" if can_reply else "не подтверждены"
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    "🔗 Telegram Business подключён.\n"
                    f"Ответы от имени аккаунта: {status}"
                ),
            )
        except Exception as exc:
            print(f"Business connection notification error: {exc}")


async def business_redirect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Telegram Business secretary.

    IMPORTANT: ReplyKeyboardMarkup is not supported for messages sent on behalf
    of a Business account, so the language selector and the final bot link use
    InlineKeyboardMarkup.
    """
    message = update.effective_message
    if not message:
        return

    business_languages = context.application.bot_data.setdefault("business_languages", {})
    chat_id = message.chat.id
    lang = business_languages.get(str(chat_id))

    # First message from a client: ask for language with inline buttons.
    if not lang:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇷🇺 Русский", callback_data="business_lang_ru"),
                InlineKeyboardButton("🇺🇿 O‘zbekcha", callback_data="business_lang_uz"),
            ]
        ])
        await message.reply_text(
            "👋 Здравствуйте! Выберите язык / Tilni tanlang:",
            reply_markup=keyboard,
        )
        return

    await send_business_redirect(message, context, lang)


async def send_business_redirect(message, context, lang):
    """Send the localized redirect with an inline URL button."""
    if lang == "uz":
        text_out = "👇 To‘liq ma’lumot uchun bizning botimizga o‘ting"
        button = "🎉 FUNLANDIA BOTINI OCHISH"
    else:
        text_out = "👇 Для полной информации перейдите в наш бот"
        button = "🎉 ОТКРЫТЬ FUNLANDIA"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(button, url="https://t.me/Funlandiauzbot")]
    ])

    await message.reply_text(text_out, reply_markup=keyboard)


async def business_callback_raw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle Telegram's updateBusinessBotCallbackQuery directly.

    python-telegram-bot 22.8 does not yet expose this Business-specific update
    as a dedicated Update field, but unknown Bot API fields are preserved in
    Update.api_kwargs. We therefore read it there and answer through the
    business_connection_id supplied by Telegram.
    """
    raw = getattr(update, "api_kwargs", {}) or {}
    callback = raw.get("business_bot_callback_query")
    if not callback:
        # Be tolerant if a future PTB version exposes it as a real attribute.
        callback = getattr(update, "business_bot_callback_query", None)
    if not callback:
        return

    data = callback.get("data", "") if isinstance(callback, dict) else getattr(callback, "data", "")
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="ignore")
    data = str(data or "")
    if data not in ("business_lang_ru", "business_lang_uz"):
        return

    connection_id = callback.get("connection_id") if isinstance(callback, dict) else getattr(callback, "connection_id", None)
    query_id = callback.get("query_id") if isinstance(callback, dict) else getattr(callback, "query_id", None)
    raw_message = callback.get("message") if isinstance(callback, dict) else getattr(callback, "message", None)
    if not connection_id or not query_id or not raw_message:
        return

    raw_chat = raw_message.get("chat", {}) if isinstance(raw_message, dict) else getattr(raw_message, "chat", None)
    if isinstance(raw_chat, dict):
        chat_id = raw_chat.get("id")
    else:
        chat_id = getattr(raw_chat, "id", None)
    if not chat_id:
        return

    lang = "ru" if data == "business_lang_ru" else "uz"

    # Keep the selected language for this Business chat.
    business_languages = context.application.bot_data.setdefault("business_languages", {})
    business_languages[str(chat_id)] = lang

    # Telegram requires an answer to every callback query.
    try:
        await context.bot.answer_callback_query(callback_query_id=str(query_id))
    except Exception as exc:
        print(f"Business callback answer error: {exc}")

    if lang == "uz":
        text_out = "👇 To‘liq ma’lumot uchun bizning botimizga o‘ting"
        button = "🎉 FUNLANDIA BOTINI OCHISH"
    else:
        text_out = "👇 Для полной информации перейдите в наш бот"
        button = "🎉 ОТКРЫТЬ FUNLANDIA"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(button, url="https://t.me/Funlandiauzbot")]
    ])

    await context.bot.send_message(
        chat_id=chat_id,
        text=text_out,
        reply_markup=keyboard,
        business_connection_id=connection_id,
    )

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setphoto", setphoto))
    app.add_handler(CommandHandler("setpromo", setpromo))
    app.add_handler(CommandHandler("donephoto", donephoto))

    # Telegram Business / Secretary Mode.
    # Telegram sends a BusinessConnection update when the account is connected.
    app.add_handler(BusinessConnectionHandler(business_connection))

    # Telegram Business / Secretary Mode.
    # Messages arriving through a connected Business account are delivered
    # as BUSINESS_MESSAGE updates.
    app.add_handler(
        MessageHandler(
            filters.UpdateType.BUSINESS_MESSAGE,
            business_redirect,
        )
    )

    # Telegram currently delivers Business inline-button clicks as the raw
    # updateBusinessBotCallbackQuery update. PTB 22.8 does not expose it in
    # Update.ALL_TYPES, so handle it through api_kwargs.
    app.add_handler(TypeHandler(Update, business_callback_raw))

    # Normal bot chats.
    app.add_handler(MessageHandler(filters.PHOTO, receive_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))
    app.add_error_handler(error_handler)

    # Explicitly receive normal + Business updates, including the
    # Business callback update that is not yet listed in PTB 22.8 ALL_TYPES.
    allowed_updates = list(Update.ALL_TYPES)
    if "business_bot_callback_query" not in allowed_updates:
        allowed_updates.append("business_bot_callback_query")
    app.run_polling(allowed_updates=allowed_updates)

if __name__ == "__main__":
    main()
