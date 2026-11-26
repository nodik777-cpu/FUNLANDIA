import os
import json
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, BusinessConnectionHandler, filters
from ai_assistant import answer_customer

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DB_POOL = None

ADMIN_PHONE = "+998 93 381 00 55"
CALL_CENTER = "+998 55 512-73-37"
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

def detect_message_language(text: str, fallback: str = "ru") -> str:
    """Lightweight language detection for RU, Uzbek (Latin/Cyrillic), and EN."""
    import re
    value = (text or "").lower()
    if re.search(r"[а-яё]", value):
        uz_cyrillic = ("салом", "рахмат", "нархи", "қанча", "болалар",
                       "майдонча", "батут", "иш вақти", "манзил", "борми")
        return "uz" if any(token in value for token in uz_cyrillic) else "ru"
    uzbek_words = (
        "salom", "assalomu", "rahmat", "narxi", "narxlar", "qancha",
        "bolalar", "maydoncha", "batut", "ish vaqti", "manzil",
        "bormi", "necha", "so'm", "so‘m", "tug'ilgan", "tug‘ilgan",
        "iltimos", "mumkinmi", "qayerda", "ochiqmisiz"
    )
    if any(token in value for token in uzbek_words):
        return "uz"
    return fallback if fallback in ("ru", "uz", "en") else "en"


def menu(lang="ru", admin=False):
    # Full Telegram menu plus a separate Mini App launcher at the top.
    app_labels = {
        "ru": "🎡 Открыть графическое меню FUNLANDIA",
        "uz": "🎡 FUNLANDIA grafik menyusini ochish",
        "en": "🎡 Open FUNLANDIA visual menu",
    }
    if lang == "uz":
        rows = [
            ["💬 Savol berish", "📸 FOTO-GID"],
            ["🎉 Tug‘ilgan kunni bron qilish", "🎟️ Narxlar"],
            ["🎠 Ko‘ngilochar", "🎁 Aksiya oyi"],
            ["🕐 Ish vaqti", "📍 Kontaktlar"],
        ]
    elif lang == "en":
        rows = [
            ["💬 Ask a question", "📸 PHOTO GUIDE"],
            ["🎉 Book a Birthday", "🎟️ Prices"],
            ["🎠 Attractions", "🎁 Promotion"],
            ["🕐 Opening Hours", "📍 Contacts"],
        ]
    else:
        rows = [
            ["💬 Задать вопрос", "📸 ФОТО-ГИД"],
            ["🎉 Забронировать день рождения", "🎟️ Цены"],
            ["🎠 Развлечения", "🎁 Акция месяца"],
            ["🕐 Время работы", "📍 Контакты"],
        ]
    keyboard = [[
        KeyboardButton(
            app_labels.get(lang, app_labels["ru"]),
            web_app=WebAppInfo(url="https://funlandia-mini-app-test.up.railway.app/")
        )
    ]]
    keyboard.extend(two_col(rows))
    if admin:
        keyboard.append([KeyboardButton("🛠 Панель администратора", web_app=WebAppInfo(url="https://funlandia-mini-app-test.up.railway.app/admin"))])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

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
    start_arg = context.args[0].lower() if context.args else "ru"
    action = start_arg if start_arg in ("question", "birthday", "photos", "promotion") else None
    lang = start_arg if start_arg in ("ru", "uz", "en") else "ru"
    context.user_data.clear()
    context.user_data["lang"] = lang

    # Deep links from the Mini App must open the matching bot section,
    # not fall through to the generic welcome screen.
    if action == "question":
        prompts = {
            "ru": "💬 Напишите ваш вопрос — я с радостью помогу!",
            "uz": "💬 Savolingizni yozing — mamnuniyat bilan yordam beraman!",
            "en": "💬 Type your question — I’ll be happy to help!",
        }
        await update.effective_message.reply_text(prompts[lang], reply_markup=menu(lang))
        return
    if action == "birthday":
        return await birthday(update, context)
    if action == "photos":
        return await funlandia(update, lang)
    if action == "promotion":
        return await september_promo(update, context, lang)

    messages = {
        "ru": ("🎉 ДОБРО ПОЖАЛОВАТЬ В FUNLANDIA! 🎉\n\nМесто, где дети играют, веселятся и получают яркие эмоции, а родители отдыхают! ❤️\n\n🛝 Лабиринты • 🤸 Батуты • 🎢 Горки • 🎯 Пневмопушки • 🧗 Тарзанка\n\nВыберите интересующий раздел ниже 👇"),
        "uz": ("🎉 FUNLANDIA'GA XUSH KELIBSIZ! 🎉\n\nBu yerda bolalar o‘ynaydi, quvonadi va yorqin taassurotlar oladi, ota-onalar esa maroqli dam oladi! ❤️\n\n🛝 Labirintlar • 🤸 Batutlar • 🎢 Tepaliklar • 🎯 Pnevmatik to‘plar • 🧗 Tarzanka\n\nKerakli bo‘limni tanlang 👇"),
        "en": ("🎉 WELCOME TO FUNLANDIA! 🎉\n\nA place where children play, have fun and enjoy bright emotions, while parents relax! ❤️\n\n🛝 Labyrinths • 🤸 Trampolines • 🎢 Slides • 🎯 Air Cannons • 🧗 Rope Adventure\n\nChoose a section below 👇")
    }
    is_admin_user = bool(update.effective_user and ADMIN_CHAT_ID and str(update.effective_user.id) == str(ADMIN_CHAT_ID))
    await update.effective_message.reply_text(messages[lang], reply_markup=menu(lang, admin=is_admin_user))


async def uz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = ["uz"]
    return await start(update, context)


async def secretary_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Friendly customer assistant: greet first, then answer with verified facts or AI."""
    raw = (update.effective_message.text or "").strip()
    fallback_lang = context.user_data.get("lang", "ru")
    telegram_lang = getattr(update.effective_user, "language_code", None)
    if fallback_lang == "ru" and telegram_lang in ("uz", "en"):
        fallback_lang = telegram_lang
    # Keep the conversation language for short replies such as "1 soat".
    import re
    short_followup = len(raw.split()) <= 3 and not re.search(
        r"\b(hello|hi|salom|assalomu|rahmat|narxi|qancha|bolalar|maydoncha|batut|"
        r"bormi|bor-mi|necha|yosh|soat|iltimos|mumkinmi|"
        r"привет|здравствуйте|сколько|цена|ребён|ребен|площадк|батут|"
        r"нян\w*|nanny|babysitter|enaga|борми|бор\w*|"
        r"hours?|час|лет|года)\b", raw.lower()
    )
    lang = fallback_lang if short_followup else detect_message_language(raw, fallback_lang)
    context.user_data["lang"] = lang
    question = raw.lower()

    # Nanny availability is checked in person at the cashier; never answer that
    # the service is unavailable because the bot has no live staffing data.
    import re
    if re.search(r"\b(нян\w*|nanny|babysitter|enaga|qarovul)\b", question, re.IGNORECASE):
        nanny_reply = {
            "ru": "По поводу услуги няни, пожалуйста, уточните информацию на кассе. Если свободная няня есть, сотрудники кассы подскажут и предоставят её.",
            "uz": "Enaga xizmati bo‘yicha, iltimos, kassadan ma’lumot oling. Agar bo‘sh enaga bo‘lsa, kassa xodimlari sizga yordam berishadi.",
            "en": "Please ask at the cashier about the nanny service. If a nanny is available, the cashier staff will let you know and arrange it.",
        }
        await update.effective_message.reply_text(nanny_reply[lang])
        return

    # Remember a child's age mentioned earlier and pass it explicitly to Gemini.
    age_match = (
        re.search(r"\b(\d{1,2})\s*(?:лет|года|год|месяц(?:а|ев)?|мес)\b", question)
        or re.search(r"\b(\d{1,2})\s*(?:yosh|years? old|months? old)\b", question)
    )
    if age_match:
        context.user_data["child_age"] = age_match.group(1)
    known_age = context.user_data.get("child_age")
    ai_question = (
        f"Known context from this conversation: the child's age is {known_age}. "
        f"Keep this age in mind when recommending zones and attractions. "
        f"Current customer message: {raw}"
        if known_age else raw
    )

    # Friendly greetings at any later point.
    greetings = (
        "привет", "здравствуйте", "здравствуй", "добрый день",
        "добрый вечер", "доброе утро", "салом", "салом алейкум",
        "ассалому алейкум", "алейкум ассалом", "hello", "hi",
        "salom", "assalomu alaykum"
    )
    if any(word in question for word in greetings):
        greeting = {
            "ru": "👋 Здравствуйте! 😊 Чем могу помочь?",
            "uz": "👋 Assalomu alaykum! 😊 Sizga qanday yordam bera olaman?",
            "en": "👋 Hello! 😊 How can I help you?",
        }
        await update.effective_message.reply_text(greeting[lang])
        return

    # All free-form customer questions go to Gemini. Only explicit menu buttons
    # and booking-form states are handled earlier in handler().
    
    # Unknown questions are answered by the AI assistant using the verified
    # FUNLANDIA facts in ai_assistant.py. Availability and booking confirmation
    # are always escalated to a human administrator.
    history = context.user_data.setdefault("ai_history", [])
    answer, handoff = await answer_customer(ai_question, lang, history)

    if handoff:
        user = update.effective_user
        name = user.full_name or "Без имени"
        username = user.username or "без username"
        sent_to_admin = False
        if ADMIN_CHAT_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=(
                        "📩 ВОПРОС КЛИЕНТА — НУЖЕН АДМИНИСТРАТОР\n\n"
                        f"👤 {name}\n"
                        f"📱 @{username}\n"
                        f"🌐 Язык: {lang}\n\n"
                        f"❓ {raw}"
                    ),
                )
                sent_to_admin = True
            except Exception as exc:
                print(f"AI admin notification error: {exc}")
        if sent_to_admin:
            reply = {
                "ru": "Этот вопрос лучше уточнить у администратора. Я передал ему ваше сообщение.",
                "uz": "Bu savolni administrator bilan aniqlashtirish kerak. Xabaringizni unga yubordim.",
                "en": "An administrator should confirm this. I have forwarded your message.",
            }
        else:
            reply = {
                "ru": "Этот вопрос нужно уточнить у администратора. Позвоните, пожалуйста: +998 55 512-73-37.",
                "uz": "Bu savolni administrator bilan aniqlashtirish kerak. Iltimos, qo‘ng‘iroq qiling: +998 55 512-73-37.",
                "en": "An administrator needs to confirm this. Please call +998 55 512-73-37.",
            }
        await update.effective_message.reply_text(reply.get(lang, reply["ru"]))
        return

    if not answer:
        fallback = {
            "ru": "Извините, онлайн-консультант временно недоступен. Позвоните нам: +998 55 512-73-37.",
            "uz": "Kechirasiz, onlayn maslahatchi vaqtincha ishlamayapti. Bizga qo‘ng‘iroq qiling: +998 55 512-73-37.",
            "en": "Sorry, the online assistant is temporarily unavailable. Please call +998 55 512-73-37.",
        }
        await update.effective_message.reply_text(fallback.get(lang, fallback["ru"]))
        return

    history.extend([
        {"role": "user", "content": raw},
        {"role": "assistant", "content": answer},
    ])
    del history[:-12]
    await update.effective_message.reply_text(answer)

async def prices(update: Update, lang):
    if lang == "uz":
        text = ("🎟️ FUNLANDIA NARXLARI\n\n🛝 BOLALAR ZONASI\n🏰 Labirintlar\n🎪 Puflanadigan batutlar\n🎢 Tepaliklar\n🎯 Pnevmatik to‘plar\n\n💰 1 soat — 80 000 so‘m\n💰 2 soat — 90 000 so‘m\n♾️ Cheksiz — 100 000 so‘m\n\n👶 1 yoshgacha bo‘lgan bolalar — bepul.\n👧👦 1 yoshdan 16 yoshgacha — kirish pullik.\n\n🤸 BATUT ZONASI\n💰 1 soat — 80 000 so‘m\n💰 2 soat — 90 000 so‘m\n♾️ Cheksiz — 100 000 so‘m\n⛔ 7 yoshgacha batut zonasiga kirish mumkin emas. 7 yoshdan boshlab — ota-ona yoki katta yoshli hamroh nazoratida.\n\n🎉 IKKALA ZONA — 120 000 so‘m\n♾️ Ikkala zonaga cheksiz kirish!")
    elif lang == "en":
        text = ("🎟️ FUNLANDIA PRICES\n\n🛝 KIDS ZONE\n🏰 Labyrinths\n🎪 Inflatable trampolines\n🎢 Slides\n🎯 Air cannons\n\n💰 1 hour — 80,000 UZS\n💰 2 hours — 90,000 UZS\n♾️ Unlimited — 100,000 UZS\n\n👶 Children under 1 year old — free entry.\n👧👦 Children from 1 to 16 years — paid entry.\n\n🤸 TRAMPOLINE ZONE\n💰 1 hour — 80,000 UZS\n💰 2 hours — 90,000 UZS\n♾️ Unlimited — 100,000 UZS\n⛔ Children under 7 are not allowed in the trampoline zone. From age 7, only under parent/adult supervision.\n\n🎉 BOTH ZONES — 120,000 UZS\n♾️ Unlimited access to both zones!")
    else:
        text = ("🎟️ ЦЕНЫ FUNLANDIA\n\n🛝 ДЕТСКАЯ ЗОНА\n🏰 Лабиринты\n🎪 Надувные батуты\n🎢 Горки\n🎯 Пневмопушки\n\n💰 1 час — 80 000 сум\n💰 2 часа — 90 000 сум\n♾️ Безлимит — 100 000 сум\n\n👶 Детям до 1 года — бесплатно.\n👧👦 Детям от 1 года до 16 лет — вход платный.\n\n🤸 БАТУТНАЯ ЗОНА\n💰 1 час — 80 000 сум\n💰 2 часа — 90 000 сум\n♾️ Безлимит — 100 000 сум\n⛔ До 7 лет вход в батутную зону запрещён. С 7 лет — только под присмотром родителей или взрослого.\n\n🎉 ДВЕ ЗОНЫ — 120 000 сум\n♾️ Безлимитное посещение обеих зон!")
    await update.effective_message.reply_text(text, reply_markup=menu(lang))


async def hours(update: Update, lang):
    texts={"ru":"🕐 ВРЕМЯ РАБОТЫ FUNLANDIA\n\n🗓 Вторник – воскресенье: 10:00–22:00\n\n🧹 Каждый понедельник — санитарный день до 14:00. С 14:00 до 22:00 мы ждём вас!", "uz":"🕐 FUNLANDIA ISH VAQTI\n\n🗓 Seshanba – yakshanba: 10:00–22:00\n\n🧹 Har dushanba — 14:00 gacha sanitariya kuni. 14:00 dan 22:00 gacha sizni kutamiz!", "en":"🕐 FUNLANDIA OPENING HOURS\n\n🗓 Tuesday – Sunday: 10:00–22:00\n\n🧹 Every Monday is a sanitation day until 14:00. We look forward to seeing you from 14:00 to 22:00!"}
    await update.effective_message.reply_text(texts.get(lang,texts["ru"]), reply_markup=menu(lang))


async def contacts(update: Update, lang):
    texts = {
        "ru": (
            "📍 КОНТАКТЫ FUNLANDIA\n\n"
            "📞 Телефон: +998 93 381 00 55\n"
            "☎️ Колл-центр: +998 55 512-73-37\n\n"
            "📱 Telegram: @Funlandia_Tashkent\n"
            "📸 Instagram: @funlandiauz\n\n"
            f"📍 Адрес: {ADDRESS}"
        ),
        "uz": (
            "📍 FUNLANDIA ALOQA\n\n"
            "📞 Telefon: +998 93 381 00 55\n"
            "☎️ Call-markaz: +998 55 512-73-37\n\n"
            "📱 Telegram: @Funlandia_Tashkent\n"
            "📸 Instagram: @funlandiauz\n\n"
            f"📍 Manzil: {ADDRESS}"
        ),
        "en": (
            "📍 FUNLANDIA CONTACTS\n\n"
            "📞 Phone: +998 93 381 00 55\n"
            "☎️ Call center: +998 55 512-73-37\n\n"
            "📱 Telegram: @Funlandia_Tashkent\n"
            "📸 Instagram: @funlandiauz\n\n"
            f"📍 Address: {ADDRESS}"
        ),
    }
    buttons = [
        [
            InlineKeyboardButton("📱 Telegram", url=TELEGRAM),
            InlineKeyboardButton("📸 Instagram", url=INSTAGRAM),
        ],
        [
            InlineKeyboardButton(
                {"ru": "🗺️ Открыть локацию на карте", "uz": "🗺️ Xaritada ochish", "en": "🗺️ Open map"}[lang],
                url="https://yandex.uz/maps/org/funlandia/179053879477/?indoorLevel=1&ll=69.354446%2C41.352979&mode=search&sctx=ZAAAAAgBEAAaKAoSCcueBDbnUVFAERGPxMvTp0RAEhIJ%2B1xtxf6y0D8Rb0p5rYTuwD8iBgABAgMEBSgKOABAnp8GSAFqAnV6nQHNzMw9oAEAqAEAvQHPmqmMggIJZnVubGFuZGlhigIAkgIMZGVza3RvcC1tYXBz&sll=69.354446%2C41.352979&sspn=0.005647%2C0.002861&text=funlandia&utm_source=share&z=17",
            ),
        ],
    ]
    await update.effective_message.reply_text(
        texts.get(lang, texts["ru"]),
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def direct_contact(update: Update, lang, kind):
    if kind == "call":
        texts={"ru":"☎️ КОЛЛ-ЦЕНТР\n\n📞 +998 55 512-73-37","uz":"☎️ CALL-MARKAZ\n\n📞 +998 55 512-73-37","en":"☎️ CALL CENTER\n\n📞 +998 55 512-73-37"}
    else:
        texts={"ru":"📞 КОНТАКТ\n\n📞 +998933810055","uz":"📞 KONTAKT\n\n📞 +998933810055","en":"📞 CONTACT\n\n📞 +998933810055"}
    await update.effective_message.reply_text(texts.get(lang,texts["ru"]), reply_markup=menu(lang))

async def simple(update: Update, lang, kind):
    if kind == "address":
        ending={"ru":"Будем рады видеть вас! 🎉","uz":"Sizni kutamiz! 🎉","en":"We look forward to seeing you! 🎉"}
        text=f"📍 FUNLANDIA\n\n{ADDRESS}\n\n{ending.get(lang,ending['ru'])}"
        map_text={"ru":"🗺️ Открыть на карте","uz":"🗺️ Xaritada ochish","en":"🗺️ Open map"}
        keyboard=InlineKeyboardMarkup([[InlineKeyboardButton(map_text.get(lang,map_text["ru"]),url="https://yandex.uz/maps/org/funlandia/179053879477/?indoorLevel=1&ll=69.354446%2C41.352979&mode=search&sctx=ZAAAAAgBEAAaKAoSCcueBDbnUVFAERGPxMvTp0RAEhIJ%2B1xtxf6y0D8Rb0p5rYTuwD8iBgABAgMEBSgKOABAnp8GSAFqAnV6nQHNzMw9oAEAqAEAvQHPmqmMggIJZnVubGFuZGlhigIAkgIAmgIMZGVza3RvcC1tYXBz&sll=69.354446%2C41.352979&sspn=0.005647%2C0.002861&text=funlandia&utm_source=share&z=17")]])
        await update.effective_message.reply_text(text,reply_markup=keyboard); return
    if kind == "instagram":
        label={"ru":"📸 Instagram FUNLANDIA","uz":"📸 Instagram FUNLANDIA","en":"📸 FUNLANDIA Instagram"}[lang]
        text=f"{label}\n\n{INSTAGRAM}"
    else:
        label={"ru":"📱 Telegram FUNLANDIA","uz":"📱 Telegram FUNLANDIA","en":"📱 FUNLANDIA Telegram"}[lang]
        text=f"{label}\n\n{TELEGRAM}"
    await update.effective_message.reply_text(text,reply_markup=menu(lang))

async def attractions(update: Update, lang):
    texts={"ru":"🎠 НАШИ РАЗВЛЕЧЕНИЯ\n\n🛝 4-этажный лабиринт\n🎪 Надувные батуты\n🤸 Профессиональные батуты\n🎢 Скоростные горки, включая 17-метровую\n🧗 Канатный маршрут и тарзанка\n🎯 Пневмопушки\n🧸 Зона для малышей\n🏖️ Кинетический песок\n🎠 Карусели\n🎮 Игровые автоматы", "uz":"🎠 BIZNING KO‘NGILOCHARLAR\n\n🛝 4 qavatli labirint\n🎪 Puflanadigan batutlar\n🤸 Professional batutlar\n🎢 Tezkor sirpanchiqlar, jumladan 17 metrlik\n🧗 Arqonli yo‘lak va tarzanka\n🎯 Pnevmatik to‘plar\n🧸 Kichkintoylar zonasi\n🏖️ Kinetik qum\n🎠 Karusellar\n🎮 O‘yin avtomatlari", "en":"🎠 OUR ATTRACTIONS\n\n🛝 4-floor labyrinth\n🎪 Inflatable trampolines\n🤸 Professional trampolines\n🎢 Speed slides, including a 17-metre slide\n🧗 Rope course and rope swing\n🎯 Air cannons\n🧸 Toddler zone\n🏖️ Kinetic sand\n🎠 Carousels\n🎮 Arcade games"}
    await update.effective_message.reply_text(texts.get(lang,texts["ru"]), reply_markup=menu(lang))


async def funlandia(update: Update, lang):
    texts={"ru":"🎡 FUNLANDIA\n\nВыберите раздел:","uz":"🎡 FUNLANDIA\n\nTanlang:","en":"🎡 FUNLANDIA\n\nChoose a section:"}
    await update.effective_message.reply_text(texts.get(lang,texts["ru"]), reply_markup=funlandia_menu(lang))


async def birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "ru")
    # The new hybrid flow starts in the Telegram Mini App calendar. Do not
    # start the legacy free-text questionnaire here: it bypasses live slot holds.
    context.user_data.pop("birthday", None)
    context.user_data.pop("birthday_step", None)
    intro = {
        "ru": "🎂 ДЕНЬ РОЖДЕНИЯ В FUNLANDIA\n\n"
              "Выберите зону, дату и свободное время в календаре.\n"
              "После отправки заявка временно занимает выбранное время и поступает администратору. "
              "Бронирование станет подтверждённым только после проверки администратором.\n\n"
              "📅 Нажмите кнопку ниже, чтобы открыть календарь и отправить заявку.",
        "uz": "🎂 FUNLANDIA'DA TUG‘ILGAN KUN\n\n"
              "Kalendar orqali zona, sana va bo‘sh vaqtni tanlang.\n"
              "Ariza yuborilgach, tanlangan vaqt vaqtincha band qilinadi va administratorga yuboriladi. "
              "Bron faqat administrator tekshirganidan keyin tasdiqlanadi.\n\n"
              "📅 Kalendarni ochish va ariza yuborish uchun quyidagi tugmani bosing.",
        "en": "🎂 BIRTHDAY AT FUNLANDIA\n\n"
              "Choose a zone, date and available time in the calendar.\n"
              "After submission, the selected time is temporarily reserved and sent to the administrator. "
              "The booking is confirmed only after the administrator reviews it.\n\n"
              "📅 Tap the button below to open the calendar and submit your request.",
    }
    button = {
        "ru": "📅 Открыть календарь бронирования",
        "uz": "📅 Bron kalendarini ochish",
        "en": "📅 Open booking calendar",
    }
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            button.get(lang, button["ru"]),
            web_app=WebAppInfo(url="https://funlandia-mini-app-test.up.railway.app/booking")
        )
    ]])
    await update.effective_message.reply_text(intro.get(lang, intro["ru"]), reply_markup=keyboard)


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
    lang = context.user_data.get("lang", "ru")
    step = context.user_data.get("birthday_step", 1)
    value = (update.effective_message.text or "").strip()
    data = context.user_data.setdefault("birthday", {})
    fields = {
        "ru": [
            ("name", "🎂 Как зовут именинника?"),
            ("age", "🎈 Сколько лет исполнится имениннику?"),
            ("date", "📅 На какую дату планируете праздник?"),
            ("children", "👧👦 Сколько будет детей?"),
            ("adults", "👨‍👩‍👧‍👦 Сколько будет взрослых?"),
            ("phone", "📞 Оставьте номер телефона для связи:"),
            ("format", "🎉 Какой формат праздника предпочитаете? Опишите, пожалуйста."),
            ("wishes", "💬 Есть ли дополнительные пожелания или особые детали? Если нет, напишите «нет»."),
        ],
        "uz": [
            ("name", "🎂 Tug‘ilgan kun egasining ismi nima?"),
            ("age", "🎈 Tug‘ilgan kun egasi necha yoshga to‘ladi?"),
            ("date", "📅 Bayramni qaysi sanaga rejalashtiryapsiz?"),
            ("children", "👧👦 Nechta bola keladi?"),
            ("adults", "👨‍👩‍👧‍👦 Nechta kattalar keladi?"),
            ("phone", "📞 Bog‘lanish uchun telefon raqamingizni yozing:"),
            ("format", "🎉 Bayramning qaysi formatini xohlaysiz? Iltimos, yozing."),
            ("wishes", "💬 Qo‘shimcha istaklaringiz yoki muhim tafsilotlar bormi? Bo‘lmasa, «yo‘q» deb yozing."),
        ],
        "en": [
            ("name", "🎂 What is the birthday child’s name?"),
            ("age", "🎈 How old will the birthday child be?"),
            ("date", "📅 What date are you planning the celebration?"),
            ("children", "👧👦 How many children will attend?"),
            ("adults", "👨‍👩‍👧‍👦 How many adults will attend?"),
            ("phone", "📞 Please leave a contact phone number:"),
            ("format", "🎉 What kind of celebration would you like? Please describe it."),
            ("wishes", "💬 Any additional wishes or important details? If not, write “no”."),
        ],
    }[lang]
    if not value:
        await update.effective_message.reply_text({
            "ru": "Пожалуйста, напишите ответ.",
            "uz": "Iltimos, javobingizni yozing.",
            "en": "Please enter your answer.",
        }[lang])
        return

    if step < 1 or step > len(fields):
        context.user_data.pop("birthday_step", None)
        return

    key, _ = fields[step - 1]
    data[key] = value
    if step < len(fields):
        context.user_data["birthday_step"] = step + 1
        await update.effective_message.reply_text(fields[step][1])
        return

    context.user_data["birthday_step"] = 9
    if lang == "ru":
        summary = (
            "🎂 ПРОВЕРЬТЕ ЗАЯВКУ НА ДЕНЬ РОЖДЕНИЯ\n\n"
            f"👤 Именинник: {data['name']}\n🎈 Возраст: {data['age']}\n"
            f"📅 Желаемая дата: {data['date']}\n👧👦 Детей: {data['children']}\n"
            f"👨‍👩‍👧‍👦 Взрослых: {data['adults']}\n📞 Телефон: {data['phone']}\n"
            f"🎉 Формат праздника: {data['format']}\n💬 Пожелания: {data['wishes']}\n\n"
            "Нажмите «Подтвердить заявку», чтобы отправить её администратору.\n"
            "Это заявка, а не подтверждение бронирования. Администратор уточнит доступность даты, детали и стоимость."
        )
        kb = [["✅ Подтвердить заявку", "✏️ Изменить"], ["🔙 Назад"]]
    elif lang == "uz":
        summary = (
            "🎂 TUG‘ILGAN KUN ARIZASINI TEKSHIRING\n\n"
            f"👤 Ism: {data['name']}\n🎈 Yosh: {data['age']}\n"
            f"📅 Rejalashtirilgan sana: {data['date']}\n👧👦 Bolalar: {data['children']}\n"
            f"👨‍👩‍👧‍👦 Kattalar: {data['adults']}\n📞 Telefon: {data['phone']}\n"
            f"🎉 Bayram formati: {data['format']}\n💬 Istaklar: {data['wishes']}\n\n"
            "Arizani administratorga yuborish uchun «Arizani tasdiqlash» tugmasini bosing.\n"
            "Bu ariza, bron tasdig‘i emas. Administrator sana mavjudligi, tafsilotlar va narxni aniqlashtiradi."
        )
        kb = [["✅ Arizani tasdiqlash", "✏️ O‘zgartirish"], ["🔙 Orqaga"]]
    else:
        summary = (
            "🎂 CHECK YOUR BIRTHDAY REQUEST\n\n"
            f"👤 Birthday child: {data['name']}\n🎈 Age: {data['age']}\n"
            f"📅 Requested date: {data['date']}\n👧👦 Children: {data['children']}\n"
            f"👨‍👩‍👧‍👦 Adults: {data['adults']}\n📞 Phone: {data['phone']}\n"
            f"🎉 Celebration format: {data['format']}\n💬 Wishes: {data['wishes']}\n\n"
            "Press “Confirm request” to send it to the administrator.\n"
            "This is a request, not a confirmed booking. The administrator will check availability, details and price."
        )
        kb = [["✅ Confirm request", "✏️ Edit"], ["🔙 Back"]]
    await update.effective_message.reply_text(
        summary,
        reply_markup=ReplyKeyboardMarkup(two_col(kb), resize_keyboard=True),
    )


async def finish_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "ru")
    data = context.user_data.get("birthday", {})
    user = update.effective_user
    username = f"@{user.username}" if user.username else "нет username"
    display_name = user.full_name or "Без имени"
    labels = {
        "ru": ("НОВАЯ ЗАЯВКА НА ДЕНЬ РОЖДЕНИЯ", "Именинник", "Возраст", "Желаемая дата",
               "Детей", "Взрослых", "Телефон", "Формат праздника", "Пожелания"),
        "uz": ("YANGI TUG‘ILGAN KUN ARIZASI", "Ism", "Yosh", "Rejalashtirilgan sana",
               "Bolalar", "Kattalar", "Telefon", "Bayram formati", "Istaklar"),
        "en": ("NEW BIRTHDAY REQUEST", "Birthday child", "Age", "Requested date",
               "Children", "Adults", "Phone", "Celebration format", "Wishes"),
    }
    title, name_l, age_l, date_l, children_l, adults_l, phone_l, format_l, wishes_l = labels.get(lang, labels["ru"])
    msg = (
        f"🎂 {title}\n\n"
        f"👤 {name_l}: {data.get('name', '')}\n🎈 {age_l}: {data.get('age', '')}\n"
        f"📅 {date_l}: {data.get('date', '')}\n👧👦 {children_l}: {data.get('children', '')}\n"
        f"👨‍👩‍👧‍👦 {adults_l}: {data.get('adults', '')}\n📞 {phone_l}: {data.get('phone', '')}\n"
        f"🎉 {format_l}: {data.get('format', '')}\n💬 {wishes_l}: {data.get('wishes', '')}\n\n"
        f"👥 Клиент: {display_name} ({username})\n"
        f"🆔 Telegram ID: {user.id}\n"
        "⚠️ Дата не подтверждена. Требуется связаться с клиентом, проверить доступность, согласовать детали, стоимость и аванс."
    )
    saved = False
    try:
        saved = await save_birthday_request(user, data, lang)
        if not saved:
            print("BOOKING_DB_SAVE_SKIPPED: database pool is unavailable", flush=True)
    except Exception as exc:
        print(f"BOOKING_DB_SAVE_ERROR: {type(exc).__name__}: {exc}", flush=True)

    sent = False
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg)
            sent = True
        except Exception as exc:
            print(f"Birthday admin notification error: {exc}")
    context.user_data.pop("birthday_step", None)
    context.user_data.pop("birthday", None)
    context.user_data["lang"] = lang
    replies = {
        "ru": "✅ Ваша заявка отправлена администратору FUNLANDIA.\n\n"
              "📌 Это пока не является подтверждением бронирования. "
              "Администратор уточнит доступность даты, детали праздника, стоимость и аванс.\n"
              "Мы свяжемся с вами.",
        "uz": "✅ Arizangiz FUNLANDIA administratoriga yuborildi.\n\n"
              "📌 Bu hali bron tasdiqlanganini anglatmaydi. "
              "Administrator sana mavjudligi, bayram tafsilotlari, narxi va avansni aniqlashtiradi.\n"
              "Siz bilan bog‘lanamiz.",
        "en": "✅ Your request has been sent to the FUNLANDIA administrator.\n\n"
              "📌 This is not a booking confirmation yet. "
              "The administrator will check the date, celebration details, price and advance payment.\n"
              "We will contact you.",
    }
    if not sent:
        replies = {
            "ru": "⚠️ Заявка заполнена, но не отправлена администратору: канал администратора пока не настроен. Позвоните, пожалуйста: +998 55 512-73-37 и сообщите данные заявки.",
            "uz": "⚠️ Ariza to‘ldirildi, lekin administrator kanali sozlanmagani uchun yuborilmadi. Iltimos, +998 55 512-73-37 raqamiga qo‘ng‘iroq qilib, ariza ma’lumotlarini ayting.",
            "en": "⚠️ Your request is complete but was not sent because the administrator channel is not configured. Please call +998 55 512-73-37 and provide your request details.",
        }
    await update.effective_message.reply_text(replies.get(lang, replies["ru"]), reply_markup=menu(lang))


async def birthday_confirm_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "ru")
    text = (update.effective_message.text or "").strip()
    edit = {"ru": "✏️ Изменить", "uz": "✏️ O‘zgartirish", "en": "✏️ Edit"}
    confirm = {"ru": "✅ Подтвердить заявку", "uz": "✅ Arizani tasdiqlash", "en": "✅ Confirm request"}
    if text == edit[lang]:
        context.user_data["birthday_step"] = 1
        context.user_data["birthday"] = {}
        await update.effective_message.reply_text({
            "ru": "Начнём заявку заново. 🎂\n\nКак зовут именинника?",
            "uz": "Arizani boshidan boshlaymiz. 🎂\n\nTug‘ilgan kun egasining ismi nima?",
            "en": "Let’s start the request again. 🎂\n\nWhat is the birthday child’s name?",
        }[lang])
        return True
    if text == confirm[lang]:
        await finish_birthday(update, context)
        return True
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

    if text in ("💬 Задать вопрос", "💬 Savol berish", "💬 Ask a question"):
        prompts = {
            "ru": "💬 Напишите ваш вопрос — я с радостью помогу!",
            "uz": "💬 Savolingizni yozing — mamnuniyat bilan yordam beraman!",
            "en": "💬 Type your question — I’ll be happy to help!",
        }
        return await update.effective_message.reply_text(prompts.get(lang, prompts["ru"]))

    if text in ("📸 ФОТО-ГИД", "📸 FOTO-GID", "📸 PHOTO GUIDE"):
        return await funlandia(update, lang)

    if text in ("🎁 Акция месяца", "🎁 Aksiya oyi", "🎁 Promotion"):
        return await september_promo(update, context, lang)

    if text in ("🎟️ Цены", "🎟️ Narxlar", "🎟️ Prices"):
        return await prices(update, lang)
    if text in ("🎂 День рождения", "🎂 Tug‘ilgan kun", "🎂 Birthday",
                 "🎉 Забронировать день рождения", "🎉 Tug‘ilgan kunni bron qilish", "🎉 Book a Birthday",
                 "📝 Забронировать день рождения", "📝 Tug‘ilgan kunni bron qilish", "📝 Book a Birthday"):
        return await birthday(update, context)
    if text in ("🎠 Развлечения", "🎠 Ko‘ngilochar", "🎠 Attractions"):
        return await attractions(update, lang)
    if text in ("📍 Адрес", "📍 Manzil", "📍 Address"):
        return await simple(update, lang, "address")
    if text in ("🗺️ Локация на карте", "🗺️ Xaritadagi joylashuv", "🗺️ Map location"):
        return await simple(update, lang, "address")
    if text in ("🕐 Время работы", "🕐 Ish vaqti", "🕐 Opening Hours"):
        return await hours(update, lang)
    if text in ("📍 Контакты", "📍 Kontaktlar", "📍 Contacts", "📞 Контакт", "📞 Kontakt", "📞 Контакты", "📞 Aloqa", "📞 Contact"):
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

    if context.user_data.get("birthday_step") == 9:
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


async def init_booking_database(application: Application):
    """Initialize booking storage and acquire a PostgreSQL singleton lock."""
    global DB_POOL
    if not DATABASE_URL:
        print("BOOKING_DB_DISABLED: DATABASE_URL is not configured", flush=True)
        raise RuntimeError("DATABASE_URL is required to enforce a single test-bot poller")
    try:
        import asyncpg
        # Keep this dedicated connection open for the process lifetime. PostgreSQL
        # releases the advisory lock automatically if the process/connection dies.
        lock_connection = await asyncpg.connect(DATABASE_URL, command_timeout=15)
        acquired = await lock_connection.fetchval("SELECT pg_try_advisory_lock(9107602613)")
        if not acquired:
            await lock_connection.close()
            print("BOT_INSTANCE_LOCKED: another test-bot instance owns the polling lock; exiting", flush=True)
            raise RuntimeError("Another test-bot instance is already active")
        application.bot_data["polling_lock_connection"] = lock_connection
        DB_POOL = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=3, command_timeout=15
        )
        await DB_POOL.execute("""
            CREATE TABLE IF NOT EXISTS birthday_requests (
                id BIGSERIAL PRIMARY KEY,
                telegram_user_id BIGINT NOT NULL,
                telegram_username TEXT,
                customer_name TEXT NOT NULL,
                child_name TEXT NOT NULL,
                child_age TEXT,
                requested_date TEXT NOT NULL,
                children_count TEXT,
                adults_count TEXT,
                phone TEXT NOT NULL,
                celebration_format TEXT,
                wishes TEXT,
                language TEXT NOT NULL DEFAULT 'ru',
                status TEXT NOT NULL DEFAULT 'new',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        print("BOOKING_DB_READY: birthday_requests table is available; polling lock acquired", flush=True)
    except Exception as exc:
        DB_POOL = None
        print(f"BOOKING_DB_ERROR: {type(exc).__name__}: {exc}", flush=True)
        raise


async def save_birthday_request(user, data, lang):
    if DB_POOL is None:
        return False
    await DB_POOL.execute("""
        INSERT INTO birthday_requests (
            telegram_user_id, telegram_username, customer_name, child_name,
            child_age, requested_date, children_count, adults_count, phone,
            celebration_format, wishes, language
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
    """,
        user.id, user.username, user.full_name or "Без имени",
        data.get("name", ""), data.get("age", ""), data.get("date", ""),
        data.get("children", ""), data.get("adults", ""), data.get("phone", ""),
        data.get("format", ""), data.get("wishes", ""), lang
    )
    return True


async def admin_authorized(update: Update) -> bool:
    user = update.effective_user
    return bool(user and ADMIN_CHAT_ID and str(user.id) == str(ADMIN_CHAT_ID))


async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_authorized(update):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return
    if DB_POOL is None:
        await update.effective_message.reply_text("База заявок пока недоступна. Проверьте состояние тестового бота.")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖥 Открыть панель администратора", web_app=WebAppInfo(url="https://funlandia-mini-app-test.up.railway.app/admin"))],
        [InlineKeyboardButton("📅 Заявки на сегодня", callback_data="adm:list:today")],
        [InlineKeyboardButton("📋 Все заявки", callback_data="adm:list:all")],
    ])
    await update.effective_message.reply_text("🎂 FUNLANDIA — управление заявками", reply_markup=keyboard)


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    if not await admin_authorized(update):
        await query.answer("Нет доступа", show_alert=True)
        return
    await query.answer()
    if DB_POOL is None:
        await query.edit_message_text("База заявок пока недоступна.")
        return
    action = (query.data or "").split(":")
    if len(action) == 3 and action[0] == "adm" and action[1] == "list":
        if action[2] == "today":
            rows = await DB_POOL.fetch("""
                SELECT id, child_name, requested_date, phone, status, created_at
                FROM birthday_requests
                WHERE created_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Tashkent')
                                      AT TIME ZONE 'Asia/Tashkent'
                  AND created_at < (date_trunc('day', now() AT TIME ZONE 'Asia/Tashkent') + interval '1 day')
                                      AT TIME ZONE 'Asia/Tashkent'
                ORDER BY created_at DESC LIMIT 30
            """)
            heading = "📅 Заявки, поступившие сегодня"
        else:
            rows = await DB_POOL.fetch("""
                SELECT id, child_name, requested_date, phone, status, created_at
                FROM birthday_requests ORDER BY created_at DESC LIMIT 50
            """)
            heading = "📋 Последние заявки"
        if not rows:
            await query.edit_message_text(heading + "\n\nПока заявок нет.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Меню", callback_data="adm:menu")]]))
            return
        buttons = []
        lines = [heading, ""]
        for row in rows:
            status = {"new":"🆕 Новая","confirmed":"✅ Подтверждена","rejected":"❌ Отклонена"}.get(row["status"], row["status"])
            lines.append(f"№{row['id']} · {row['child_name']} · дата праздника: {row['requested_date']} · {status}")
            buttons.append([InlineKeyboardButton(f"Открыть №{row['id']} — {row['child_name']}", callback_data=f"adm:view:{row['id']}")])
        buttons.append([InlineKeyboardButton("⬅️ Меню", callback_data="adm:menu")])
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
        return
    if len(action) == 2 and action == ["adm", "menu"]:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Заявки на сегодня", callback_data="adm:list:today")],
            [InlineKeyboardButton("📋 Все заявки", callback_data="adm:list:all")],
        ])
        await query.edit_message_text("🎂 FUNLANDIA — управление заявками", reply_markup=keyboard)
        return
    if len(action) == 3 and action[0] == "adm" and action[1] == "view":
        row = await DB_POOL.fetchrow("SELECT * FROM birthday_requests WHERE id=$1", int(action[2]))
        if not row:
            await query.edit_message_text("Заявка не найдена.")
            return
        status = {"new":"🆕 Новая","confirmed":"✅ Подтверждена","rejected":"❌ Отклонена"}.get(row["status"], row["status"])
        username = "@" + row["telegram_username"] if row["telegram_username"] else "нет username"
        body = (
            f"🎂 ЗАЯВКА №{row['id']}\n\n"
            f"Статус: {status}\n"
            f"Именинник: {row['child_name']}\nВозраст: {row['child_age']}\n"
            f"Дата праздника: {row['requested_date']}\n"
            f"Детей: {row['children_count']}\nВзрослых: {row['adults_count']}\n"
            f"Телефон: {row['phone']}\nФормат: {row['celebration_format']}\n"
            f"Пожелания: {row['wishes']}\n\n"
            f"Клиент: {row['customer_name']} ({username})\nTelegram ID: {row['telegram_user_id']}\n"
            f"Получена: {row['created_at'].astimezone().strftime('%d.%m.%Y %H:%M')}"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Подтвердить", callback_data=f"adm:status:{row['id']}:confirmed"),
             InlineKeyboardButton("❌ Отклонить", callback_data=f"adm:status:{row['id']}:rejected")],
            [InlineKeyboardButton("⬅️ К заявкам", callback_data="adm:list:all")]
        ])
        await query.edit_message_text(body, reply_markup=keyboard)
        return
    if len(action) == 4 and action[0] == "adm" and action[1] == "status":
        request_id, new_status = int(action[2]), action[3]
        if new_status not in ("confirmed", "rejected"):
            return
        row = await DB_POOL.fetchrow(
            "UPDATE birthday_requests SET status=$2 WHERE id=$1 RETURNING id, child_name",
            request_id, new_status
        )
        if not row:
            await query.edit_message_text("Заявка не найдена.")
            return
        label = "подтверждена" if new_status == "confirmed" else "отклонена"
        await query.edit_message_text(f"Заявка №{row['id']} ({row['child_name']}) {label}.\n\nОткройте /admin для продолжения.")
        return


async def log_bot_identity(application: Application):
    # Safe diagnostic: print Telegram bot identity only, never the token.
    me = await application.bot.get_me()
    print(f"TEST_BOT_IDENTITY id={me.id} username=@{me.username} name={me.first_name}", flush=True)
    await init_booking_database(application)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = Application.builder().token(BOT_TOKEN).post_init(log_bot_identity).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^adm:"))
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