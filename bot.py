import os
import json
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, BusinessConnectionHandler, filters

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

PHOTO_TITLES_EN = {
    "entrance": "🚪 FUNLANDIA Entrance",
    "cashier": "🎟️ Cashier",
    "trampoline": "🤸 Trampolines",
    "playground": "🛝 Kids Playground",
    "carousel": "🎠 Carousels",
    "arcade": "🎮 Arcade Games",
    "autodrome": "🏎️ Bumper Cars",
    "ninja": "🪢 Rope Course",
    "birthday1": "🎈 Zone №1",
    "birthday2": "🎈 Zone №2",
    "birthday3": "🎈 Zone №3",
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
            ["🇬🇧 English"],
        ]
    elif lang == "en":
        rows = [
            ["📸 PHOTO GUIDE", "🎟️ Prices"],
            ["🤖 Auto Secretary", "🎁 Promotion"],
            ["🎠 Attractions", "📍 Address"],
            ["🎉 Book a Birthday", "🕐 Opening Hours"],
            ["📞 Contact", "📸 Instagram"],
            ["📱 Telegram", "🇷🇺 Русский"],
            ["🇺🇿 O‘zbekcha"],
        ]
    else:
        rows = [
            ["📸 ФОТО-ГИД", "🎟️ Цены"],
            ["🤖 Авто-секретарь", "🎁 Акция месяца"],
            ["🎠 Развлечения", "📍 Адрес"],
            ["🎉 Забронировать день рождения", "🕐 Время работы"],
            ["📞 Контакт", "📸 Instagram"],
            ["📱 Telegram", "🇺🇿 O‘zbekcha"],
            ["🇬🇧 English"],
        ]
    return ReplyKeyboardMarkup(two_col(rows), resize_keyboard=True)


def funlandia_menu(lang="ru"):
    if lang == "uz":
        rows = [["🚪 FUNLANDIA kirish", "🎟️ Kassa"], ["🤸 Batutlar", "🛝 Bolalar maydonchasi"], ["🎠 Karusellar", "🎮 O'yin avtomatlari"], ["🏎️ Avtodrom", "🪢 Kanat yo‘li"], ["🔙 Orqaga"]]
    elif lang == "en":
        rows = [["🚪 FUNLANDIA Entrance", "🎟️ Cashier"], ["🤸 Trampolines", "🛝 Kids Playground"], ["🎠 Carousels", "🎮 Arcade Games"], ["🏎️ Bumper Cars", "🪢 Rope Course"], ["🔙 Back"]]
    else:
        rows = [["🚪 Вход в FUNLANDIA", "🎟️ Касса"], ["🤸 Батуты", "🛝 Детская площадка"], ["🎠 Карусели", "🎮 Игровые автоматы"], ["🏎️ Автодром", "🪢 Канатная дорога"], ["🔙 Назад"]]
    return ReplyKeyboardMarkup(two_col(rows), resize_keyboard=True)


def birthday_menu(lang="ru"):
    if lang == "uz":
        rows = [["🎈 Zona №1", "🎈 Zona №2"], ["🎈 Zona №3", "📝 Tug‘ilgan kunni bron qilish"], ["🔙 Orqaga"]]
    elif lang == "en":
        rows = [["🎈 Zone №1", "🎈 Zone №2"], ["🎈 Zone №3", "📝 Book a Birthday"], ["🔙 Back"]]
    else:
        rows = [["🎈 Зона №1", "🎈 Зона №2"], ["🎈 Зона №3", "📝 Забронировать день рождения"], ["🔙 Назад"]]
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
    requested_lang = context.args[0].lower() if context.args else "ru"
    lang = requested_lang if requested_lang in ("ru", "uz", "en") else "ru"
    context.user_data.clear()
    context.user_data["lang"] = lang
    messages = {
        "ru": ("🎉 ДОБРО ПОЖАЛОВАТЬ В FUNLANDIA! 🎉\n\nМесто, где дети играют, веселятся и получают яркие эмоции, а родители отдыхают! ❤️\n\n🛝 Лабиринты • 🤸 Батуты • 🎢 Горки • 🎯 Пневмопушки • 🧗 Тарзанка\n\nВыберите интересующий раздел ниже 👇"),
        "uz": ("🎉 FUNLANDIA'GA XUSH KELIBSIZ! 🎉\n\nBu yerda bolalar o‘ynaydi, quvonadi va yorqin taassurotlar oladi, ota-onalar esa maroqli dam oladi! ❤️\n\n🛝 Labirintlar • 🤸 Batutlar • 🎢 Tepaliklar • 🎯 Pnevmatik to‘plar • 🧗 Tarzanka\n\nKerakli bo‘limni tanlang 👇"),
        "en": ("🎉 WELCOME TO FUNLANDIA! 🎉\n\nA place where children play, have fun and enjoy bright emotions, while parents relax! ❤️\n\n🛝 Labyrinths • 🤸 Trampolines • 🎢 Slides • 🎯 Air Cannons • 🧗 Rope Adventure\n\nChoose a section below 👇")
    }
    await update.effective_message.reply_text(messages[lang], reply_markup=menu(lang))


async def uz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = ["uz"]
    return await start(update, context)


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
    texts = {
      "ru": "🤖 АВТО-СЕКРЕТАРЬ FUNLANDIA\n\nЯ помогу вам узнать:\n💰 цены\n🎂 день рождения и бронирование\n🕐 график работы и санитарный день\n📍 адрес\n📞 телефон\n📸 Instagram\n📱 Telegram\n\nНапишите свой вопрос — я постараюсь сразу ответить.",
      "uz": "🤖 AVTO-KOTIB FUNLANDIA\n\nMen sizga yordam beraman:\n💰 narxlar\n🎂 tug‘ilgan kun va bron\n🕐 ish vaqti va sanitariya kuni\n📍 manzil\n📞 telefon\n📸 Instagram\n📱 Telegram\n\nSavolingizni yozing — kerakli ma’lumotni beraman.",
      "en": "🤖 FUNLANDIA AUTO SECRETARY\n\nI can help you with:\n💰 prices\n🎂 birthdays and bookings\n🕐 opening hours and sanitation day\n📍 address\n📞 phone\n📸 Instagram\n📱 Telegram\n\nWrite your question — I will try to answer right away."}
    await update.effective_message.reply_text(texts.get(lang, texts["ru"]), reply_markup=menu(lang))


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
        text = ("🎟️ FUNLANDIA NARXLARI\n\n🛝 BOLALAR ZONASI\n🏰 Labirintlar\n🎪 Puflanadigan batutlar\n🎢 Tepaliklar\n🎯 Pnevmatik to‘plar\n\n💰 1 soat — 80 000 so‘m\n💰 2 soat — 90 000 so‘m\n♾️ Cheksiz — 100 000 so‘m\n\n👧👦 1 yoshdan 16 yoshgacha — kirish pullik.\n\n🤸 BATUT ZONASI\n💰 1 soat — 80 000 so‘m\n💰 2 soat — 90 000 so‘m\n♾️ Cheksiz — 100 000 so‘m\n⚠️ 7 yoshdan boshlab, ota-ona yoki katta yoshli hamroh nazoratida.\n\n🎉 IKKALA ZONA — 120 000 so‘m\n♾️ Ikkala zonaga cheksiz kirish!")
    elif lang == "en":
        text = ("🎟️ FUNLANDIA PRICES\n\n🛝 KIDS ZONE\n🏰 Labyrinths\n🎪 Inflatable trampolines\n🎢 Slides\n🎯 Air cannons\n\n💰 1 hour — 80,000 UZS\n💰 2 hours — 90,000 UZS\n♾️ Unlimited — 100,000 UZS\n\n👧👦 Children from 1 to 16 years — paid entry.\n\n🤸 TRAMPOLINE ZONE\n💰 1 hour — 80,000 UZS\n💰 2 hours — 90,000 UZS\n♾️ Unlimited — 100,000 UZS\n⚠️ From 7 years old, under parent/adult supervision.\n\n🎉 BOTH ZONES — 120,000 UZS\n♾️ Unlimited access to both zones!")
    else:
        text = ("🎟️ ЦЕНЫ FUNLANDIA\n\n🛝 ДЕТСКАЯ ЗОНА\n🏰 Лабиринты\n🎪 Надувные батуты\n🎢 Горки\n🎯 Пневмопушки\n\n💰 1 час — 80 000 сум\n💰 2 часа — 90 000 сум\n♾️ Безлимит — 100 000 сум\n\n👧👦 Детям от 1 года до 16 лет — вход платный.\n\n🤸 БАТУТНАЯ ЗОНА\n💰 1 час — 80 000 сум\n💰 2 часа — 90 000 сум\n♾️ Безлимит — 100 000 сум\n⚠️ С 7 лет, только под присмотром родителей или взрослого.\n\n🎉 ДВЕ ЗОНЫ — 120 000 сум\n♾️ Безлимитное посещение обеих зон!")
    await update.effective_message.reply_text(text, reply_markup=menu(lang))


async def hours(update: Update, lang):
    texts={"ru":"🕐 ВРЕМЯ РАБОТЫ FUNLANDIA\n\n🗓 Каждый день: 10:00–22:00\n\n🧹 Каждый понедельник — санитарный день до 14:00.\n🎉 Ждём вас с 14:00 до 22:00!", "uz":"🕐 FUNLANDIA ISH VAQTI\n\n🗓 Har kuni: 10:00–22:00\n\n🧹 Har dushanba — 14:00 gacha sanitariya kuni.\n🎉 Sizni 14:00 dan 22:00 gacha kutamiz!", "en":"🕐 FUNLANDIA OPENING HOURS\n\n🗓 Every day: 10:00–22:00\n\n🧹 Every Monday — sanitation day until 14:00.\n🎉 We are open from 14:00 to 22:00!"}
    await update.effective_message.reply_text(texts.get(lang,texts["ru"]), reply_markup=menu(lang))


async def contacts(update: Update, lang):
    texts={"ru":"📞 КОНТАКТЫ FUNLANDIA\n\n📞 Контакт: +998933810055\n☎️ Колл-центр: +998555127337\n\n📱 Telegram: @Funlandia_Tashkent\n📸 Instagram: @funlandiauz", "uz":"📞 FUNLANDIA ALOQA\n\n📞 Kontakt: +998933810055\n☎️ Call-markaz: +998555127337\n\n📱 Telegram: @Funlandia_Tashkent\n📸 Instagram: @funlandiauz", "en":"📞 FUNLANDIA CONTACTS\n\n📞 Contact: +998933810055\n☎️ Call center: +998555127337\n\n📱 Telegram: @Funlandia_Tashkent\n📸 Instagram: @funlandiauz"}
    await update.effective_message.reply_text(texts.get(lang,texts["ru"]), reply_markup=menu(lang))


async def direct_contact(update: Update, lang, kind):
    if kind == "call":
        texts={"ru":"☎️ КОЛЛ-ЦЕНТР\n\n📞 +998555127337","uz":"☎️ CALL-MARKAZ\n\n📞 +998555127337","en":"☎️ CALL CENTER\n\n📞 +998555127337"}
    else:
        texts={"ru":"📞 КОНТАКТ\n\n📞 +998933810055","uz":"📞 KONTAKT\n\n📞 +998933810055","en":"📞 CONTACT\n\n📞 +998933810055"}
    await update.effective_message.reply_text(texts.get(lang,texts["ru"]), reply_markup=menu(lang))

async def simple(update: Update, lang, kind):
    if kind == "address":
        ending={"ru":"Будем рады видеть вас! 🎉","uz":"Sizni kutamiz! 🎉","en":"We look forward to seeing you! 🎉"}
        text=f"📍 FUNLANDIA\n\n{ADDRESS}\n\n{ending.get(lang,ending['ru'])}"
        map_text={"ru":"🗺️ Открыть на карте","uz":"🗺️ Xaritada ochish","en":"🗺️ Open map"}
        keyboard=InlineKeyboardMarkup([[InlineKeyboardButton(map_text.get(lang,map_text["ru"]),url="https://yandex.uz/maps/-/CTT~uR0N")]])
        await update.effective_message.reply_text(text,reply_markup=keyboard); return
    if kind == "instagram":
        label={"ru":"📸 Instagram FUNLANDIA","uz":"📸 Instagram FUNLANDIA","en":"📸 FUNLANDIA Instagram"}[lang]
        text=f"{label}\n\n{INSTAGRAM}"
    else:
        label={"ru":"📱 Telegram FUNLANDIA","uz":"📱 Telegram FUNLANDIA","en":"📱 FUNLANDIA Telegram"}[lang]
        text=f"{label}\n\n{TELEGRAM}"
    await update.effective_message.reply_text(text,reply_markup=menu(lang))

async def attractions(update: Update, lang):
    texts={"ru":"🎠 НАШИ РАЗВЛЕЧЕНИЯ\n\n🛝 4-этажные лабиринты\n🎪 Надувные батуты\n🤸 Профессиональные батуты\n🎢 Горки\n🛝 17-метровая горка\n🧗 Тарзанка\n🎯 Пневмопушки\n🧸 Зона для малышей\n🏖️ Кинетический песок\n🎠 Карусели", "uz":"🎠 BIZNING KO‘NGILOCHARLAR\n\n🛝 4 qavatli labirintlar\n🎪 Puflanadigan batutlar\n🤸 Professional batutlar\n🎢 Tepaliklar\n🛝 17 metrlik tepalik\n🧗 Tarzanka\n🎯 Pnevmatik to‘plar\n🧸 Kichkintoylar zonasi\n🏖️ Kinetik qum\n🎠 Karusellar", "en":"🎠 OUR ATTRACTIONS\n\n🛝 4-floor labyrinths\n🎪 Inflatable trampolines\n🤸 Professional trampolines\n🎢 Slides\n🛝 17-meter slide\n🧗 Rope adventure\n🎯 Air cannons\n🧸 Toddler zone\n🏖️ Kinetic sand\n🎠 Carousels"}
    await update.effective_message.reply_text(texts.get(lang,texts["ru"]), reply_markup=menu(lang))


async def funlandia(update: Update, lang):
    texts={"ru":"🎡 FUNLANDIA\n\nВыберите раздел:","uz":"🎡 FUNLANDIA\n\nTanlang:","en":"🎡 FUNLANDIA\n\nChoose a section:"}
    await update.effective_message.reply_text(texts.get(lang,texts["ru"]), reply_markup=funlandia_menu(lang))


async def birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang=context.user_data.get("lang","ru"); context.user_data["birthday_step"]=1; context.user_data["birthday"]={}
    texts={
      "ru":"🎂 ДЕНЬ РОЖДЕНИЯ В FUNLANDIA!\n\n🎁 АКЦИЯ ДЛЯ ИМЕНИННИКА\n\nПразднование проходит в одной выбранной зоне:\n🛝 Детская площадка\n🤸 Батутная зона\n\n👧 5 детей — 450 000 сум\n👦 10 детей — 900 000 сум\n\n🍽️ ЗАКАЗ СТОЛА\n🪑 Стол на 3 часа — 200 000 сум\n➕ Дополнительное время — 50 000 сум за каждый час\n\n🪑 ВЫБОР ЗОНЫ ПОСАДКИ\n1️⃣ Зона 1\n2️⃣ Зона 2\n3️⃣ Зона 3\n\n💰 Для подтверждения бронирования необходим аванс — минимум 100 000 сум.\n\nЧтобы оставить заявку, напишите имя именинника:",
      "uz":"🎂 FUNLANDIA'DA TUG‘ILGAN KUN!\n\n🎁 TUG‘ILGAN KUN EGASI UCHUN AKSIYA\n\nBayram bitta tanlangan zonada:\n🛝 Bolalar maydonchasi\n🤸 Batut zonasi\n\n👧 5 bola — 450 000 so‘m\n👦 10 bola — 900 000 so‘m\n\n🍽️ STOL BUYURTMA QILISH\n🪑 3 soatga stol — 200 000 so‘m\n➕ Qo‘shimcha vaqt — har bir soat uchun 50 000 so‘m\n\n🪑 O‘TIRISH ZONASINI TANLASH\n1️⃣ Zona 1\n2️⃣ Zona 2\n3️⃣ Zona 3\n\n💰 Bronni tasdiqlash uchun kamida 100 000 so‘m avans kerak.\n\nAriza qoldirish uchun tug‘ilgan kun egasining ismini yozing:",
      "en":"🎂 BIRTHDAY AT FUNLANDIA!\n\n🎁 BIRTHDAY CHILD SPECIAL OFFER\n\nThe celebration takes place in one selected zone:\n🛝 Kids Playground\n🤸 Trampoline Zone\n\n👧 5 children — 450,000 UZS\n👦 10 children — 900,000 UZS\n\n🍽️ TABLE BOOKING\n🪑 Table for 3 hours — 200,000 UZS\n➕ Extra time — 50,000 UZS per hour\n\n🪑 SEATING ZONE\n1️⃣ Zone 1\n2️⃣ Zone 2\n3️⃣ Zone 3\n\n💰 A minimum advance payment of 100,000 UZS is required to confirm the booking.\n\nTo submit a request, write the birthday child’s name:"}
    await update.effective_message.reply_text(texts[lang], reply_markup=menu(lang))


async def september_promo(update: Update, context: ContextTypes.DEFAULT_TYPE, lang):
    photos=load_photos(); file_ids=normalize_photo_list(photos.get("promotion"))
    title={"ru":"🎁 АКЦИЯ МЕСЯЦА","uz":"🎁 OY AKSIYASI","en":"🎁 PROMOTION"}.get(lang,"🎁 PROMOTION")
    if file_ids:
        for index,file_id in enumerate(file_ids):
            await update.effective_message.reply_photo(photo=file_id, caption=title if index==0 else None, reply_markup=menu(lang) if index==len(file_ids)-1 else None)
    else:
        empty={"ru":"Фото акции пока не загружены.","uz":"Aksiya fotosuratlari hali yuklanmagan.","en":"Promotion photos have not been uploaded yet."}
        await update.effective_message.reply_text(title+"\n\n"+empty.get(lang,empty["en"]), reply_markup=menu(lang))


async def birthday_gallery(update: Update, lang):
    intros={"ru":"🎂 ДЕНЬ РОЖДЕНИЯ В FUNLANDIA!\n\n🎈 Фотографии зон для празднования:\n🪑 1️⃣ Зона 1\n🪑 2️⃣ Зона 2\n🪑 3️⃣ Зона 3", "uz":"🎂 FUNLANDIA'DA TUG‘ILGAN KUN!\n\n🎈 Bayram zonalari fotosuratlari:\n🪑 1️⃣ Zona 1\n🪑 2️⃣ Zona 2\n🪑 3️⃣ Zona 3", "en":"🎂 BIRTHDAY AT FUNLANDIA!\n\n🎈 Photos of our birthday zones:\n🪑 1️⃣ Zone 1\n🪑 2️⃣ Zone 2\n🪑 3️⃣ Zone 3"}
    await update.effective_message.reply_text(intros.get(lang,intros["ru"]))
    photos=load_photos()
    zone_keys=(("birthday1","🎈 Зона №1","🎈 Zona №1"),("birthday2","🎈 Зона №2","🎈 Zona №2"),("birthday3","🎈 Зона №3","🎈 Zona №3"))
    shown=0
    for key,title_ru,title_uz in zone_keys:
        title=title_ru if lang=="ru" else (title_uz if lang=="uz" else f"🎈 Zone №{key[-1]}")
        for index,file_id in enumerate(normalize_photo_list(photos.get(key))):
            await update.effective_message.reply_photo(photo=file_id,caption=title if index==0 else None); shown+=1
    if shown==0:
        no={"ru":"📸 Фото зон пока не загружены. Ниже можно выбрать зону или оформить бронь.","uz":"📸 Zona fotosuratlari hali yuklanmagan. Quyida zonani tanlashingiz yoki bron qilishingiz mumkin.","en":"📸 Zone photos have not been uploaded yet. You can choose a zone or start a booking below."}
        await update.effective_message.reply_text(no.get(lang,no["ru"]))
    else:
        choose={"ru":"👇 Выберите нужную зону или сразу оформите бронирование:","uz":"👇 Kerakli zonani tanlang yoki bronni boshlang:","en":"👇 Choose a zone or start your booking:"}
        await update.effective_message.reply_text(choose.get(lang,choose["ru"]))
    await update.effective_message.reply_text("👇",reply_markup=birthday_menu(lang))

async def send_photo_key(update: Update, context: ContextTypes.DEFAULT_TYPE, key):
    lang = context.user_data.get("lang", "ru")
    photos = load_photos()
    file_ids = normalize_photo_list(photos.get(key))
    title = PHOTO_TITLES_UZ.get(key, key) if lang == "uz" else (PHOTO_TITLES_EN.get(key, key) if lang == "en" else PHOTO_KEYS.get(key, key))
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
    lang=context.user_data.get("lang","ru"); step=context.user_data.get("birthday_step",1); value=(update.effective_message.text or "").strip(); data=context.user_data.setdefault("birthday",{})
    fields={
      "ru":[("name","🎂 Как зовут именинника?"),("age","🎈 Сколько лет исполнится имениннику?"),("date","📅 На какую дату планируете праздник?"),("children","👧👦 Сколько будет детей?"),("time","🕐 На какое время планируете праздник?"),("phone","📞 Оставьте номер телефона для связи:"),("seat_zone","🪑 Какую зону посадки выбираете: Зона 1, Зона 2 или Зона 3?"),("extras","🎁 Дополнительные услуги\n\n🎈 Оформление шарами\n🫧 Мыльные пузыри\n🎭 Оформление стены с героями\n\nНапишите, что хотите добавить или «без доп. услуг»."),("advance","💰 Аванс — минимум 100 000 сум после подтверждения заявки. Готовы внести аванс после подтверждения? Напишите: да / нет.")],
      "uz":[("name","🎂 Tug‘ilgan kun egasining ismi nima?"),("age","🎈 Tug‘ilgan kun egasining yoshi nechaga to‘ladi?"),("date","📅 Bayram qaysi sanada bo‘ladi?"),("children","👧👦 Nechta bola bo‘ladi?"),("time","🕐 Bayram uchun qaysi vaqt qulay?"),("phone","📞 Bog‘lanish uchun telefon raqamingizni yozing:"),("seat_zone","🪑 Qaysi o‘tirish zonasini tanlaysiz: 1-zona, 2-zona yoki 3-zona?"),("extras","🎁 Qo‘shimcha xizmatlar\n\n🎈 Sharlar bilan bezatish\n🫧 Sovun pufaklari\n🎭 Qahramonlar bilan devor bezagi\n\nNimani qo‘shishni xohlaysiz yoki «qo‘shimcha xizmatlarsiz» deb yozing."),("advance","💰 Avans — ariza tasdiqlangandan keyin kamida 100 000 so‘m. Tasdiqlangandan keyin avans to‘lashga tayyormisiz? Ha / yo‘q.")],
      "en":[("name","🎂 What is the birthday child’s name?"),("age","🎈 How old will the birthday child be?"),("date","📅 What date are you planning the celebration?"),("children","👧👦 How many children will attend?"),("time","🕐 What time would you like to celebrate?"),("phone","📞 Please leave a phone number for contact:"),("seat_zone","🪑 Which seating zone would you like: Zone 1, Zone 2 or Zone 3?"),("extras","🎁 Additional services\n\n🎈 Balloon decoration\n🫧 Soap bubbles\n🎭 Character wall decoration\n\nTell us what you would like to add, or write “no extras”."),("advance","💰 A minimum advance payment of 100,000 UZS is required after the request is confirmed. Are you ready to pay the advance after confirmation? Yes / no.")]
    }[lang]
    if not value:
        await update.effective_message.reply_text({"ru":"Пожалуйста, напишите ответ.","uz":"Iltimos, javobingizni yozing.","en":"Please enter your answer."}[lang]); return
    key,_current_prompt=fields[step-1]; data[key]=value
    if step<len(fields):
        next_prompt=fields[step][1]
        context.user_data["birthday_step"]=step+1; await update.effective_message.reply_text(next_prompt); return
    context.user_data["birthday_step"]=10
    if lang=="ru":
        summary=("🎂 ПРОВЕРЬТЕ ЗАЯВКУ НА ДЕНЬ РОЖДЕНИЯ\n\n" f"👤 Именинник: {data['name']}\n🎈 Возраст: {data['age']}\n📅 Дата: {data['date']}\n👧👦 Детей: {data['children']}\n🕐 Время: {data['time']}\n📞 Телефон: {data['phone']}\n🪑 Зона посадки: {data['seat_zone']}\n🎁 Дополнительные услуги: {data['extras']}\n💰 Аванс: {data['advance']}\n\nНажмите «Подтвердить заявку», чтобы отправить её администратору.")
        kb=[["✅ Подтвердить заявку","✏️ Изменить"],["🔙 Назад"]]
    elif lang=="uz":
        summary=("🎂 TUG‘ILGAN KUN BRONI ARIZASINI TEKSHIRING\n\n" f"👤 Tug‘ilgan kun egasi: {data['name']}\n🎈 Yosh: {data['age']}\n📅 Sana: {data['date']}\n👧👦 Bolalar: {data['children']}\n🕐 Vaqt: {data['time']}\n📞 Telefon: {data['phone']}\n🪑 O‘tirish zonasi: {data['seat_zone']}\n🎁 Qo‘shimcha xizmatlar: {data['extras']}\n💰 Avans: {data['advance']}\n\nArizani administratorga yuborish uchun «Arizani tasdiqlash» tugmasini bosing.")
        kb=[["✅ Arizani tasdiqlash","✏️ O‘zgartirish"],["🔙 Orqaga"]]
    else:
        summary=("🎂 CHECK YOUR BIRTHDAY BOOKING\n\n" f"👤 Birthday child: {data['name']}\n🎈 Age: {data['age']}\n📅 Date: {data['date']}\n👧👦 Children: {data['children']}\n🕐 Time: {data['time']}\n📞 Phone: {data['phone']}\n🪑 Seating zone: {data['seat_zone']}\n🎁 Additional services: {data['extras']}\n💰 Advance: {data['advance']}\n\nPress “Confirm request” to send it to the administrator.")
        kb=[["✅ Confirm request","✏️ Edit"],["🔙 Back"]]
    await update.effective_message.reply_text(summary,reply_markup=ReplyKeyboardMarkup(two_col(kb),resize_keyboard=True))

async def finish_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang=context.user_data.get("lang","ru"); data=context.user_data.get("birthday",{}); username=update.effective_user.username or "нет username"
    if lang=="en":
        msg=("🎂 NEW FUNLANDIA BIRTHDAY REQUEST\n\n" f"👤 Birthday child: {data.get('name','')}\n🎈 Age: {data.get('age','')}\n📅 Date: {data.get('date','')}\n👧👦 Children: {data.get('children','')}\n🕐 Time: {data.get('time','')}\n📞 Phone: {data.get('phone','')}\n🪑 Seating zone: {data.get('seat_zone','')}\n🎁 Additional services: {data.get('extras','')}\n💰 Advance: {data.get('advance','')}\nTelegram: @{username}")
    else:
        msg=("🎂 НОВАЯ ЗАЯВКА FUNLANDIA\n\n" f"👤 Именинник: {data.get('name','')}\n🎈 Возраст: {data.get('age','')}\n📅 Дата: {data.get('date','')}\n👧👦 Детей: {data.get('children','')}\n🕐 Время: {data.get('time','')}\n📞 Телефон: {data.get('phone','')}\n🪑 Зона посадки: {data.get('seat_zone','')}\n🎁 Дополнительные услуги: {data.get('extras','')}\n💰 Аванс: {data.get('advance','')}\nTelegram: @{username}")
    if ADMIN_CHAT_ID:
        try: await context.bot.send_message(chat_id=ADMIN_CHAT_ID,text=msg)
        except Exception as exc: print(f"Birthday admin notification error: {exc}")
    context.user_data.clear(); context.user_data["lang"]=lang
    done={"ru":"✅ Заявка отправлена администратору!\n\n💰 Для подтверждения бронирования необходим аванс — минимум 100 000 сум.\nАдминистратор FUNLANDIA свяжется с вами.","uz":"✅ Arizangiz administratorga yuborildi!\n\n💰 Bronni tasdiqlash uchun kamida 100 000 so‘m avans kerak.\nAdministrator FUNLANDIA siz bilan bog‘lanadi.","en":"✅ Your request has been sent to the administrator!\n\n💰 A minimum advance payment of 100,000 UZS is required to confirm the booking.\nFUNLANDIA administrator will contact you."}
    await update.effective_message.reply_text(done[lang],reply_markup=menu(lang))

async def birthday_confirm_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang=context.user_data.get("lang","ru"); text=(update.effective_message.text or "").strip()
    edit={"ru":"✏️ Изменить","uz":"✏️ O‘zgartirish","en":"✏️ Edit"}; confirm={"ru":"✅ Подтвердить заявку","uz":"✅ Arizani tasdiqlash","en":"✅ Confirm request"}
    if text==edit[lang]:
        context.user_data["birthday_step"]=1; context.user_data["birthday"]={}
        await update.effective_message.reply_text({"ru":"Начнём заявку заново. 🎂\n\nКак зовут именинника?","uz":"Arizani boshidan boshlaymiz. 🎂\n\nTug‘ilgan kun egasining ismi nima?","en":"Let’s start the request again. 🎂\n\nWhat is the birthday child’s name?"}[lang]); return True
    if text==confirm[lang]: await finish_birthday(update,context); return True
    return False

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or "").strip()
    lang = context.user_data.get("lang", "ru")

    # Telegram/user input can contain different Unicode apostrophe characters.
    # Normalize only for menu matching; displayed texts stay unchanged.
    text_match = (text.replace("’", "'").replace("‘", "'").replace("ʻ", "'").replace("ʼ", "'")
                  .replace("`", "'"))

    if text in ("🇺🇿 O‘zbekcha", "UZ O‘zbekcha"):
        return await uz_start(update, context)
    if text == "🇬🇧 English":
        context.args = ["en"]
        return await start(update, context)
    if text == "🇷🇺 Русский":
        context.args = ["ru"]
        return await start(update, context)

    if text in ("🔙 Назад", "🔙 Orqaga", "🔙 Back"):
        context.user_data.pop("birthday_step", None)
        context.user_data.pop("birthday", None)
        return await update.effective_message.reply_text(
            "Главное меню:" if lang == "ru" else ("Asosiy menyu:" if lang == "uz" else "Main menu:" ),
            reply_markup=menu(lang)
        )

    if text in ("📸 ФОТО-ГИД", "📸 FOTO-GID", "📸 PHOTO GUIDE"):
        return await funlandia(update, lang)

    if text in ("🎁 Акция месяца", "🎁 Aksiya oyi", "🎁 Promotion"):
        return await september_promo(update, context, lang)

    if text in ("🤖 Авто-секретарь", "🤖 Avto-kotib", "🤖 Auto Secretary"):
        return await secretary(update, context)

    if text in ("🎟️ Цены", "🎟️ Narxlar", "🎟️ Prices"):
        return await prices(update, lang)
    if text in ("🎂 День рождения", "🎂 Tug‘ilgan kun", "🎂 Birthday"):
        return await birthday_gallery(update, lang)
    if text in ("🎉 Забронировать день рождения", "🎉 Tug‘ilgan kunni bron qilish", "🎉 Book a Birthday"):
        return await birthday_gallery(update, lang)
    if text in ("📝 Забронировать день рождения", "📝 Tug‘ilgan kunni bron qilish", "📝 Book a Birthday"):
        return await birthday(update, context)
    if text in ("🎠 Развлечения", "🎠 Ko‘ngilochar", "🎠 Attractions"):
        return await attractions(update, lang)
    if text in ("📍 Адрес", "📍 Manzil", "📍 Address"):
        return await simple(update, lang, "address")
    if text in ("🕐 Время работы", "🕐 Ish vaqti", "🕐 Opening Hours"):
        return await hours(update, lang)
    if text in ("📞 Контакт", "📞 Kontakt", "📞 Контакты", "📞 Aloqa", "📞 Contact"):
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
        "🪢 Kanat yo‘li": "ninja",
        "🚪 FUNLANDIA Entrance": "entrance",
        "🎟️ Cashier": "cashier",
        "🤸 Trampolines": "trampoline",
        "🛝 Kids Playground": "playground",
        "🎠 Carousels": "carousel",
        "🎮 Arcade Games": "arcade",
        "🏎️ Bumper Cars": "autodrome",
        "🪢 Rope Course": "ninja",
        "🎈 Зона №1": "birthday1",
        "🎈 Зона №2": "birthday2",
        "🎈 Зона №3": "birthday3",
        "🎈 Zona №1": "birthday1",
        "🎈 Zona №2": "birthday2",
        "🎈 Zona №3": "birthday3",
        "🎈 Zone №1": "birthday1",
        "🎈 Zone №2": "birthday2",
        "🎈 Zone №3": "birthday3",
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
    """Telegram Business secretary.

    Business messages can use inline keyboards, but Business callback updates
    are not exposed by the current python-telegram-bot Bot API layer.
    Therefore the language buttons use direct Telegram bot links.
    This is reliable: tapping a language immediately opens the main FUNLANDIA
    bot in that language.
    """
    message = update.effective_message
    if not message:
        return

    # Secretary must greet only once per Business chat.
    # Without this guard it answers every incoming message (including "ok"
    # after a completed booking) and starts the language prompt again.
    chat_key = f"business_secretary_seen:{getattr(message, 'chat_id', None)}"
    if context.bot_data.get(chat_key):
        return
    context.bot_data[chat_key] = True

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🇷🇺 Русский",
                url="https://t.me/Funlandiauzbot?start=ru"
            ),
            InlineKeyboardButton("🇺🇿 O‘zbekcha", url="https://t.me/Funlandiauzbot?start=uz"),
            InlineKeyboardButton("🇬🇧 English", url="https://t.me/Funlandiauzbot?start=en"),
        ]
    ])

    await message.reply_text(
        "👋 Здравствуйте! Выберите язык / Tilni tanlang:\n\n"
        "После выбора откроется бот FUNLANDIA на выбранном языке. / After selection, FUNLANDIA will open in your language.",
        reply_markup=keyboard,
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


    # Normal bot chats.
    app.add_handler(MessageHandler(filters.PHOTO, receive_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))
    app.add_error_handler(error_handler)

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
