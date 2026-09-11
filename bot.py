import os
import json
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

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
        return ReplyKeyboardMarkup([
            ["📸 FOTO-GID", "🎟️ Narxlar"],
            ["🤖 Avto-kotib", "🎁 Aksiya oyi"],
            ["🎠 Ko‘ngilochar"],
            ["📍 Manzil"],
            ["🎉 Tug‘ilgan kunni bron qilish"],
            ["🕐 Ish vaqti", "📞 Kontakt"],
            ["📸 Instagram", "📱 Telegram"],
            ["🇷🇺 Русский"],
        ], resize_keyboard=True)
    return ReplyKeyboardMarkup([
        ["📸 ФОТО-ГИД", "🎟️ Цены"],
        ["🤖 Авто-секретарь", "🎁 Акция месяца"],
        ["🎠 Развлечения"],
        ["📍 Адрес"],
        ["🎉 Забронировать день рождения"],
        ["🕐 Время работы", "📞 Контакт"],
        ["📸 Instagram", "📱 Telegram"],
        ["🇺🇿 O‘zbekcha"],
    ], resize_keyboard=True)

def funlandia_menu(lang="ru"):
    if lang == "uz":
        return ReplyKeyboardMarkup([
            ["🚪 FUNLANDIA kirish", "🎟️ Kassa"],
            ["🤸 Batutlar", "🛝 Bolalar maydonchasi"],
            ["🎠 Karusellar", "🎮 O'yin avtomatlari"],
            ["🏎️ Avtodrom", "🪢 Kanat yo‘li"],
            ["🔙 Orqaga"],
        ], resize_keyboard=True)
    return ReplyKeyboardMarkup([
        ["🚪 Вход в FUNLANDIA", "🎟️ Касса"],
        ["🤸 Батуты", "🛝 Детская площадка"],
        ["🎠 Карусели", "🎮 Игровые автоматы"],
        ["🏎️ Автодром", "🪢 Канатная дорога"],
        ["🔙 Назад"],
    ], resize_keyboard=True)

def birthday_menu(lang="ru"):
    if lang == "uz":
        return ReplyKeyboardMarkup([
            ["🎈 Zona №1", "🎈 Zona №2"],
            ["🎈 Zona №3"],
            ["📝 Tug‘ilgan kunni bron qilish"],
            ["🔙 Orqaga"],
        ], resize_keyboard=True)
    return ReplyKeyboardMarkup([
        ["🎈 Зона №1", "🎈 Зона №2"],
        ["🎈 Зона №3"],
        ["📝 Забронировать день рождения"],
        ["🔙 Назад"],
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
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
    context.user_data.clear()
    context.user_data["lang"] = "uz"
    await update.message.reply_text(
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
    await update.message.reply_text(text, reply_markup=menu(lang))


async def secretary_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "ru")
    question = (update.message.text or "").strip().lower()

    price_words = ("цен", "стоим", "сколько", "price", "narx", "so'm", "сум")
    birthday_words = ("день рождения", "день рожд", "birthday", "tug‘ilgan", "tugilgan", "брон", "забронировать")
    hours_words = ("график", "время работы", "работаете", "открыт", "закрыт", "иш ваqти", "ish vaqti", "когда работает")
    monday_words = ("понедель", "санитар", "санитарный", "dushanba", "sanitariya")
    address_words = ("адрес", "где находит", "где вы", "манзил", "manzil")
    phone_words = ("телефон", "номер", "позвон", "контакт", "телеграм", "telegram", "instagram", "инстаграм")
    playground_age_words = ("возраст площадки", "возраст детской площадки", "сколько лет на площадку", "с какого возраста на площадку", "площадка с какого возраста",
                            "yosh", "maydoncha necha yosh", "maydonchaga necha yoshdan", "bolalar maydonchasi yosh")
    trampoline_age_words = ("возраст батута", "возраст батут", "с какого возраста батут", "батут с какого возраста", "на батут с какого возраста",
                            "batut necha yosh", "batutga necha yoshdan", "batut yoshi")
    age_general_words = ("возраст", "сколько лет", "с какого возраста", "неполный год", "1 год", "7 лет", "16 лет", "yoshdan", "necha yosh")

    if any(word in question for word in price_words):
        return await prices(update, lang)

    if any(word in question for word in playground_age_words):
        text = (
            "🛝 BOLALAR MAYDONCHASI\n\n"
            "👶 1 yoshgacha — bepul.\n"
            "👧 1 yoshdan 16 yoshgacha — kirish pullik.\n"
            "🎉 Bolalar xavfsizlik qoidalariga rioya qilishlari kerak."
            if lang == "uz" else
            "🛝 ДЕТСКАЯ ПЛОЩАДКА\n\n"
            "👶 До 1 года — бесплатно.\n"
            "👧 От 1 года до 16 лет — вход платный.\n"
            "🎉 Дети должны соблюдать правила безопасности."
        )
        return await update.message.reply_text(text, reply_markup=menu(lang))

    if any(word in question for word in trampoline_age_words):
        text = (
            "🤸 БАТУТ ЗОНАСИ\n\n"
            "👧 Батут зонасига 7 yoshdan boshlab bolalar qo‘yiladi.\n"
            "👨‍👩‍👧 7 yoshdan boshlab bola ota-ona yoki katta yoshli hamroh nazoratida bo‘lishi kerak."
            if lang == "uz" else
            "🤸 БАТУТНАЯ ЗОНА\n\n"
            "👧 На батутную зону допускаются дети от 7 лет.\n"
            "👨‍👩‍👧 Ребёнок должен находиться под присмотром родителей или сопровождающего взрослого."
        )
        return await update.message.reply_text(text, reply_markup=menu(lang))

    if any(word in question for word in age_general_words):
        text = (
            "👶 1 yoshgacha — bolalar maydonchasiga kirish bepul.\n"
            "🛝 1 yoshdan 16 yoshgacha — bolalar maydonchasiga kirish pullik.\n"
            "🤸 Batut zonasi — 7 yoshdan boshlab va ota-ona yoki katta yoshli hamroh nazoratida."
            if lang == "uz" else
            "👶 До 1 года — детская площадка бесплатно.\n"
            "🛝 От 1 года до 16 лет — вход на детскую площадку платный.\n"
            "🤸 Батутная зона — с 7 лет и под присмотром родителей или сопровождающего взрослого."
        )
        return await update.message.reply_text(text, reply_markup=menu(lang))

    if any(word in question for word in birthday_words):
        return await birthday_gallery(update, lang)

    if any(word in question for word in monday_words):
        text = (
            "🧹 Har dushanba — 14:00 gacha sanitariya kuni.\n"
            "🎉 Sizni 14:00 dan 22:00 gacha kutamiz."
            if lang == "uz" else
            "🧹 Каждый понедельник — санитарный день до 14:00.\n"
            "🎉 Ждём вас с 14:00 до 22:00."
        )
        return await update.message.reply_text(text, reply_markup=menu(lang))

    if any(word in question for word in hours_words):
        return await hours(update, lang)

    if any(word in question for word in address_words):
        return await simple(update, lang, "address")

    if any(word in question for word in phone_words):
        return await contacts(update, lang)

    # Anything outside the known FAQ is passed to the administrator.
    username = update.effective_user.username
    display_name = update.effective_user.full_name or "Без имени"
    user_ref = f"@{username}" if username else "без username"
    admin_text = (
        "🤖 АВТО-СЕКРЕТАРЬ — НОВЫЙ СЛОЖНЫЙ ВОПРОС\n\n"
        f"Клиент: {display_name}\n"
        f"Telegram: {user_ref}\n"
        f"Язык: {'UZ' if lang == 'uz' else 'RU'}\n\n"
        f"Вопрос:\n{update.message.text}"
    )

    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)
        except Exception as exc:
            print(f"Admin notification error: {exc}")

    await update.message.reply_text(
        "Savolingizni administratorga yubordim. Tez orada siz bilan bog‘lanishadi."
        if lang == "uz" else
        "Я передал ваш вопрос администратору FUNLANDIA. Вам ответят в ближайшее время.",
        reply_markup=menu(lang)
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
    if kind == "instagram":
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

async def funlandia(update: Update, lang):
    text = "🎡 FUNLANDIA\n\nTanlang:" if lang == "uz" else "🎡 FUNLANDIA\n\nВыберите раздел:"
    await update.message.reply_text(text, reply_markup=funlandia_menu(lang))

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
    await update.message.reply_text(text, reply_markup=menu(lang))

async def september_promo(update: Update, context: ContextTypes.DEFAULT_TYPE, lang):
    key = "promotion"
    photos = load_photos()
    file_ids = normalize_photo_list(photos.get(key))

    if file_ids:
        title = "🎁 АКЦИЯ МЕСЯЦА" if lang == "ru" else "🎁 OY AKSIYASI"
        for index, file_id in enumerate(file_ids):
            await update.message.reply_photo(
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
        await update.message.reply_text(text, reply_markup=menu(lang))


async def birthday_gallery(update: Update, lang):
    text = (
        "🎂 TUG‘ILGAN KUN FUNLANDIA'DA\n\n"
        "🎈 Bayram zonasi fotosuratini tanlang yoki bron qiling:"
        if lang == "uz" else
        "🎂 ДЕНЬ РОЖДЕНИЯ В FUNLANDIA\n\n"
        "🎈 Выберите зону, чтобы посмотреть фотографии, или сразу оформите бронь:"
    )
    await update.message.reply_text(text, reply_markup=birthday_menu(lang))

async def send_photo_key(update: Update, context: ContextTypes.DEFAULT_TYPE, key):
    lang = context.user_data.get("lang", "ru")
    photos = load_photos()
    file_ids = normalize_photo_list(photos.get(key))
    title = PHOTO_TITLES_UZ.get(key, key) if lang == "uz" else PHOTO_KEYS.get(key, key)
    if not file_ids:
        await update.message.reply_text(
            f"📸 {title}\n\nФото пока не подключено. Администратор добавит его после загрузки."
            if lang == "uz" else
            f"📸 {title}\n\nФото пока не подключено. Мы добавим его на следующем этапе.",
            reply_markup=funlandia_menu(lang) if key not in ("birthday1", "birthday2", "birthday3") else birthday_menu(lang)
        )
        return
    reply_markup = funlandia_menu(lang) if key not in ("birthday1", "birthday2", "birthday3") else birthday_menu(lang)
    for index, file_id in enumerate(file_ids):
        await update.message.reply_photo(
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
        await update.message.reply_text(
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
        await update.message.reply_text(
            "📸 Раздел: 🎁 Акция месяца\n\n"
            "Старая акция очищена.\n\n"
            "Теперь отправьте 2 новые фотографии акции подряд.\n"
            "После второй фотографии отправьте /donephoto."
        )
    else:
        await update.message.reply_text(
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

    await update.message.reply_text(
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
        await update.message.reply_text("ℹ️ Сейчас нет активной загрузки фотографий.")
        return
    photos = load_photos()
    count = len(normalize_photo_list(photos.get(key)))
    await update.message.reply_text(
        f"✅ Готово! Для «{PHOTO_KEYS[key]}» сохранено: {count} фото.\n\n"
        "Теперь можно выбрать следующий раздел через /setphoto key."
    )

async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    key = context.user_data.get("setting_photo")
    if not key:
        return
    photo = update.message.photo[-1]
    photos = load_photos()
    file_ids = normalize_photo_list(photos.get(key))
    file_ids.append(photo.file_id)
    photos[key] = file_ids
    save_photos(photos)
    await update.message.reply_text(
        f"✅ Фото №{len(file_ids)} сохранено для: {PHOTO_KEYS[key]}\n"
        "Можешь отправить следующее фото. Когда закончишь — /donephoto"
    )

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

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    lang = context.user_data.get("lang", "ru")

    if text in ("🇺🇿 O‘zbekcha", "UZ O‘zbekcha"):
        return await uz_start(update, context)
    if text == "🇷🇺 Русский":
        return await start(update, context)

    if text in ("🔙 Назад", "🔙 Orqaga"):
        context.user_data.pop("birthday_step", None)
        context.user_data.pop("birthday", None)
        return await update.message.reply_text(
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

    if context.user_data.get("birthday_step") == 6:
        return await finish_birthday(update, context)
    if context.user_data.get("birthday_step"):
        return await birthday_form(update, context)

    return await secretary_answer(update, context)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    # Keep the bot running even if one user message causes an exception.
    print(f"Bot error: {context.error}")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setphoto", setphoto))
    app.add_handler(CommandHandler("setpromo", setpromo))
    app.add_handler(CommandHandler("donephoto", donephoto))

    # Telegram Business / Secretary Mode.
    # Messages arriving through a connected Business account are delivered
    # as BUSINESS_MESSAGE updates. We route them through the same handler
    # so the existing auto-secretary can answer clients on behalf of FUNLANDIA.
    app.add_handler(
        MessageHandler(
            filters.UpdateType.BUSINESS_MESSAGE & filters.PHOTO,
            receive_photo,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.UpdateType.BUSINESS_MESSAGE & filters.TEXT,
            handler,
        )
    )

    # Normal bot chats.
    app.add_handler(MessageHandler(filters.PHOTO, receive_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))
    app.add_error_handler(error_handler)

    app.run_polling()

if __name__ == "__main__":
    main()
