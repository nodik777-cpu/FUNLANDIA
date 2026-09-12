import os
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("STAFF_DB_PATH", "staff_attendance.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            user_name TEXT,
            event_time TEXT NOT NULL,
            event_type TEXT,
            source TEXT DEFAULT 'dahua',
            raw_payload TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def save_event(payload):
    user_id = str(payload.get("UserID") or payload.get("user_id") or payload.get("userId") or "")
    user_name = str(
        payload.get("CardName")
        or payload.get("UserName")
        or payload.get("user_name")
        or payload.get("name")
        or ""
    )
    event_type = str(
        payload.get("Method")
        or payload.get("EventType")
        or payload.get("event_type")
        or payload.get("Action")
        or ""
    )
    event_time = str(
        payload.get("CreateTime")
        or payload.get("EventTime")
        or payload.get("event_time")
        or datetime.now(timezone.utc).isoformat()
    )

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO attendance (user_id, user_name, event_time, event_type, raw_payload) VALUES (?, ?, ?, ?, ?)",
        (user_id, user_name, event_time, event_type, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


class DahuaHandler(BaseHTTPRequestHandler):
    def _reply(self, code=200, text="OK"):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/health"):
            self._reply(200, "FUNLANDIA STAFF OK")
        else:
            self._reply(200, "FUNLANDIA STAFF WEBHOOK OK")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b""
            text = raw.decode("utf-8", errors="replace")
            content_type = self.headers.get("Content-Type", "")
            logger.info("DAHUA POST content-type=%s body=%s", content_type, text[:4000])

            payload = {}
            if "json" in content_type.lower():
                payload = json.loads(text or "{}")
            else:
                # Accept simple key=value or form-style payloads without assuming a fixed Dahua format.
                for part in text.replace("\n", "&").split("&"):
                    if "=" in part:
                        key, value = part.split("=", 1)
                        payload[key.strip()] = value.strip()

            if not payload and text:
                payload = {"raw": text}

            if payload:
                save_event(payload)

            self._reply(200, "OK")
        except Exception as exc:
            logger.exception("DAHUA webhook error: %s", exc)
            self._reply(200, "OK")

    def log_message(self, format, *args):
        return


def run_http_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), DahuaHandler)
    logger.info("DAHUA HTTP SERVER LISTENING ON 0.0.0.0:%s", PORT)
    server.serve_forever()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👷 FUNLANDIA — БОТ СОТРУДНИКОВ\n\n"
        "✅ Бот работает.\n"
        "🌐 Сервер для Dahua запущен.\n\n"
        "Система учёта рабочего времени готова к подключению терминала."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Доступные команды:\n\n"
        "/start — запуск бота\n"
        "/help — помощь\n"
        "/today — посещаемость за сегодня"
    )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    day = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT user_id, user_name, event_time, event_type FROM attendance WHERE event_time LIKE ? ORDER BY event_time DESC LIMIT 50",
        (day + "%",),
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📅 Сегодня пока нет записей посещения.")
        return

    lines = ["📅 Посещаемость сегодня:"]
    for user_id, user_name, event_time, event_type in rows:
        who = user_name or user_id or "Неизвестный"
        lines.append(f"• {who} — {event_time} {event_type}".strip())

    await update.message.reply_text("\n".join(lines))


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    init_db()
    threading.Thread(target=run_http_server, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("today", today))

    print("STAFF BOT STARTED")
    application.run_polling()


if __name__ == "__main__":
    main()
