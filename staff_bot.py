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
        logger.info("DAHUA GET path=%s", self.path)
        if self.path.startswith("/health"):
            self._reply(200, "FUNLANDIA STAFF OK")
        else:
            self._reply(200, "FUNLANDIA STAFF WEBHOOK OK")

    def _read_chunked(self):
        chunks = []
        while True:
            line = self.rfile.readline(65536)
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                size = int(line.split(b";", 1)[0], 16)
            except ValueError:
                logger.warning("DAHUA invalid chunk size: %r", line[:100])
                break
            if size == 0:
                # Consume trailing CRLF / optional trailer headers.
                while True:
                    trailer = self.rfile.readline(65536)
                    if not trailer or trailer in (b"\r\n", b"\n"):
                        break
                break
            data = self.rfile.read(size)
            chunks.append(data)
            self.rfile.read(2)  # CRLF after each chunk
        return b"".join(chunks)

    def _read_body(self):
        transfer_encoding = self.headers.get("Transfer-Encoding", "")
        if "chunked" in transfer_encoding.lower():
            return self._read_chunked()
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length else b""

    def do_POST(self):
        try:
            raw = self._read_body()
            content_type = self.headers.get("Content-Type", "")
            transfer_encoding = self.headers.get("Transfer-Encoding", "")
            logger.info(
                "DAHUA POST path=%s content-type=%s transfer-encoding=%s length=%s body-bytes=%s",
                self.path,
                content_type,
                transfer_encoding,
                self.headers.get("Content-Length", ""),
                len(raw),
            )

            # Keep a readable preview, but do not dump binary JPEG data into logs.
            if raw:
                preview = raw[:2000].decode("utf-8", errors="replace")
                logger.info("DAHUA BODY PREVIEW: %s", preview)

            payload = {}
            text = raw.decode("utf-8", errors="replace")
            if "json" in content_type.lower():
                payload = json.loads(text or "{}")
            elif "multipart/" in content_type.lower():
                # Dahua commonly sends multipart data containing an event JSON part
                # and an image part. Extract JSON-looking parts without assuming a
                # fixed field name or exact multipart layout.
                for marker in (b"application/json", b"text/json"):
                    pos = raw.lower().find(marker)
                    if pos >= 0:
                        start = raw.find(b"\r\n\r\n", pos)
                        if start >= 0:
                            start += 4
                            end = raw.find(b"\r\n--", start)
                            if end < 0:
                                end = len(raw)
                            candidate = raw[start:end].decode("utf-8", errors="replace").strip()
                            try:
                                payload = json.loads(candidate)
                                break
                            except Exception:
                                pass
            else:
                for part in text.replace("\n", "&").split("&"):
                    if "=" in part:
                        key, value = part.split("=", 1)
                        payload[key.strip()] = value.strip()

            if not payload and text and "multipart/" not in content_type.lower():
                payload = {"raw": text}

            if payload:
                save_event(payload)
                logger.info(
                    "DAHUA EVENT parsed user_id=%s user_name=%s event_time=%s event_type=%s",
                    payload.get("UserID") or payload.get("user_id") or payload.get("userId") or "",
                    payload.get("CardName") or payload.get("UserName") or payload.get("user_name") or payload.get("name") or "",
                    payload.get("CreateTime") or payload.get("EventTime") or payload.get("event_time") or "",
                    payload.get("Method") or payload.get("EventType") or payload.get("event_type") or payload.get("Action") or "",
                )
            else:
                logger.info("DAHUA EVENT: no JSON/form payload extracted; raw bytes received=%s", len(raw))

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
