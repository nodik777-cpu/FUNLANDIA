import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
PHONE = "+998 93 381 00 55"
ADDRESS = "Ташкент, ул. Тимур Малика, 3"
INSTAGRAM = "https://www.instagram.com/funlandiauz/"

def menu():
    return ReplyKeyboardMarkup([
        ["🎟️ Цены", "🎂 День рождения"],
        ["🎠 Развлечения", "📍 Адрес"],
        ["🕐 Время работы", "📸 Instagram"],
        ["📞 Администратор", "🇺🇿 O‘zbekcha"],
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎡 FUNLANDIA\n\nДобро пожаловать! Здесь дети играют, а родители отдыхают ❤️\n\nВыберите раздел:",
        reply_markup=menu())

async def birthday_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data["birthday_step"]
    value = update.message.text.strip()
    data = context.user_data["birthday"]

    if step == 1:
        data["name"] = value
        context.user_data["birthday_step"] = 2
        await update.message.reply_text("📅 На какую дату планируете день рождения?")
    elif step == 2:
        data["date"] = value
        context.user_data["birthday_step"] = 3
        await update.message.reply_text("👧👦 Сколько будет детей?")
    elif step == 3:
        data["children"] = value
        context.user_data["birthday_step"] = 4
        await update.message.reply_text("🕐 Какое время вас интересует?")
    elif step == 4:
        data["time"] = value
        context.user_data["birthday_step"] = 5
        await update.message.reply_text("📞 Оставьте номер телефона для связи с администратором.")
    else:
        data["phone"] = value
        username = update.effective_user.username or "нет username"
        msg = (f"🎂 НОВАЯ ЗАЯВКА FUNLANDIA\n\nИменинник: {data['name']}\n"
               f"Дата: {data['date']}\nДетей: {data['children']}\n"
               f"Время: {data['time']}\nТелефон: {data['phone']}\nTelegram: @{username}")
        if ADMIN_CHAT_ID:
            try:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg)
            except Exception:
                pass
        context.user_data.clear()
        await update.message.reply_text(
            "✅ Спасибо! Заявка принята. Администратор FUNLANDIA свяжется с вами.",
            reply_markup=menu())

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if context.user_data.get("birthday_step"):
        return await birthday_form(update, context)

    if text == "🎟️ Цены":
        reply = ("🎟️ ЦЕНЫ FUNLANDIA\n\n1 зона — площадка ИЛИ батут:\n"
                 "⏱️ 1 час — 80 000 сум\n⏱️ 2 часа — 90 000 сум\n"
                 "♾️ Безлимит — 100 000 сум\n\n2 зоны — площадка + батут:\n"
                 "♾️ Безлимит — 120 000 сум")
    elif text == "🕐 Время работы":
        reply = ("🕐 ВРЕМЯ РАБОТЫ\n\nВторник–воскресенье: 10:00–22:00\n"
                 "Понедельник: 14:00–22:00\n\n🧹 Понедельник до 14:00 — санитарный день.\nБез выходных.")
    elif text == "📍 Адрес":
        reply = f"📍 FUNLANDIA\n\n{ADDRESS}\n\n📞 {PHONE}"
    elif text == "📸 Instagram":
        reply = f"📸 Instagram FUNLANDIA:\n{INSTAGRAM}"
    elif text == "📞 Администратор":
        reply = f"📞 Администратор FUNLANDIA\n\n{PHONE}"
    elif text == "🎠 Развлечения":
        reply = ("🎠 НАШИ РАЗВЛЕЧЕНИЯ\n\n🛝 4-этажный лабиринт\n🎢 Горки\n"
                 "🤸 Батуты\n⚡ Ninja\n🧸 Зона для малышей\n🏖️ Кинетический песок\n"
                 "🎯 Пневматические развлечения\n🎠 Карусели")
    elif text == "🇺🇿 O‘zbekcha":
        reply = "🇺🇿 O‘zbek tili bo‘limi tez orada to‘liq ishga tushadi."
    elif text == "🎂 День рождения":
        context.user_data["birthday_step"] = 1
        context.user_data["birthday"] = {}
        return await update.message.reply_text(
            "🎂 TUG‘ILGAN KUNNI FUNLANDIA'DA NISHONLANG!\n\n"
            "🎉 5 bolaga — 450 000 so‘m\n🎉 10 bolaga — 900 000 so‘m\n"
            "🎁 Tug‘ilgan kun egasiga — 3 ta karusel sovg‘a!\n\n"
            "Bolaning ismini yozing:")
    else:
        reply = "😊 Menyudan kerakli bo‘limni tanlang yoki administrator bilan bog‘laning."
    await update.message.reply_text(reply, reply_markup=menu())

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))
    app.run_polling()

if __name__ == "__main__":
    main()
