import os, json, re, sqlite3, hashlib, logging, threading, calendar, socket
from datetime import datetime, timezone, timedelta, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as ET
import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("funlandia_staff")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("STAFF_DB_PATH", "staff_attendance.db")
ADMIN_CHAT_ID = os.getenv("STAFF_ADMIN_CHAT_ID", os.getenv("ADMIN_CHAT_ID", "")).strip()
SHIFT_START = os.getenv("SHIFT_START", "09:00")
TZ = timezone(timedelta(hours=5))

MENU = ReplyKeyboardMarkup([
    ["📊 Сегодня", "👥 Сейчас на работе"],
    ["📅 Неделя", "🗓 Месяц"],
    ["👤 Мои записи", "📋 Мой отчёт"],
    ["ℹ️ Помощь"]
], resize_keyboard=True)

SUCCESS = {"", "1", "true", "success", "succeeded", "ok", "completed", "выполнено", "успешно"}


def now():
    return datetime.now(TZ)


def db():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS attendance(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_key TEXT UNIQUE NOT NULL,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        event_time TEXT NOT NULL,
        event_type TEXT NOT NULL,
        status TEXT NOT NULL,
        source TEXT NOT NULL,
        raw_payload TEXT NOT NULL,
        created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS telegram_users(
        chat_id INTEGER PRIMARY KEY,
        dahua_user_id TEXT,
        username TEXT,
        first_name TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_att_time ON attendance(event_time)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_att_user ON attendance(user_id,event_time)")
    c.commit(); c.close()


def parse_time(v):
    if v is None or str(v).strip() == "":
        return now().isoformat()
    s = str(v).strip()
    if re.fullmatch(r"\d{9,13}", s):
        try:
            n = int(s); n = n / 1000 if n > 10_000_000_000 else n
            return datetime.fromtimestamp(n, timezone.utc).astimezone(TZ).isoformat()
        except Exception: pass
    s = s.replace("Z", "+00:00")
    for x in (s, s.replace("/", "-")):
        try:
            d = datetime.fromisoformat(x)
            if d.tzinfo is None: d = d.replace(tzinfo=TZ)
            return d.astimezone(TZ).isoformat()
        except Exception: pass
    for f in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try: return datetime.strptime(s, f).replace(tzinfo=TZ).isoformat()
        except Exception: pass
    return now().isoformat()


def pick(d, *keys):
    if not isinstance(d, dict): return ""
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip() != "": return v
    return ""


def collect_dicts(x):
    out = []
    if isinstance(x, dict):
        out.append(x)
        for v in x.values():
            if isinstance(v, (dict, list)): out.extend(collect_dicts(v))
    elif isinstance(x, list):
        for v in x: out.extend(collect_dicts(v))
    return out


def normalize(payload):
    ds = collect_dicts(payload)
    uid = name = tm = typ = status = rec = method = ""
    for d in ds:
        uid = uid or str(pick(d, "UserID", "userId", "user_id", "PersonID", "personId", "personCode", "EmployeeID", "CardNo", "No"))
        name = name or str(pick(d, "CardName", "UserName", "userName", "user_name", "PersonName", "personName", "Name", "name"))
        tm = tm or str(pick(d, "CreateTime", "EventTime", "eventTime", "Time", "time", "alarmDate", "DateTime"))
        typ = typ or str(pick(d, "Type", "EventType", "eventType", "event_type", "InOut", "inOut", "Direction", "direction", "OperateType", "operateType"))
        status = status or str(pick(d, "Status", "Result", "result", "ErrorCode", "errorCode", "syncFlags"))
        rec = rec or str(pick(d, "RecNo", "RecordNo", "recordNo", "Sequence", "seq"))
        method = method or str(pick(d, "Method", "method", "OpenMethod", "openMethod"))
    return {"user_id":uid.strip(), "user_name":name.strip(), "event_time":parse_time(tm), "type_raw":typ.strip(), "status":status.strip(), "rec_no":rec.strip(), "method":method.strip()}


def event_type(info):
    s = (info.get("type_raw") or "").lower().strip()
    if s in {"1", "in", "entry", "entrance", "вход", "входить"} or "entry" in s or "вход" in s: return "Вход"
    if s in {"2", "out", "exit", "выход"} or "exit" in s or "выход" in s: return "Выход"
    return ""


def successful(info):
    s = str(info.get("status", "")).lower().strip()
    if not s: return True
    if s in SUCCESS: return True
    if s in {"0", "false", "fail", "failed", "error", "denied", "нет разрешения", "не выполнено"}: return False
    # Dahua ErrorCode 0 is normally success; non-zero is failure.
    if re.fullmatch(r"-?\d+", s): return int(s) == 0
    return True


def infer_type(user_id, explicit):
    if explicit: return explicit
    c = db(); r = c.execute("SELECT event_type FROM attendance WHERE user_id=? ORDER BY event_time DESC,id DESC LIMIT 1", (user_id,)).fetchone(); c.close()
    if r and r["event_type"] == "Вход": return "Выход"
    return "Вход"


def telegram_send(chat_id, text):
    if not BOT_TOKEN or not chat_id: return
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id":int(chat_id),"text":text}, timeout=8)
        if r.status_code != 200: log.warning("Telegram sendMessage HTTP %s", r.status_code)
    except Exception as e: log.warning("Telegram notification failed: %s", e)


def notify(info, etype):
    c = db(); rows = c.execute("SELECT chat_id FROM telegram_users WHERE dahua_user_id=?", (info["user_id"],)).fetchall(); c.close()
    if not rows: return
    icon = "🟢" if etype == "Вход" else "🔴"
    tm = datetime.fromisoformat(info["event_time"]).strftime("%d.%m.%Y %H:%M:%S")
    method = f"\nМетод: {info['method']}" if info.get("method") else ""
    text = f"{icon} {etype.upper()}\n\n👤 {info['user_name'] or info['user_id']}\n🆔 ID: {info['user_id']}\n🕐 {tm}{method}"
    for r in rows: threading.Thread(target=telegram_send, args=(r["chat_id"], text), daemon=True).start()


def save_payload(payload):
    info = normalize(payload)
    # DoorStatus/Pulse and other technical heartbeats are deliberately ignored as attendance.
    raw_text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    low = raw_text.lower()
    if not info["user_id"] and not info["user_name"]: return False, info, "ignored_no_person"
    if "doorstatus" in low and not any(k in low for k in ("userid", "username", "personname", "cardname")): return False, info, "ignored_door_status"
    if not successful(info): return False, info, "ignored_failed"
    etype = event_type(info)
    if not etype: etype = infer_type(info["user_id"], "")
    base = "|".join([info["rec_no"], info["user_id"], info["user_name"], info["event_time"], etype, info["method"]])
    key = hashlib.sha256((base + "|" + raw_text).encode()).hexdigest()
    c = db()
    cur = c.execute("""INSERT OR IGNORE INTO attendance
        (event_key,user_id,user_name,event_time,event_type,status,source,raw_payload,created_at)
        VALUES(?,?,?,?,?,?,?,?,?)""", (key,info["user_id"],info["user_name"],info["event_time"],etype,info["status"],"dahua_http_push",raw_text,now().isoformat()))
    inserted = cur.rowcount == 1; c.commit(); c.close()
    if inserted: notify(info, etype)
    info["event_type"] = etype
    return inserted, info, "inserted" if inserted else "duplicate"


def parse_xml(raw):
    try:
        root = ET.fromstring(raw.decode("utf-8", "replace")); out = {}
        for e in root.iter():
            if e is not root and (e.text or "").strip(): out[e.tag.split("}")[-1]] = e.text.strip()
        return out
    except Exception: return {}


def parse_body(raw, ct):
    if not raw: return {}
    s = raw.decode("utf-8", "replace").strip(); ct = (ct or "").lower()
    if "json" in ct or s.startswith("{") or s.startswith("["):
        try: return json.loads(s)
        except Exception: pass
    if "xml" in ct or s.startswith("<"):
        x = parse_xml(raw)
        if x: return x
    if "multipart/" in ct:
        for part in re.split(r"\r?\n--[^\r\n]+", s):
            p = part.split("\r\n\r\n", 1)[-1].strip()
            if p.startswith("{"):
                try: return json.loads(p)
                except Exception: pass
    q = parse_qs(s, keep_blank_values=True)
    if q: return {k:v[-1] for k,v in q.items()}
    out = {}
    for line in s.splitlines():
        if "=" in line:
            k,v=line.split("=",1); out[k.strip()]=v.strip()
    return out or {"raw":s[:10000]}


def payload_list(p):
    if isinstance(p, list): return [x for x in p if isinstance(x, dict)]
    if not isinstance(p, dict): return []
    for k in ("events", "Events", "records", "Records", "data", "Data"):
        if isinstance(p.get(k), list): return [x for x in p[k] if isinstance(x, dict)]
    return [p]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "FUNLANDIA-STAFF/3.0"
    def reply(self, code=200, text="OK"):
        b=text.encode()
        try:
            self.send_response(code); self.send_header("Content-Type","text/plain; charset=utf-8"); self.send_header("Content-Length",str(len(b))); self.send_header("Connection","close"); self.end_headers(); self.wfile.write(b); self.wfile.flush()
        except Exception: pass
    def read_body(self):
        te=self.headers.get("Transfer-Encoding","").lower()
        if "chunked" in te:
            data=b""
            while True:
                line=self.rfile.readline().strip()
                if not line: continue
                try:n=int(line.split(b";",1)[0],16)
                except Exception: break
                if n==0: self.rfile.readline(); break
                data += self.rfile.read(n); self.rfile.readline()
            return data
        try:n=int(self.headers.get("Content-Length","0") or 0)
        except Exception:n=0
        if n<=0:return b""
        data=b""; old=self.connection.gettimeout()
        try:
            self.connection.settimeout(10)
            while len(data)<n:
                part=self.rfile.read(n-len(data))
                if not part:break
                data+=part
        except Exception as e: log.warning("Dahua body read: %s",e)
        finally:
            try:self.connection.settimeout(old)
            except Exception:pass
        return data
    def handle_payload(self, raw):
        p=parse_body(raw,self.headers.get("Content-Type","")) if raw else {}
        total=0
        for item in payload_list(p):
            ins,info,reason=save_payload(item)
            if info.get("user_id") or info.get("user_name"):
                log.info("DAHUA EVENT %s id=%s name=%s time=%s type=%s",reason,info.get("user_id"),info.get("user_name"),info.get("event_time"),info.get("event_type"))
            total += int(ins)
        return total
    def do_GET(self):
        path=urlparse(self.path).path
        log.info("DAHUA GET %s",path)
        self.reply(200,"FUNLANDIA STAFF OK")
    def do_POST(self):
        try:
            raw=self.read_body(); path=urlparse(self.path).path
            log.info("DAHUA POST path=%s ct=%s bytes=%s preview=%r",path,self.headers.get("Content-Type",""),len(raw),raw[:1200].decode("utf-8","replace"))
            n=self.handle_payload(raw) if "keepalive" not in path.lower() else 0
            log.info("DAHUA PUSH path=%s new-events=%s",path,n)
            self.reply(200,"OK")
        except Exception as e:
            log.exception("Dahua webhook error: %s",e); self.reply(200,"OK")
    def log_message(self,*args): pass


def server():
    s=ThreadingHTTPServer(("0.0.0.0",PORT),Handler); log.info("Dahua HTTP server listening on %s",PORT); s.serve_forever()


def is_admin(u): return bool(ADMIN_CHAT_ID and str(u.effective_chat.id)==ADMIN_CHAT_ID)

def linked(chat_id):
    c=db(); r=c.execute("SELECT dahua_user_id FROM telegram_users WHERE chat_id=?",(chat_id,)).fetchone(); c.close(); return r["dahua_user_id"] if r else None

def parse_dt(s):
    try:return datetime.fromisoformat(s)
    except Exception:return None

def day_rows(day, uid=None):
    c=db(); q="SELECT * FROM attendance WHERE event_time LIKE ?"; a=[day+"%"]
    if uid:q+=" AND user_id=?"; a.append(str(uid))
    rows=c.execute(q+" ORDER BY event_time,id",a).fetchall(); c.close(); return rows

def state(rows):
    present=False; opened=None; first=None; last=None; worked=0
    for r in rows:
        d=parse_dt(r["event_time"])
        if not d:continue
        if r["event_type"]=="Вход":
            if first is None:first=d
            if opened is None:opened=d
            present=True
        elif r["event_type"]=="Выход":
            last=d
            if opened and d>=opened:worked+=int((d-opened).total_seconds())
            opened=None; present=False
    if opened:worked+=max(0,int((now()-opened).total_seconds()))
    return present,first,last,worked

def dur(sec):
    h,m=divmod(max(0,int(sec)),3600); m//=60
    return f"{h} ч {m:02d} мин" if h else f"{m} мин"

def people(day):
    c=db(); rows=c.execute("SELECT * FROM attendance WHERE event_time LIKE ? ORDER BY event_time,id",(day+"%",)).fetchall(); c.close(); g={}
    for r in rows:g.setdefault(r["user_id"],[]).append(r)
    out=[]
    for uid,rs in g.items():
        p,f,l,w=state(rs); out.append((uid,rs[-1]["user_name"] or uid,p,f,l,w))
    return out

def ranges():
    t=now().date(); m=t-timedelta(days=t.weekday()); last=calendar.monthrange(t.year,t.month)[1]
    return m,(m+timedelta(days=6)),t.replace(day=1),t.replace(day=last)

async def start(u,c):
    x=u.effective_user; t=now().isoformat(); con=db(); con.execute("""INSERT INTO telegram_users(chat_id,username,first_name,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,updated_at=excluded.updated_at""",(u.effective_chat.id,x.username if x else "",x.first_name if x else "",t,t)); con.commit(); con.close()
    await u.message.reply_text("👷 FUNLANDIA — БОТ СОТРУДНИКОВ\n\nDahua подключен напрямую.\nПривяжите Telegram к ID Dahua командой /link ID.",reply_markup=MENU)

async def link(u,c):
    if ADMIN_CHAT_ID and not is_admin(u):return await u.message.reply_text("🔒 Привязку выполняет руководитель.",reply_markup=MENU)
    if not c.args:return await u.message.reply_text("Использование: /link ID",reply_markup=MENU)
    uid=c.args[0].strip(); x=u.effective_user; t=now().isoformat(); con=db(); con.execute("""INSERT INTO telegram_users(chat_id,dahua_user_id,username,first_name,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET dahua_user_id=excluded.dahua_user_id,updated_at=excluded.updated_at""",(u.effective_chat.id,uid,x.username if x else "",x.first_name if x else "",t,t)); r=con.execute("SELECT user_name FROM attendance WHERE user_id=? ORDER BY id DESC LIMIT 1",(uid,)).fetchone(); con.commit(); con.close(); await u.message.reply_text(f"✅ Telegram привязан к {r['user_name'] if r else uid} (ID {uid}).",reply_markup=MENU)

async def today_cmd(u,c): await u.message.reply_text(dashboard(),reply_markup=MENU)

def dashboard():
    day=now().date().isoformat(); ps=people(day); current=[x for x in ps if x[2]]
    lines=[f"📊 FUNLANDIA — {day}","",f"👥 Отметились: {len(ps)}",f"🟢 Сейчас на работе: {len(current)}"]
    if current:lines += ["","🟢 СЕЙЧАС"]+[f"• {x[1]} — с {x[3].strftime('%H:%M') if x[3] else '—'}" for x in current]
    return "\n".join(lines)

async def current_cmd(u,c): await u.message.reply_text(dashboard(),reply_markup=MENU)

async def me_cmd(u,c):
    uid=linked(u.effective_chat.id)
    if not uid:return await u.message.reply_text("⚠️ Telegram ещё не привязан. Используйте /link ID.",reply_markup=MENU)
    rows=day_rows(now().date().isoformat(),uid)
    if not rows:return await u.message.reply_text("📋 Сегодня записей нет.",reply_markup=MENU)
    lines=[f"👤 {rows[-1]['user_name'] or uid}",""]
    for r in rows:lines.append(f"{'🟢' if r['event_type']=='Вход' else '🔴'} {r['event_type']} — {parse_dt(r['event_time']).strftime('%H:%M:%S') if parse_dt(r['event_time']) else r['event_time']}")
    p,f,l,w=state(rows); lines += ["",f"⏱ Отработано: {dur(w)}",f"📍 Статус: {'НА РАБОТЕ' if p else 'НЕ НА РАБОТЕ'}"]
    await u.message.reply_text("\n".join(lines),reply_markup=MENU)

async def report_cmd(u,c):
    uid=linked(u.effective_chat.id)
    if not uid:return await u.message.reply_text("⚠️ Сначала /link ID.",reply_markup=MENU)
    ps=[]; d=now().date(); start=d-timedelta(days=6)
    total=0; days=0
    x=start
    while x<=d:
        rs=day_rows(x.isoformat(),uid)
        if rs:
            p,f,l,w=state(rs); total+=w; days+=1; ps.append((x,f,l,w))
        x+=timedelta(days=1)
    if not ps:return await u.message.reply_text("📋 За последние 7 дней записей нет.",reply_markup=MENU)
    lines=["📋 МОЙ ОТЧЁТ",f"Рабочих дней: {days}",f"Отработано: {dur(total)}",""]
    for d,f,l,w in ps:lines.append(f"{d.strftime('%d.%m')} — {f.strftime('%H:%M') if f else '—'} / {l.strftime('%H:%M') if l else '—'} — {dur(w)}")
    await u.message.reply_text("\n".join(lines),reply_markup=MENU)

async def period_cmd(u,c,kind):
    if not is_admin(u):return await u.message.reply_text("🔒 Отчёт доступен руководителю.",reply_markup=MENU)
    t=now().date(); start=t-timedelta(days=t.weekday()) if kind=='week' else t.replace(day=1); end=t
    groups={}; d=start
    while d<=end:
        for uid,name,p,f,l,w in people(d.isoformat()):
            z=groups.setdefault(uid,[name,0,0,0]); z[0]=name; z[1]+=1; z[2]+=w
            if f:
                try:
                    h,m=map(int,SHIFT_START.split(':')); z[3]+=max(0,int((f.replace(hour=h,minute=m,second=0,microsecond=0)-f).total_seconds()//60))
                except Exception:pass
        d+=timedelta(days=1)
    title='НЕДЕЛЬНЫЙ' if kind=='week' else 'МЕСЯЧНЫЙ'; lines=[f"📊 {title} ОТЧЁТ",f"{start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')}",""]
    if not groups:lines.append("Записей нет.")
    for uid,(name,days,w,late) in sorted(groups.items(),key=lambda x:x[1][0].lower()):lines += [f"👤 {name}",f"   Дней: {days} | Время: {dur(w)}"+(f" | Опоздание: {late} мин" if late else ""),""]
    await u.message.reply_text("\n".join(lines).strip(),reply_markup=MENU)

async def help_cmd(u,c): await u.message.reply_text("ℹ️ Команды:\n/link ID — привязать Telegram к сотруднику Dahua\n/today — сегодня\n/me — мои записи\n/report — мой отчёт\n\nРуководитель: /week и /month",reply_markup=MENU)

async def buttons(u,c):
    t=u.message.text
    if t=="📊 Сегодня":return await today_cmd(u,c)
    if t=="👥 Сейчас на работе":return await current_cmd(u,c)
    if t=="👤 Мои записи":return await me_cmd(u,c)
    if t=="📋 Мой отчёт":return await report_cmd(u,c)
    if t=="📅 Неделя":return await period_cmd(u,c,'week')
    if t=="🗓 Месяц":return await period_cmd(u,c,'month')
    if t=="ℹ️ Помощь":return await help_cmd(u,c)


def main():
    if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN is not set")
    init_db(); threading.Thread(target=server,daemon=True,name='dahua-http').start()
    app=Application.builder().token(BOT_TOKEN).build()
    for cmd,fn in [('start',start),('link',link),('today',today_cmd),('me',me_cmd),('report',report_cmd),('help',help_cmd)]:app.add_handler(CommandHandler(cmd,fn))
    app.add_handler(CommandHandler('week',lambda u,c: period_cmd(u,c,'week')))
    app.add_handler(CommandHandler('month',lambda u,c: period_cmd(u,c,'month')))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,buttons))
    log.info('FUNLANDIA STAFF BOT 3.0 STARTED')
    app.run_polling(drop_pending_updates=False)

if __name__=='__main__': main()
