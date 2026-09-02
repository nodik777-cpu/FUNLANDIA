import os
import asyncio
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_BOT_TOKEN_HERE")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")  # optional

ADDRESS = "Ташкент, ул. Тимур Малика, 3"
INSTAGRAM = "https://www.instagram.com/funlandiauz/"
PHONE = "+998 93 381 00 55"

def main_menu():
    return ReplyKeyboardMarkup([
        ["🎟️ Цены", "🎂 День рождения"],
        ["🎠 Развлечения", "📍 Адрес"],
        ["🕐 Время работы", "📸 Instagram"],
        ["📞 Администратор", "🇺🇿 O‘zbekcha"],
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎡 FUNLANDIA\n\n"
        "Добро пожаловать! Здесь дети играют, а родители отдыхают ❤️\n\n"
        "Выберите интересующий раздел:"
    )
    await update.message.reply_text(text, reply_markup=main_menu())

async def prices(update: Update):
    await update.message.reply_text(
        "🎟️ ЦЕНЫ FUNLANDIA\n\n"
        "1 зона — детская площадка ИЛИ батут:\n"
        "⏱️ 1 час — 80 000 сум\n"
        "⏱️ 2 часа — 90 000 сум\n"
        "♾️ Безлимит — 100 000 сум\n\n"
        "2 зоны — площадка + батут:\n"
        "♾️ Безлимит — 120 000 сум"
    )

async def hours(update: Update):
    await update.message.reply_text(
        "🕐 ВРЕМЯ РАБОТЫ\n\n"
        "Вторник–воскресенье: 10:00–22:00\n"
        "Понедельник: 14:00–22:00\n\n"
        "🧹 Каждый понедельник до 14:00 — санитарный день.\n"
        "Без выходных."
    )

async def address(update: Update):
    await update.message.reply_text(
        f"📍 FUNLANDIA\n\n{ADDRESS}\n\n"
        f"📞 {PHONE}\n"
        "🗺️ Откройте адрес в картах Telegram/Google/Yandex."
    )

async def instagram(update: Update):
    await update.message.reply_text(f"📸 Instagram FUNLANDIA:\n{INSTAGRAM}")

async def attractions(update: Update):
    await update.message.reply_text(
        "🎠 НАШИ РАЗВЛЕЧЕНИЯ\n\n"
        "🛝 4-этажный лабиринт\n"
        "🎢 Горки\n"
        "🤸 Батуты\n"
        "⚡ Ninja\n"
        "🧸 Зона для малышей\n"
        "🏖️ Кинетический песок\n"
        "🎯 Пневматические развлечения\n"
        "🎠 Карусели\n\n"
        "За актуальными условиями и ограничениями обращайтесь к администратору."
    )

async def birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["birthday"] = True
    context.user_data["birthday_step"] = 1
    await update.message.reply_text(
        "🎂 ДЕНЬ РОЖДЕНИЯ В FUNLANDIA!\n\n"
        "🎉 5 детей — 450 000 сум\n"
        "🎉 10 детей — 900 000 сум\n"
        "🎁 Имениннику — 3 карусели в подарок!\n\n"
        "Давайте оформим заявку.\n"
        "Напишите имя именинника:"
    )

async def admin(update: Update):
    await update.message.reply_text(
        f"📞 АДМИНИСТРАТОР\n\n"
        f"Телефон: {PHONE}\n\n"
        "Нажмите на номер, чтобы позвонить."
    )

async def handle_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("birthday_step", 0)
    value = update.message.text.strip()
    data = context.user_data.setdefault("birthday_data", {})

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
        await update.message.reply_text(
            "📞 Оставьте номер телефона для связи с администратором."
        )
    elif step == 5:
        data["phone"] = value
        username = update.effective_user.username or "нет username"
        summary = (
            "🎂 НОВАЯ ЗАЯВКА FUNLANDIA\n\n"
            f"Именинник: {data['name']}\n"
            f"Дата: {data['date']}\n"
            f"Детей: {data['children']}\n"
            f"Время: {data['time']}\n"
            f"Телефон: {data['phone']}\n"
            f"Telegram: @{username}"
        )
        if ADMIN_CHAT_ID:
            try:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=summary)
            except Exception:
                pass
        context.user_data.clear()
        await update.message.reply_text(
            "✅ Спасибо! Заявка принята.\n"
            "Администратор FUNLANDIA свяжется с вами для подтверждения.",
            reply_markup=main_menu()
        )

async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if context.user_data.get("birthday"):
        return await handle_birthday(update, context)

    if text == "🎟️ Цены":
        return await prices(update)
    if text == "🎂 День рождения":
        return await birthday(update, context)
    if text == "🎠 Развлечения":
        return await attractions(update)
    if text == "📍 Адрес":
        return await address(update)
    if text == "🕐 Время работы":
        return await hours(update)
    if text == "📸 Instagram":
        return await instagram(update)
    if text == "📞 Администратор":
        return await admin(update)
    if text == "🇺🇿 O‘zbekcha":
        await update.message.reply_text(
            "🇺🇿 Hozircha o‘zbekcha bo‘lim tayyorlanmoqda.\n"
            "Tez orada barcha javoblar o‘zbek tilida ham ishlaydi.",
            reply_markup=main_menu()
        )
        return

    await update.message.reply_text(
        "😊 Savolingizni tushunmadim.\n"
        "Menyudan kerakli bo‘limni tanlang yoki administrator bilan bog‘laning.",
        reply_markup=main_menu()
    )

def run():
    if BOT_TOKEN == "PASTE_BOT_TOKEN_HERE":
        raise RuntimeError("Укажите BOT_TOKEN в переменной окружения BOT_TOKEN.")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message))
    app.run_polling()

if __name__ == "__main__":
    run()
