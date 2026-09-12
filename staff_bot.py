import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👷 FUNLANDIA — БОТ СОТРУДНИКОВ\n\n"
        "✅ Бот работает.\n\n"
        "Здесь будет система учёта рабочего времени."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Доступные команды:\n\n"
        "/start — запуск бота\n"
        "/help — помощь"
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    print("STAFF BOT STARTED")

    application.run_polling()


if __name__ == "__main__":
    main()
