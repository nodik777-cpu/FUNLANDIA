import os
import re
import json
import hashlib
import logging
import sqlite3
import threading
import calendar
from datetime import datetime, timezone, timedelta, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("funlandia_staff")

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("STAFF_DB_PATH", "staff_attendance.db")
ADMIN_CHAT_ID = os.getenv("STAFF_ADMIN_CHAT_ID") or os.getenv("ADMIN_CHAT_ID", "")
SHIFT_START = os.getenv("SHIFT_START", "09:00")
LOCAL_TZ = timezone(timedelta(hours=5))

MENU = ReplyKeyboardMarkup(
    [
        ["📊 Сегодня", "👥 Сейчас на работе"],
        ["📅 Неделя", "🗓 Месяц"],
        ["👤 Мои записи", "📋 Мой отчёт"],
        ["ℹ️ Помощь"],
    ],
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_attendance_day ON attendance(event_time)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_attendance_user ON attendance(user_id, event_time)")
    conn.commit()
    conn.close()


def now_local():
    return datetime.now(LOCAL_TZ)


def parse_time_value(value):
    if value in (None, ""):
        return now_local().isoformat()
    text = str(value).strip()
    if text.isdigit():
        try:
            number = int(text)
            dt = datetime.fromtimestamp(number, tz=timezone.utc).astimezone(LOCAL_TZ)
            return dt.isoformat()
        except Exception:
            pass
    text = text.replace("Z", "+00:00")
    for candidate in (text, text.replace("/", "-")):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=LOCAL_TZ)
            return dt.astimezone(LOCAL_TZ).isoformat()
        except Exception:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=LOCAL_TZ).isoformat()
        except Exception:
            pass
    return now_local().isoformat()


def first_value(data, *keys):
    if not isinstance(data, dict):
        return ""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return ""


def flatten_event(payload):
    candidates = []
    if isinstance(payload, dict):
        candidates.append(payload)
        for key in ("data", "Data", "event", "Event", "record", "Record", "params", "paramsData"):
            value = payload.get(key)
            if isinstance(value, dict):
                candidates.append(value)
            elif isinstance(value, list):
                candidates.extend(x for x in value if isinstance(x, dict))
        grouped = {}
        for key, value in payload.items():
            m = re.match(r"(?:Events|records)\[(\d+)\]\.(.+)$", str(key), re.I)
            if m:
                grouped.setdefault(m.group(1), {})[m.group(2)] = value
        candidates.extend(grouped.values())

    user_id = user_name = event_time = event_type = status = rec_no = ""
    for item in candidates:
        user_id = user_id or str(first_value(item, "UserID", "user_id", "userId", "ID", "id", "No"))
        user_name = user_name or str(first_value(item, "CardName", "UserName", "user_name", "userIdName", "name", "Name"))
        event_time = event_time or str(first_value(item, "CreateTime", "EventTime", "event_time", "Time", "time"))
        event_type = event_type or str(first_value(item, "Type", "EventType", "event_type", "Action", "Name"))
        status = status or str(first_value(item, "Status", "status", "Result", "result", "ErrorCode"))
        rec_no = rec_no or str(first_value(item, "RecNo", "RecordNo", "recordNo"))

    return {
        "user_id": user_id.strip(),
        "user_name": user_name.strip(),
        "event_time": parse_time_value(event_time),
        "event_type": event_type.strip(),
        "status": status.strip(),
        "rec_no": rec_no.strip(),
    }


def event_key(payload, info):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    base = "|".join([
        info["rec_no"], info["user_id"], info["user_name"],
        info["event_time"], info["event_type"], info["status"],
    ])
    return hashlib.sha256((base + "|" + raw).encode("utf-8")).hexdigest()


def status_success(value):
    text = str(value).strip().lower()
    return text in ("", "1", "true", "success", "succeeded", "ok", "выполнено")


def save_event(payload):
    info = flatten_event(payload)
    if not info["user_id"] and not info["user_name"]:
        return False, info
    key = event_key(payload, info)
    conn = db()
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO attendance
        (event_key, user_id, user_name, event_time, event_type, status, source, raw_payload)
        VALUES (?, ?, ?, ?, ?, ?, 'dahua_http_push', ?)
        """,
        (
            key, info["user_id"], info["user_name"], info["event_time"],
            info["event_type"], info["status"],
            json.dumps(payload, ensure_ascii=False, default=str),
        ),
    )
    inserted = cur.rowcount == 1
    conn.commit()
    conn.close()
    return inserted, info


def xml_to_dict(raw):
    try:
        root = ET.fromstring(raw.decode("utf-8", errors="replace"))
    except Exception:
        return {}
    result = {}
    for elem in root.iter():
        if elem is root:
            continue
        tag = elem.tag.split("}")[-1]
        value = (elem.text or "").strip()
        if value:
            result[tag] = value
    return result


def parse_text_event(text):
    result = {}
    for line in re.split(r"\r?\n", text):
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def parse_body(raw, content_type):
    if not raw:
        return {}
    text = raw.decode("utf-8", errors="replace").strip()
    ct = (content_type or "").lower()

    if "json" in ct or text.startswith("{") or text.startswith("["):
        try:
            return json.loads(text or "{}")
        except Exception:
            pass
    if "xml" in ct or text.startswith("<"):
        parsed = xml_to_dict(raw)
        if parsed:
            return parsed
    if "multipart/" in ct:
        parts = re.split(rb"\r?\n--[^\r\n]+", raw)
        for part in parts:
            if not part:
                continue
            marker = part.find(b"\r\n\r\n")
            step = 4
            if marker < 0:
                marker = part.find(b"\n\n")
                step = 2
            if marker >= 0:
                body = part[marker + step:].strip()
                if body.startswith(b"{"):
                    try:
                        return json.loads(body.decode("utf-8", errors="replace"))
                    except Exception:
                        pass
                parsed = parse_text_event(body.decode("utf-8", errors="replace"))
                if parsed:
                    return parsed
        return {"raw": text[:20000]}

    form = parse_qs(text, keep_blank_values=True)
    if form:
        return {k: v[-1] if v else "" for k, v in form.items()}
    parsed = parse_text_event(text)
    return parsed or {"raw": text[:20000]}


def extract_payloads(payload):
    if not isinstance(payload, dict):
        return []
    events = []
    for key in ("events", "Events", "records", "Records"):
        value = payload.get(key)
        if isinstance(value, list):
            events.extend(x for x in value if isinstance(x, dict))
    if events:
        return events
    grouped = {}
    for key, value in payload.items():
        m = re.match(r"(?:Events|records)\[(\d+)\]\.(.+)$", str(key), re.I)
        if m:
            grouped.setdefault(m.group(1), {})[m.group(2)] = value
    if grouped:
        return list(grouped.values())
    return [payload]


class DahuaHandler(BaseHTTPRequestHandler):
    def _reply(self, code=200, text="OK", content_type="text/plain; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def do_GET(self):
        path = urlparse(self.path).path
        logger.info("DAHUA GET path=%s", path)
        self._reply(200, "FUNLANDIA STAFF OK" if path.startswith("/health") else "OK")

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
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        return self.rfile.read(length) if length else b""

    def do_POST(self):
        try:
            raw = self._read_body()
            content_type = self.headers.get("Content-Type", "")
            path = urlparse(self.path).path
            logger.info(
                "DAHUA POST path=%s content-type=%s transfer=%s body-bytes=%s",
                path, content_type, self.headers.get("Transfer-Encoding", ""), len(raw)
            )
            if "keepalive" in path.lower() or not raw:
                self._reply(200, "OK")
                return
            payload = parse_body(raw, content_type)
            inserted_count = 0
            for event in extract_payloads(payload):
                inserted, info = save_event(event)
                if inserted:
                    inserted_count += 1
                if info["user_id"] or info["user_name"]:
                    logger.info(
                        "DAHUA EVENT inserted=%s id=%s name=%s time=%s type=%s status=%s",
                        inserted, info["user_id"], info["user_name"], info["event_time"],
                        info["event_type"], info["status"]
                    )
            logger.info("DAHUA PUSH processed=%s new-events=%s", path, inserted_count)
            self._reply(200, "OK")
        except Exception as exc:
            logger.exception("DAHUA webhook error: %s", exc)
            self._reply(200, "OK")

    def log_message(self, format, *args):
        return


def run_http_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), DahuaHandler)
    logger.info("DAHUA HTTP PUSH SERVER LISTENING ON 0.0.0.0:%s", PORT)
    server.serve_forever()


def day_rows(day, user_id=None, successful_only=True):
    conn = db()
    where = ["event_time LIKE ?"]
    args = [day + "%"]
    if user_id:
        where.append("user_id=?")
        args.append(str(user_id))
    if successful_only:
        where.append("(status IS NULL OR status='' OR lower(status) IN ('1','true','success','succeeded','ok','выполнено'))")
    sql = "SELECT * FROM attendance WHERE " + " AND ".join(where) + " ORDER BY event_time ASC, id ASC"
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return rows


def rows_between(start_day, end_day, user_id=None):
    conn = db()
    where = ["event_time >= ?", "event_time < ?"]
    args = [start_day + "T00:00:00+05:00", end_day + "T23:59:59.999999+05:00"]
    if user_id:
        where.append("user_id=?")
        args.append(str(user_id))
    where.append("(status IS NULL OR status='' OR lower(status) IN ('1','true','success','succeeded','ok','выполнено'))")
    sql = "SELECT * FROM attendance WHERE " + " AND ".join(where) + " ORDER BY event_time ASC, id ASC"
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return rows


def normalize_type(value):
    text = str(value or "").strip().lower()
    if text in ("entry", "вход", "in"):
        return "Entry"
    if text in ("exit", "выход", "out"):
        return "Exit"
    return ""


def parse_dt(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def staff_state(rows):
    events = [r for r in rows if status_success(r["status"])]
    if not events:
        return {"present": False, "first": None, "last_exit": None, "worked": 0, "events": []}
    typed = [(r, normalize_type(r["event_type"])) for r in events]
    has_direction = any(t for _, t in typed)
    present = False
    first = None
    last_exit = None
    worked = 0
    open_time = None
    for row, typ in typed:
        dt = parse_dt(row["event_time"])
        if not dt:
            continue
        if typ == "Entry":
            if first is None:
                first = dt
            if open_time is None:
                open_time = dt
            present = True
        elif typ == "Exit":
            if last_exit is None or dt > last_exit:
                last_exit = dt
            if open_time is not None and dt >= open_time:
                worked += int((dt - open_time).total_seconds())
                open_time = None
            present = False
        elif not has_direction:
            if first is None:
                first = dt
            if present:
                if last_exit is None or dt > last_exit:
                    last_exit = dt
                if open_time is not None and dt >= open_time:
                    worked += int((dt - open_time).total_seconds())
                open_time = None
                present = False
            else:
                open_time = dt
                present = True
    if open_time is not None:
        worked += max(0, int((now_local() - open_time).total_seconds()))
    if has_direction:
        last_typed = next((t for _, t in reversed(typed) if t), "")
        present = last_typed == "Entry"
    return {"present": present, "first": first, "last_exit": last_exit, "worked": worked, "events": events}


def fmt_hm(dt):
    return dt.strftime("%H:%M") if dt else "—"


def fmt_duration(seconds):
    seconds = max(0, int(seconds or 0))
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h:
        return f"{h} ч {m:02d} мин"
    return f"{m} мин"


def all_people_today(day):
    rows = day_rows(day)
    grouped = {}
    for row in rows:
        key = str(row["user_id"] or row["user_name"] or "unknown")
        grouped.setdefault(key, []).append(row)
    result = []
    for key, items in grouped.items():
        state = staff_state(items)
        name = items[-1]["user_name"] or items[-1]["user_id"] or "Неизвестный"
        result.append({"id": key, "name": name, **state})
    result.sort(key=lambda x: (not x["present"], x["name"].lower()))
    return result


def is_admin(update):
    return bool(ADMIN_CHAT_ID and str(update.effective_chat.id) == str(ADMIN_CHAT_ID))


def shift_late(first):
    if not first:
        return None
    try:
        h, m = SHIFT_START.split(":", 1)
        start = first.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
        return max(0, int((first - start).total_seconds() // 60))
    except Exception:
        return None


def period_days(start_day, end_day):
    start = date.fromisoformat(start_day)
    end = date.fromisoformat(end_day)
    while start <= end:
        yield start.isoformat()
        start += timedelta(days=1)


def period_people(start_day, end_day):
    result = {}
    for day in period_days(start_day, end_day):
        for person in all_people_today(day):
            key = person["id"]
            entry = result.setdefault(key, {
                "id": key, "name": person["name"], "days": 0, "worked": 0,
                "late_days": 0, "late_minutes": 0, "present_days": 0,
            })
            if person["name"]:
                entry["name"] = person["name"]
            entry["days"] += 1
            entry["worked"] += person["worked"]
            if person["present"]:
                entry["present_days"] += 1
            late = shift_late(person["first"])
            if late and late > 0:
                entry["late_days"] += 1
                entry["late_minutes"] += late
    return sorted(result.values(), key=lambda x: x["name"].lower())


def split_text(text, limit=3900):
    if len(text) <= limit:
        return [text]
    parts = []
    current = []
    length = 0
    for block in text.split("\n\n"):
        add = len(block) + (2 if current else 0)
        if current and length + add > limit:
            parts.append("\n\n".join(current))
            current = [block]
            length = len(block)
        else:
            current.append(block)
            length += add
    if current:
        parts.append("\n\n".join(current))
    return parts


def dashboard_text(day=None):
    day = day or now_local().strftime("%Y-%m-%d")
    people = all_people_today(day)
    present = [p for p in people if p["present"]]
    absent = [p for p in people if not p["present"]]
    lines = [
        f"📊 FUNLANDIA — {day}", "",
        f"👥 Всего отметились: {len(people)}",
        f"🟢 Сейчас на работе: {len(present)}",
        f"🔴 Уже ушли: {len(absent)}",
    ]
    if present:
        lines += ["", "🟢 СЕЙЧАС НА РАБОТЕ:"]
        lines += [f"• {p['name']} — с {fmt_hm(p['first'])}" for p in present]
    if absent:
        lines += ["", "🔴 УШЛИ:"]
        lines += [f"• {p['name']} — до {fmt_hm(p['last_exit'])}" for p in absent]
    return "\n".join(lines)


def period_report_text(start_day, end_day, title):
    people = period_people(start_day, end_day)
    if not people:
        return f"📊 {title}\n\nЗа этот период записей нет."
    total_hours = sum(p["worked"] for p in people)
    late_people = sum(1 for p in people if p["late_days"])
    lines = [
        f"📊 {title}",
        f"📅 {start_day} — {end_day}",
        "",
        f"👥 Сотрудников с отметками: {len(people)}",
        f"⏱ Общее отработанное время: {fmt_duration(total_hours)}",
        f"⚠️ Сотрудников с опозданиями: {late_people}",
        "",
    ]
    for p in people:
        late = f" | ⚠️ опозданий: {p['late_days']} ({p['late_minutes']} мин)" if p["late_days"] else ""
        lines.append(
            f"👤 {p['name']}\n"
            f"   Рабочих дней: {p['days']} | Отработано: {fmt_duration(p['worked'])}{late}"
        )
    return "\n\n".join(lines)


def current_week_range():
    today = now_local().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def current_month_range():
    today = now_local().date()
    first = today.replace(day=1)
    last = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    return first.isoformat(), last.isoformat()


async def send_long(update, text):
    for part in split_text(text):
        await update.message.reply_text(part, reply_markup=MENU)


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
        "Dahua подключается напрямую к боту.\n"
        "Здесь можно видеть присутствие, входы, выходы, недельные и месячные отчёты.",
        reply_markup=MENU,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ Возможности:\n\n"
        "📊 Сегодня — сколько сотрудников отметилось, кто сейчас на работе и кто уже ушёл.\n"
        "👥 Сейчас на работе — текущий список сотрудников.\n"
        "📅 Неделя — отчёт за текущую неделю.\n"
        "🗓 Месяц — отчёт за текущий месяц.\n"
        "👤 Мои записи — ваши входы и выходы за сегодня.\n"
        "📋 Мой отчёт — первый вход, последний выход, отработанное время и опоздание.\n\n"
        "Команды:\n"
        "/today — сводка за сегодня\n"
        "/week — отчёт за текущую неделю\n"
        "/month — отчёт за текущий месяц\n"
        "/report YYYY-MM-DD — общий отчёт за день\n"
        "/link ID — привязка Telegram к ID Dahua\n"
        "/last — последние события"
    )
    await update.message.reply_text(text, reply_markup=MENU)


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await my_report(update, context)
        return
    await update.message.reply_text(dashboard_text(), reply_markup=MENU)


async def presence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("🔒 Этот раздел доступен руководителю.", reply_markup=MENU)
        return
    await update.message.reply_text(dashboard_text(), reply_markup=MENU)


async def week_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("🔒 Недельный отчёт доступен руководителю.", reply_markup=MENU)
        return
    start_day, end_day = current_week_range()
    await send_long(update, period_report_text(start_day, end_day, "НЕДЕЛЬНЫЙ ОТЧЁТ СОТРУДНИКОВ"))


async def month_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("🔒 Месячный отчёт доступен руководителю.", reply_markup=MENU)
        return
    start_day, end_day = current_month_range()
    await send_long(update, period_report_text(start_day, end_day, "МЕСЯЧНЫЙ ОТЧЁТ СОТРУДНИКОВ"))


async def link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_CHAT_ID and not is_admin(update):
        await update.message.reply_text("🔒 Привязку сотрудника выполняет руководитель.", reply_markup=MENU)
        return
    if not context.args or not context.args[0].strip():
        await update.message.reply_text("Использование: /link ID\nНапример: /link 33", reply_markup=MENU)
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
    row = conn.execute(
        "SELECT user_name FROM attendance WHERE user_id=? AND user_name<>'' ORDER BY id DESC LIMIT 1",
        (dahua_id,),
    ).fetchone()
    conn.commit()
    conn.close()
    name = row["user_name"] if row else "сотрудник с этим ID"
    await update.message.reply_text(f"✅ Telegram привязан к {name} (ID {dahua_id}).", reply_markup=MENU)


async def my_records(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    user = conn.execute("SELECT dahua_user_id FROM telegram_users WHERE chat_id=?", (update.effective_chat.id,)).fetchone()
    conn.close()
    if not user or not user["dahua_user_id"]:
        await update.message.reply_text("Ваш Telegram пока не привязан. Руководитель может выполнить /link ID.", reply_markup=MENU)
        return
    day = now_local().strftime("%Y-%m-%d")
    rows = day_rows(day, user["dahua_user_id"])
    if not rows:
        await update.message.reply_text("📅 Сегодня записей пока нет.", reply_markup=MENU)
        return
    name = rows[-1]["user_name"] or user["dahua_user_id"]
    lines = [f"👤 {name}", f"📅 {day}", ""]
    for row in rows:
        typ = normalize_type(row["event_type"])
        label = "Вход" if typ == "Entry" else "Выход" if typ == "Exit" else "Отметка"
        lines.append(f"• {label}: {fmt_hm(parse_dt(row['event_time']))}")
    await update.message.reply_text("\n".join(lines), reply_markup=MENU)


async def my_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    user = conn.execute("SELECT dahua_user_id FROM telegram_users WHERE chat_id=?", (update.effective_chat.id,)).fetchone()
    conn.close()
    if not user or not user["dahua_user_id"]:
        if is_admin(update):
            await update.message.reply_text(dashboard_text(), reply_markup=MENU)
        else:
            await update.message.reply_text("Ваш Telegram пока не привязан. Руководитель может выполнить /link ID.", reply_markup=MENU)
        return
    day = now_local().strftime("%Y-%m-%d")
    rows = day_rows(day, user["dahua_user_id"])
    state = staff_state(rows)
    name = rows[-1]["user_name"] if rows else user["dahua_user_id"]
    late = shift_late(state["first"])
    lines = [
        f"📋 МОЙ ОТЧЁТ — {day}", f"👤 {name}", "",
        f"🟢 Первый вход: {fmt_hm(state['first'])}",
        f"🔴 Последний выход: {fmt_hm(state['last_exit'])}",
        f"⏱ Отработано: {fmt_duration(state['worked'])}",
        f"📍 Статус: {'НА РАБОТЕ' if state['present'] else 'УШЁЛ'}",
    ]
    if late is not None and late > 0:
        lines.append(f"⚠️ Опоздание: {late} мин")
    elif late == 0:
        lines.append("✅ Опоздания нет")
    await update.message.reply_text("\n".join(lines), reply_markup=MENU)


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await my_report(update, context)
        return
    day = context.args[0] if context.args else now_local().strftime("%Y-%m-%d")
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("Формат даты: /report 2026-09-12", reply_markup=MENU)
        return
    people = all_people_today(day)
    if not people:
        await update.message.reply_text(f"📊 За {day} записей нет.", reply_markup=MENU)
        return
    lines = [f"📊 ОТЧЁТ СОТРУДНИКОВ — {day}", ""]
    for p in people:
        late = shift_late(p["first"])
        late_text = f", опоздание {late} мин" if late else ""
        status = "🟢 на работе" if p["present"] else "🔴 ушёл"
        lines.append(
            f"{status} — {p['name']}\n"
            f"   Вход: {fmt_hm(p['first'])} | Выход: {fmt_hm(p['last_exit'])} | "
            f"Время: {fmt_duration(p['worked'])}{late_text}"
        )
    await send_long(update, "\n".join(lines))


async def last_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("🔒 Этот раздел доступен руководителю.", reply_markup=MENU)
        return
    conn = db()
    rows = conn.execute("SELECT * FROM attendance ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("Событий пока нет.", reply_markup=MENU)
        return
    lines = ["🕘 ПОСЛЕДНИЕ СОБЫТИЯ:"]
    for row in rows:
        dt = parse_dt(row["event_time"])
        typ = normalize_type(row["event_type"])
        label = "Вход" if typ == "Entry" else "Выход" if typ == "Exit" else "Отметка"
        lines.append(f"• {fmt_hm(dt)} — {row['user_name'] or row['user_id']} — {label}")
    await update.message.reply_text("\n".join(lines), reply_markup=MENU)


async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text == "📊 Сегодня":
        await today(update, context)
    elif text == "👥 Сейчас на работе":
        await presence(update, context)
    elif text == "📅 Неделя":
        await week_report(update, context)
    elif text == "🗓 Месяц":
        await month_report(update, context)
    elif text == "👤 Мои записи":
        await my_records(update, context)
    elif text == "📋 Мой отчёт":
        await my_report(update, context)
    elif text == "ℹ️ Помощь":
        await help_command(update, context)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    init_db()
    threading.Thread(target=run_http_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("week", week_report))
    app.add_handler(CommandHandler("month", month_report))
    app.add_handler(CommandHandler("link", link))
    app.add_handler(CommandHandler("me", my_records))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("last", last_events))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_router))

    logger.info("FUNLANDIA STAFF BOT STARTED")
    logger.info("Dahua HTTP Push endpoint: /dahua and /GeneralHttpUpload")
    logger.info("SHIFT_START=%s ADMIN_CHAT_ID=%s", SHIFT_START, "configured" if ADMIN_CHAT_ID else "not configured")
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
