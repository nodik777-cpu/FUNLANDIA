import os
import json
import hashlib
import logging
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("funlandia_staff")

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("STAFF_DB_PATH", "staff_attendance.db")

MENU = ReplyKeyboardMarkup(
    [["📅 Сегодня", "👤 Мои записи"], ["📊 Отчёт", "ℹ️ Помощь"]],
    resize_keyboard=True,
)


def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT UNIQUE,
            user_id TEXT,
            user_name TEXT,
            event_time TEXT NOT NULL,
            event_type TEXT,
            status TEXT,
            source TEXT DEFAULT 'dahua',
            raw_payload TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_users (
            chat_id INTEGER PRIMARY KEY,
            dahua_user_id TEXT,
            username TEXT,
            first_name TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # Upgrade databases created by the earlier bot version.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(attendance)").fetchall()}
    for name, sql in [
        ("event_key", "ALTER TABLE attendance ADD COLUMN event_key TEXT"),
        ("status", "ALTER TABLE attendance ADD COLUMN status TEXT"),
    ]:
        if name not in cols:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass
    conn.commit()
    conn.close()


def first_value(data, *keys):
    if not isinstance(data, dict):
        return ""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return ""


def flatten_event(payload):
    """Extract common Dahua fields from several JSON layouts."""
    candidates = [payload]
    if isinstance(payload, dict):
        for key in ("data", "Data", "event", "Event", "record", "Record", "params", "paramsData"):
            value = payload.get(key)
            if isinstance(value, dict):
                candidates.append(value)
            elif isinstance(value, list):
                candidates.extend(x for x in value if isinstance(x, dict))

    user_id = user_name = event_time = method = status = ""
    for item in candidates:
        user_id = user_id or str(first_value(item, "UserID", "user_id", "userId", "ID", "id", "No"))
        user_name = user_name or str(first_value(item, "CardName", "UserName", "user_name", "name", "Name"))
        event_time = event_time or str(first_value(item, "CreateTime", "EventTime", "event_time", "Time", "time"))
        method = method or str(first_value(item, "Method", "EventType", "event_type", "Action", "Type"))
        status = status or str(first_value(item, "Status", "status", "Result", "result", "ErrorCode"))

    return {
        "user_id": user_id,
        "user_name": user_name,
        "event_time": event_time or datetime.now(timezone.utc).isoformat(),
        "event_type": method,
        "status": status,
    }


def event_key(payload, info):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    base = "|".join([
        info["user_id"],
        info["user_name"],
        info["event_time"],
        info["event_type"],
        info["status"],
    ])
    return hashlib.sha256((base + "|" + raw).encode("utf-8")).hexdigest()


def save_event(payload):
    info = flatten_event(payload)
    key = event_key(payload, info)
    conn = db()
    conn.execute(
        """
        INSERT OR IGNORE INTO attendance
        (event_key, user_id, user_name, event_time, event_type, status, source, raw_payload)
        VALUES (?, ?, ?, ?, ?, ?, 'dahua', ?)
        """,
        (
            key,
            info["user_id"],
            info["user_name"],
            info["event_time"],
            info["event_type"],
            info["status"],
            json.dumps(payload, ensure_ascii=False, default=str),
        ),
    )
    inserted = conn.total_changes > 0
    conn.commit()
    conn.close()
    return inserted, info


def parse_body(raw, content_type):
    if not raw:
        return {}
    text = raw.decode("utf-8", errors="replace").strip()
    if "json" in content_type.lower():
        try:
            return json.loads(text or "{}")
        except Exception:
            return {"raw": text}

    if "multipart/" in content_type.lower():
        # Look for a JSON part without depending on a fixed boundary or field name.
        lower = raw.lower()
        for marker in (b"application/json", b"text/json"):
            pos = lower.find(marker)
            if pos >= 0:
                start = raw.find(b"\r\n\r\n", pos)
                if start >= 0:
                    start += 4
                    end = raw.find(b"\r\n--", start)
                    candidate = raw[start:end if end >= 0 else len(raw)].strip()
                    try:
                        return json.loads(candidate.decode("utf-8", errors="replace"))
                    except Exception:
                        pass
        return {"raw": text[:10000]}

    parsed = parse_qs(text, keep_blank_values=True)
    if parsed:
        return {k: v[-1] if v else "" for k, v in parsed.items()}
    return {"raw": text}


class DahuaHandler(BaseHTTPRequestHandler):
    def _reply(self, code=200, text="OK", content_type="text/plain; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        logger.info("DAHUA GET path=%s", self.path)
        if self.path.startswith("/health"):
            self._reply(200, "FUNLANDIA STAFF OK")
        elif self.path.startswith("/dahua"):
            self._reply(200, "FUNLANDIA DAHUA ENDPOINT OK")
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
                logger.warning("Invalid chunk size: %r", line[:100])
                break
            if size == 0:
                while True:
                    trailer = self.rfile.readline(65536)
                    if not trailer or trailer in (b"\r\n", b"\n"):
                        break
                break
            chunks.append(self.rfile.read(size))
            self.rfile.read(2)
        return b"".join(chunks)

    def _read_body(self):
        transfer = self.headers.get("Transfer-Encoding", "")
        if "chunked" in transfer.lower():
            return self._read_chunked()
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length else b""

    def do_POST(self):
        try:
            raw = self._read_body()
            content_type = self.headers.get("Content-Type", "")
            logger.info(
                "DAHUA POST path=%s content-type=%s transfer-encoding=%s length=%s body-bytes=%s",
                self.path,
                content_type,
                self.headers.get("Transfer-Encoding", ""),
                self.headers.get("Content-Length", ""),
                len(raw),
            )

            if self.path.startswith("/dahua"):
                payload = parse_body(raw, content_type)
                if payload:
                    inserted, info = save_event(payload)
                    logger.info(
                        "DAHUA EVENT parsed inserted=%s user_id=%s user_name=%s event_time=%s event_type=%s status=%s",
                        inserted,
                        info["user_id"],
                        info["user_name"],
                        info["event_time"],
                        info["event_type"],
                        info["status"],
                    )
                else:
                    logger.info("DAHUA EVENT empty payload")
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


def now_local():
    return datetime.now().astimezone()


def format_row(row):
    name = row["user_name"] or row["user_id"] or "Неизвестный"
    tm = row["event_time"]
    if "T" in tm:
        tm = tm.split("T", 1)[-1][:8]
    elif " " in tm:
        tm = tm.split(" ", 1)[-1][:8]
    return f"• {name} — {tm}"


def get_day_rows(day, user_id=None):
    conn = db()
    if user_id:
        rows = conn.execute(
            "SELECT * FROM attendance WHERE event_time LIKE ? AND user_id=? ORDER BY event_time ASC",
            (day + "%", str(user_id)),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM attendance WHERE event_time LIKE ? ORDER BY event_time ASC",
            (day + "%",),
        ).fetchall()
    conn.close()
    return rows


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    now = now_local().isoformat()
    conn = db()
    conn.execute(
        """
        INSERT INTO telegram_users(chat_id, username, first_name, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name, updated_at=excluded.updated_at
        """,
        (update.effective_chat.id, user.username if user else "", user.first_name if user else "", now, now),
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(
        "👷 FUNLANDIA — БОТ СОТРУДНИКОВ\n\n"
        "Бот подключён. Выберите действие ниже.",
        reply_markup=MENU,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Команды:\n\n"
        "/today — посещаемость за сегодня\n"
        "/me — ваши записи, если ваш Telegram привязан к ID Dahua\n"
        "/link ID — привязать свой Telegram к ID сотрудника Dahua\n"
        "/report YYYY-MM-DD — отчёт за дату\n"
        "/last — последние 20 событий",
        reply_markup=MENU,
    )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    day = now_local().strftime("%Y-%m-%d")
    rows = get_day_rows(day)
    if not rows:
        await update.message.reply_text("📅 Сегодня записей пока нет.", reply_markup=MENU)
        return
    lines = [f"📅 Посещаемость {day}:"]
    for row in rows[-100:]:
        lines.append(format_row(row))
    await update.message.reply_text("\n".join(lines), reply_markup=MENU)


async def link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].strip():
        await update.message.reply_text("Использование: /link ID\nНапример: /link 10")
        return
    dahua_id = context.args[0].strip()
    now = now_local().isoformat()
    user = update.effective_user
    conn = db()
    conn.execute(
        """
        INSERT INTO telegram_users(chat_id, dahua_user_id, username, first_name, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET dahua_user_id=excluded.dahua_user_id, updated_at=excluded.updated_at
        """,
        (update.effective_chat.id, dahua_id, user.username if user else "", user.first_name if user else "", now, now),
    )
    conn.commit()
    row = conn.execute("SELECT user_name FROM attendance WHERE user_id=? AND user_name<>'' ORDER BY id DESC LIMIT 1", (dahua_id,)).fetchone()
    conn.close()
    name = row["user_name"] if row else "сотрудник с этим ID"
    await update.message.reply_text(f"✅ Telegram привязан к {name} (ID {dahua_id}).", reply_markup=MENU)


async def me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    user = conn.execute("SELECT dahua_user_id FROM telegram_users WHERE chat_id=?", (update.effective_chat.id,)).fetchone()
    conn.close()
    if not user or not user["dahua_user_id"]:
        await update.message.reply_text("Ваш Telegram пока не привязан. Используйте /link ID.", reply_markup=MENU)
        return
    day = now_local().strftime("%Y-%m-%d")
    rows = get_day_rows(day, user["dahua_user_id"])
    if not rows:
        await update.message.reply_text(f"📅 Сегодня для ID {user['dahua_user_id']} записей нет.", reply_markup=MENU)
        return
    await update.message.reply_text(
        f"👤 Ваши записи за {day}:\n" + "\n".join(format_row(r) for r in rows),
        reply_markup=MENU,
    )


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    day = context.args[0] if context.args else now_local().strftime("%Y-%m-%d")
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("Формат даты: /report 2026-09-12")
        return
    rows = get_day_rows(day)
    if not rows:
        await update.message.reply_text(f"📊 За {day} записей нет.", reply_markup=MENU)
        return
    grouped = {}
    for row in rows:
        key = row["user_id"] or row["user_name"] or "unknown"
        grouped.setdefault(key, {"name": row["user_name"] or key, "times": []})["times"].append(row["event_time"])
    lines = [f"📊 Отчёт за {day}", f"Событий: {len(rows)}", f"Сотрудников: {len(grouped)}", ""]
    for item in grouped.values():
        times = []
        for value in item["times"]:
            if "T" in value:
                value = value.split("T", 1)[-1][:8]
            elif " " in value:
                value = value.split(" ", 1)[-1][:8]
            times.append(value)
        lines.append(f"👤 {item['name']}: {times[0]} → {times[-1]} ({len(times)} проход.)")
    await update.message.reply_text("\n".join(lines), reply_markup=MENU)


async def last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    rows = conn.execute("SELECT * FROM attendance ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("Записей пока нет.", reply_markup=MENU)
        return
    await update.message.reply_text("🕘 Последние события:\n" + "\n".join(format_row(r) for r in reversed(rows)), reply_markup=MENU)


async def button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text if update.message else ""
    if text == "📅 Сегодня":
        await today(update, context)
    elif text == "👤 Мои записи":
        await me(update, context)
    elif text == "📊 Отчёт":
        await report(update, context)
    elif text == "ℹ️ Помощь":
        await help_command(update, context)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    init_db()
    threading.Thread(target=run_http_server, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("today", today))
    application.add_handler(CommandHandler("link", link))
    application.add_handler(CommandHandler("me", me))
    application.add_handler(CommandHandler("report", report))
    application.add_handler(CommandHandler("last", last))
    application.add_handler(__import__("telegram.ext", fromlist=["MessageHandler"]).MessageHandler(__import__("telegram.ext", fromlist=["filters"]).filters.TEXT & ~__import__("telegram.ext", fromlist=["filters"]).filters.COMMAND, button_text))

    logger.info("FUNLANDIA STAFF BOT STARTED")
    application.run_polling()


if __name__ == "__main__":
    main()
