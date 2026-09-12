import os, re, json, hashlib, logging, sqlite3, threading, calendar, socket
from datetime import datetime, timezone, timedelta, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("funlandia_staff")

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("STAFF_DB_PATH", "staff_attendance.db")
ADMIN_CHAT_ID = os.getenv("STAFF_ADMIN_CHAT_ID") or os.getenv("ADMIN_CHAT_ID", "")
SHIFT_START = os.getenv("SHIFT_START", "09:00")
LOCAL_TZ = timezone(timedelta(hours=5))

MENU = ReplyKeyboardMarkup([
    ["📊 Сегодня", "👥 Сейчас на работе"],
    ["📅 Неделя", "🗓 Месяц"],
    ["👤 Мои записи", "📋 Мой отчёт"],
    ["ℹ️ Помощь"],
], resize_keyboard=True)

SUCCESS = ("", "1", "true", "success", "succeeded", "ok", "выполнено")

def db():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS attendance(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_key TEXT UNIQUE, user_id TEXT, user_name TEXT,
        event_time TEXT NOT NULL, event_type TEXT, status TEXT,
        source TEXT DEFAULT 'dahua_http_push', raw_payload TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS telegram_users(
        chat_id INTEGER PRIMARY KEY, dahua_user_id TEXT, username TEXT,
        first_name TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_attendance_time ON attendance(event_time)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_attendance_user ON attendance(user_id,event_time)")
    c.commit(); c.close()

def now_local(): return datetime.now(LOCAL_TZ)

def parse_time(v):
    if v in (None, ""): return now_local().isoformat()
    s = str(v).strip()
    if s.isdigit():
        try: return datetime.fromtimestamp(int(s), timezone.utc).astimezone(LOCAL_TZ).isoformat()
        except Exception: pass
    s = s.replace("Z", "+00:00")
    for x in (s, s.replace("/", "-")):
        try:
            d = datetime.fromisoformat(x)
            if d.tzinfo is None: d = d.replace(tzinfo=LOCAL_TZ)
            return d.astimezone(LOCAL_TZ).isoformat()
        except Exception: pass
    for f in ("%Y-%m-%d %H:%M:%S","%Y/%m/%d %H:%M:%S","%Y-%m-%dT%H:%M:%S"):
        try: return datetime.strptime(s,f).replace(tzinfo=LOCAL_TZ).isoformat()
        except Exception: pass
    return now_local().isoformat()

def first(d, *keys):
    if not isinstance(d, dict): return ""
    for k in keys:
        if d.get(k) not in (None, ""): return d[k]
    return ""

def flatten(d):
    if not isinstance(d, dict):
        return {"user_id":"","user_name":"","event_time":parse_time(""),"event_type":"","status":"","rec_no":""}
    cand = [d]
    for k in ("data","Data","event","Event","record","Record","params","paramsData","info","Info"):
        v = d.get(k)
        if isinstance(v, dict): cand.append(v)
        elif isinstance(v, list): cand += [x for x in v if isinstance(x,dict)]
    for _,v in list(d.items()):
        if isinstance(v,str) and v.strip().startswith("{"):
            try:
                q=json.loads(v); cand.append(q if isinstance(q,dict) else {})
            except Exception: pass
    uid=name=tm=typv=status=rec=""
    for x in cand:
        uid = uid or str(first(x,"UserID","user_id","userId","personCode","ID","id","No"))
        name = name or str(first(x,"CardName","UserName","user_name","userIdName","personName","name","Name"))
        tm = tm or str(first(x,"CreateTime","EventTime","event_time","alarmDate","Time","time"))
        typv = typv or str(first(x,"Type","EventType","event_type","Action","action","operateType"))
        status = status or str(first(x,"Status","status","Result","result","ErrorCode","syncFlags"))
        rec = rec or str(first(x,"RecNo","RecordNo","recordNo","id"))
    return {"user_id":uid.strip(),"user_name":name.strip(),"event_time":parse_time(tm),"event_type":typv.strip(),"status":status.strip(),"rec_no":rec.strip()}

def save_event(payload):
    info=flatten(payload)
    if not info["user_id"] and not info["user_name"]: return False,info
    raw=json.dumps(payload,ensure_ascii=False,default=str,sort_keys=True)
    base="|".join(info[k] for k in ("rec_no","user_id","user_name","event_time","event_type","status"))
    key=hashlib.sha256((base+"|"+raw).encode()).hexdigest()
    c=db()
    cur=c.execute("""INSERT OR IGNORE INTO attendance
        (event_key,user_id,user_name,event_time,event_type,status,source,raw_payload)
        VALUES(?,?,?,?,?,?,?,?)""",
        (key,info["user_id"],info["user_name"],info["event_time"],info["event_type"],info["status"],"dahua_http_push",raw))
    ins=cur.rowcount==1; c.commit(); c.close(); return ins,info

def xml_dict(raw):
    try: root=ET.fromstring(raw.decode("utf-8","replace"))
    except Exception: return {}
    out={}
    for e in root.iter():
        if e is not root and (e.text or "").strip(): out[e.tag.split("}")[-1]]=(e.text or "").strip()
    return out

def parse_text(s):
    out={}
    for line in re.split(r"\r?\n",s):
        line=line.strip()
        if "=" in line:
            k,v=line.split("=",1); out[k.strip()]=v.strip()
    return out

def parse_body(raw,ct=""):
    if not raw: return {}
    s=raw.decode("utf-8","replace").strip(); ct=(ct or "").lower()
    if "json" in ct or s.startswith("{") or s.startswith("["):
        try: return json.loads(s)
        except Exception: pass
    if "xml" in ct or s.startswith("<"):
        x=xml_dict(raw)
        if x:return x
    if "multipart/" in ct:
        for p in re.split(rb"\r?\n--[^\r\n]+",raw):
            pos=p.find(b"\r\n\r\n"); step=4
            if pos<0: pos=p.find(b"\n\n"); step=2
            if pos>=0:
                b=p[pos+step:].strip()
                if b.startswith(b"{"):
                    try:return json.loads(b.decode("utf-8","replace"))
                    except Exception:pass
                x=parse_text(b.decode("utf-8","replace"))
                if x:return x
        return {"raw":s[:20000]}
    q=parse_qs(s,keep_blank_values=True)
    if q:return {k:(v[-1] if v else "") for k,v in q.items()}
    return parse_text(s) or {"raw":s[:20000]}

def payloads(p):
    if not isinstance(p,dict): return []
    for k in ("events","Events","records","Records"):
        if isinstance(p.get(k),list): return [x for x in p[k] if isinstance(x,dict)]
    return [p]

def typ(v):
    s=str(v or "").strip().lower()
    if s in ("entry","вход","in","1"): return "Entry"
    if s in ("exit","выход","out","2"): return "Exit"
    return ""

def ok(v): return str(v or "").strip().lower() in SUCCESS

def dt(v):
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except Exception:return None

def day_rows(day,uid=None):
    c=db(); w=["event_time LIKE ?"]; a=[day+"%"]
    w.append("(status IS NULL OR status='' OR lower(status) IN ("+",".join("?" for _ in SUCCESS)+"))"); a += list(SUCCESS)
    if uid: w.append("user_id=?"); a.append(str(uid))
    rows=c.execute("SELECT * FROM attendance WHERE "+" AND ".join(w)+" ORDER BY event_time,id",a).fetchall(); c.close(); return rows

def state(rows):
    ev=[r for r in rows if ok(r["status"])]
    present=False; first_in=None; last_out=None; worked=0; opened=None
    directional=any(typ(r["event_type"]) for r in ev)
    for r in ev:
        d=dt(r["event_time"]); t=typ(r["event_type"])
        if not d: continue
        if t=="Entry":
            if first_in is None:first_in=d
            if opened is None:opened=d
            present=True
        elif t=="Exit":
            last_out=d
            if opened and d>=opened: worked+=int((d-opened).total_seconds()); opened=None
            present=False
        elif not directional:
            if first_in is None:first_in=d
            if present:
                last_out=d
                if opened and d>=opened: worked+=int((d-opened).total_seconds())
                opened=None; present=False
            else: opened=d; present=True
    if opened: worked+=max(0,int((now_local()-opened).total_seconds()))
    return {"present":present,"first":first_in,"last_exit":last_out,"worked":worked,"events":ev}

def people_day(day):
    groups={}
    for r in day_rows(day): groups.setdefault(str(r["user_id"] or r["user_name"] or "?"),[]).append(r)
    out=[]
    for uid,rs in groups.items():
        s=state(rs); out.append({"id":uid,"name":rs[-1]["user_name"] or uid,**s})
    out.sort(key=lambda x:(not x["present"],x["name"].lower())); return out

def late(first_in):
    if not first_in:return None
    try:
        h,m=map(int,SHIFT_START.split(":")); start=first_in.replace(hour=h,minute=m,second=0,microsecond=0)
        return max(0,int((first_in-start).total_seconds()//60))
    except Exception:return None

def fmt_time(d): return d.strftime("%H:%M") if d else "—"
def fmt_dur(s):
    h,m=divmod(max(0,int(s or 0)),3600); m//=60
    return f"{h} ч {m:02d} мин" if h else f"{m} мин"

def ranges():
    t=now_local().date(); mon=t-timedelta(days=t.weekday())
    return mon.isoformat(),(mon+timedelta(days=6)).isoformat(),t.replace(day=1).isoformat(),t.replace(day=calendar.monthrange(t.year,t.month)[1]).isoformat()

def period(start,end):
    out={}; d=date.fromisoformat(start); e=date.fromisoformat(end)
    while d<=e:
        for p in people_day(d.isoformat()):
            x=out.setdefault(p["id"],{"id":p["id"],"name":p["name"],"days":0,"worked":0,"late_days":0,"late_minutes":0})
            x["name"]=p["name"]; x["days"]+=1; x["worked"]+=p["worked"]; l=late(p["first"])
            if l and l>0:x["late_days"]+=1; x["late_minutes"]+=l
        d+=timedelta(days=1)
    return sorted(out.values(),key=lambda x:x["name"].lower())

def dashboard(day=None):
    day=day or now_local().strftime("%Y-%m-%d"); ps=people_day(day); pr=[p for p in ps if p["present"]]
    lines=[f"📊 FUNLANDIA — {day}","",f"👥 Всего отметились: {len(ps)}",f"🟢 Сейчас на работе: {len(pr)}",f"🔴 Уже ушли: {len(ps)-len(pr)}"]
    if pr: lines += ["","🟢 СЕЙЧАС НА РАБОТЕ"]+[f"• {p['name']} — с {fmt_time(p['first'])}" for p in pr]
    gone=[p for p in ps if not p["present"]]
    if gone: lines += ["","🔴 УШЛИ"]+[f"• {p['name']} — до {fmt_time(p['last_exit'])}" for p in gone]
    return "\n".join(lines)

def report_period(start,end,title):
    ps=period(start,end)
    if not ps:return f"📊 {title}\n\nЗа этот период записей нет."
    total=sum(p["worked"] for p in ps); late_count=sum(bool(p["late_days"]) for p in ps)
    lines=[f"📊 {title}",f"📅 {start} — {end}","",f"👥 Сотрудников с отметками: {len(ps)}",f"⏱ Общее отработанное время: {fmt_dur(total)}",f"⚠️ Сотрудников с опозданиями: {late_count}",""]
    for p in ps:
        z=f" | ⚠️ опозданий: {p['late_days']} ({p['late_minutes']} мин)" if p["late_days"] else ""
        lines += [f"👤 {p['name']}",f"   Рабочих дней: {p['days']} | Отработано: {fmt_dur(p['worked'])}{z}",""]
    return "\n".join(lines).strip()

def admin(u): return bool(ADMIN_CHAT_ID and str(u.effective_chat.id)==str(ADMIN_CHAT_ID))

async def send_long(u,text):
    for i in range(0,len(text),3900): await u.message.reply_text(text[i:i+3900],reply_markup=MENU)

async def start(u,c):
    now=now_local().isoformat(); x=u.effective_user; con=db()
    con.execute("""INSERT INTO telegram_users(chat_id,username,first_name,created_at,updated_at)
        VALUES(?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,updated_at=excluded.updated_at""",
        (u.effective_chat.id,x.username if x else "",x.first_name if x else "",now,now)); con.commit(); con.close()
    await u.message.reply_text("👷 FUNLANDIA — БОТ СОТРУДНИКОВ\n\nDahua подключается напрямую.\nДоступны присутствие и отчёты за день, неделю и месяц.",reply_markup=MENU)

async def help_cmd(u,c):
    await u.message.reply_text("ℹ️ Меню:\n📊 Сегодня — сводка\n👥 Сейчас на работе — кто внутри\n📅 Неделя / 🗓 Месяц — отчёты руководителя\n👤 Мои записи — отметки сотрудника\n📋 Мой отчёт — личная сводка\n\nДля привязки: руководитель использует /link ID",reply_markup=MENU)

async def today_cmd(u,c): await u.message.reply_text(dashboard(),reply_markup=MENU)

async def presence(u,c):
    ps=[p for p in people_day(now_local().strftime("%Y-%m-%d")) if p["present"]]
    text="👥 СЕЙЧАС НА РАБОТЕ\n\n"+("\n".join(f"• {p['name']} — с {fmt_time(p['first'])}" for p in ps) if ps else "Сейчас никто не отмечен на работе.")
    await u.message.reply_text(text,reply_markup=MENU)

async def week(u,c):
    if not admin(u): return await u.message.reply_text("🔒 Недельный отчёт доступен руководителю.",reply_markup=MENU)
    a,b,_,_=ranges(); await send_long(u,report_period(a,b,"НЕДЕЛЬНЫЙ ОТЧЁТ СОТРУДНИКОВ"))

async def month(u,c):
    if not admin(u): return await u.message.reply_text("🔒 Месячный отчёт доступен руководителю.",reply_markup=MENU)
    _,_,a,b=ranges(); await send_long(u,report_period(a,b,"МЕСЯЧНЫЙ ОТЧЁТ СОТРУДНИКОВ"))

def linked(chat):
    c=db(); r=c.execute("SELECT dahua_user_id FROM telegram_users WHERE chat_id=?",(chat,)).fetchone(); c.close()
    return r["dahua_user_id"] if r and r["dahua_user_id"] else None

async def link(u,c):
    if ADMIN_CHAT_ID and not admin(u): return await u.message.reply_text("🔒 Привязку выполняет руководитель.",reply_markup=MENU)
    if not c.args:return await u.message.reply_text("Использование: /link ID",reply_markup=MENU)
    uid=c.args[0].strip(); now=now_local().isoformat(); x=u.effective_user; con=db()
    con.execute("""INSERT INTO telegram_users(chat_id,dahua_user_id,username,first_name,created_at,updated_at)
        VALUES(?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET dahua_user_id=excluded.dahua_user_id,updated_at=excluded.updated_at""",
        (u.effective_chat.id,uid,x.username if x else "",x.first_name if x else "",now,now))
    r=con.execute("SELECT user_name FROM attendance WHERE user_id=? AND user_name<>'' ORDER BY id DESC LIMIT 1",(uid,)).fetchone(); con.commit(); con.close()
    await u.message.reply_text(f"✅ Telegram привязан к {r['user_name'] if r else uid} (ID {uid}).",reply_markup=MENU)

async def me(u,c):
    uid=linked(u.effective_chat.id)
    if not uid:return await u.message.reply_text("Ваш Telegram пока не привязан. Руководитель: /link ID",reply_markup=MENU)
    rows=day_rows(now_local().strftime("%Y-%m-%d"),uid)
    if not rows:return await u.message.reply_text("Сегодня отметок пока нет.",reply_markup=MENU)
    text="👤 Мои записи\n\n"+"\n".join(f"• {fmt_time(dt(r['event_time']))} — {r['event_type'] or 'Отметка'} — {r['status'] or 'Выполнено'}" for r in rows)
    await u.message.reply_text(text,reply_markup=MENU)

async def report(u,c):
    uid=linked(u.effective_chat.id)
    if not uid:return await u.message.reply_text("Ваш Telegram пока не привязан. Руководитель: /link ID",reply_markup=MENU)
    rows=day_rows(now_local().strftime("%Y-%m-%d"),uid); s=state(rows)
    name=rows[-1]["user_name"] if rows else uid
    text=f"📋 Мой отчёт — {name}\n\nВход: {fmt_time(s['first'])}\nВыход: {fmt_time(s['last_exit'])}\nОтработано: {fmt_dur(s['worked'])}\nСтатус: {'🟢 на работе' if s['present'] else '🔴 не на работе'}"
    l=late(s["first"])
    if l and l>0:text+=f"\nОпоздание: {l} мин"
    await u.message.reply_text(text,reply_markup=MENU)

async def last(u,c):
    if not admin(u): return await u.message.reply_text("🔒 Последние записи доступны руководителю.",reply_markup=MENU)
    con=db(); rows=con.execute("SELECT * FROM attendance ORDER BY id DESC LIMIT 20").fetchall(); con.close()
    if not rows:return await u.message.reply_text("Записей пока нет.",reply_markup=MENU)
    text="📌 Последние записи\n\n"+"\n".join(f"• {fmt_time(dt(r['event_time']))} {r['user_name'] or r['user_id']} — {r['event_type'] or 'Отметка'}" for r in rows)
    await u.message.reply_text(text,reply_markup=MENU)

async def buttons(u,c):
    t=(u.message.text or "").strip()
    if t=="📊 Сегодня": return await today_cmd(u,c)
    if t=="👥 Сейчас на работе": return await presence(u,c)
    if t=="📅 Неделя": return await week(u,c)
    if t=="🗓 Месяц": return await month(u,c)
    if t=="👤 Мои записи": return await me(u,c)
    if t=="📋 Мой отчёт": return await report(u,c)
    if t=="ℹ️ Помощь": return await help_cmd(u,c)
    await u.message.reply_text("Выберите пункт меню.",reply_markup=MENU)

class DahuaHandler(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    server_version="FUNLANDIA-STAFF/2.0"
    def reply(self,code=200,text="OK"):
        b=text.encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type","text/plain; charset=utf-8")
            self.send_header("Content-Length",str(len(b)))
            self.send_header("Connection","close")
            self.end_headers()
            self.wfile.write(b); self.wfile.flush()
        except Exception: pass

    def read_body(self):
        expect=self.headers.get("Expect","").lower()
        if "100-continue" in expect:
            try:
                self.send_response_only(100); self.end_headers()
            except Exception: pass
        te=self.headers.get("Transfer-Encoding","").lower()
        if "chunked" in te: return self.read_chunked()
        try:n=int(self.headers.get("Content-Length","0") or 0)
        except ValueError:n=0
        if n<=0:return b""
        data=b""; old_timeout=self.connection.gettimeout()
        try:
            self.connection.settimeout(8.0)
            while len(data)<n:
                chunk=self.rfile.read(n-len(data))
                if not chunk:break
                data+=chunk
        except (socket.timeout,TimeoutError,OSError) as e:
            logger.warning("DAHUA body read incomplete expected=%s got=%s error=%s",n,len(data),e)
        finally:
            try:self.connection.settimeout(old_timeout)
            except Exception:pass
        return data

    def read_chunked(self):
        out=[]
        while True:
            line=self.rfile.readline(65536)
            if not line:break
            try:n=int(line.strip().split(b";",1)[0],16)
            except Exception:break
            if n==0:
                self.rfile.readline()
                break
            out.append(self.rfile.read(n)); self.rfile.read(2)
        return b"".join(out)

    def event_from_query_headers(self):
        p=parse_qs(urlparse(self.path).query,keep_blank_values=True)
        d={k:(v[-1] if v else "") for k,v in p.items()}
        for k,v in self.headers.items():
            nk=re.sub(r"[^a-z0-9_]","",k.lower())
            if nk in {"userid","user_id","username","cardname","eventtime","eventtype","type","status","recno","recordno","createtime","time","action"} and v:
                d[k]=v
        return d

    def process(self,raw):
        ct=self.headers.get("Content-Type","")
        p=parse_body(raw,ct) if raw else self.event_from_query_headers()
        if not p:return 0
        n=0
        for e in payloads(p):
            ins,info=save_event(e); n+=int(ins)
            if info["user_id"] or info["user_name"]:
                logger.info("DAHUA EVENT inserted=%s id=%s name=%s time=%s type=%s status=%s",ins,info["user_id"],info["user_name"],info["event_time"],info["event_type"],info["status"])
        return n

    def do_GET(self):
        path=urlparse(self.path).path
        logger.info("DAHUA GET path=%s",path)
        if "keepalive" not in path.lower():self.process(b"")
        self.reply(200,"FUNLANDIA STAFF OK" if path.startswith("/health") else "OK")

    def do_POST(self):
        try:
            raw=self.read_body(); path=urlparse(self.path).path
            preview=raw[:2000].decode("utf-8","replace") if raw else ""
            logger.info("DAHUA POST path=%s content-type=%s transfer=%s content-length=%s body-bytes=%s body-preview=%r",path,self.headers.get("Content-Type",""),self.headers.get("Transfer-Encoding",""),self.headers.get("Content-Length",""),len(raw),preview)
            if "keepalive" not in path.lower():logger.info("DAHUA PUSH processed=%s new-events=%s",path,self.process(raw))
            self.reply(200,"OK")
        except Exception as e:
            logger.exception("DAHUA webhook error: %s",e)
            try:self.reply(200,"OK")
            except Exception:pass

    def log_message(self,*args):pass

def http_server():
    s=ThreadingHTTPServer(("0.0.0.0",PORT),DahuaHandler)
    s.daemon_threads=True
    logger.info("DAHUA HTTP PUSH SERVER LISTENING ON %s",PORT)
    s.serve_forever()

def main():
    if not BOT_TOKEN:raise RuntimeError("BOT_TOKEN is not set")
    init_db(); threading.Thread(target=http_server,daemon=True,name="dahua-http").start()
    app=Application.builder().token(BOT_TOKEN).build()
    for cmd,fn in [("start",start),("help",help_cmd),("today",today_cmd),("week",week),("month",month),("link",link),("me",me),("report",report),("last",last)]:app.add_handler(CommandHandler(cmd,fn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,buttons)); logger.info("FUNLANDIA STAFF BOT STARTED"); app.run_polling(drop_pending_updates=False)

if __name__=="__main__":main()
