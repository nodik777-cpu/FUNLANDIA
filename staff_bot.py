import os, json, hashlib, logging, sqlite3, threading, socket, asyncio
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("funlandia_staff")
BOT_TOKEN=os.getenv("BOT_TOKEN","").strip(); PORT=int(os.getenv("PORT","8080")); DB_PATH=os.getenv("STAFF_DB_PATH","staff_attendance.db")
ADMIN_CHAT_ID=os.getenv("STAFF_ADMIN_CHAT_ID","").strip(); SHIFT_START=os.getenv("SHIFT_START","09:00").strip(); TZ=timezone(timedelta(hours=5))
MENU=ReplyKeyboardMarkup([["📊 Сегодня","👥 Сейчас на работе"],["📅 Неделя","🗓 Месяц"],["👤 Мои записи","📋 Мой отчёт"],["ℹ️ Помощь"]],resize_keyboard=True)
SUCCESS={"","1","true","success","succeeded","ok","выполнено","passed"}; IGNORE={"doorstatus","keepalive","heartbeat","pulse"}
LOOP=None; APP=None

def now(): return datetime.now(TZ)
def db():
    c=sqlite3.connect(DB_PATH,timeout=30); c.row_factory=sqlite3.Row; return c

def init_db():
    c=db(); c.execute("""CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY AUTOINCREMENT,event_key TEXT UNIQUE NOT NULL,user_id TEXT,user_name TEXT,event_time TEXT NOT NULL,event_type TEXT,status TEXT,method TEXT,direction TEXT,source TEXT NOT NULL,raw_payload TEXT NOT NULL)"""); c.execute("""CREATE TABLE IF NOT EXISTS telegram_users(chat_id INTEGER PRIMARY KEY,dahua_user_id TEXT,username TEXT,first_name TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)"""); c.execute("CREATE INDEX IF NOT EXISTS idx_a ON attendance(user_id,event_time)"); c.commit(); c.close()

def parse_time(v):
    if v in (None,""): return now()
    s=str(v).strip()
    if s.isdigit():
        try:
            n=int(s)
            if n>100000000:return datetime.fromtimestamp(n,timezone.utc).astimezone(TZ)
        except: pass
    s=s.replace("Z","+00:00")
    for x in (s,s.replace("/","-")):
        try:
            d=datetime.fromisoformat(x); return (d.replace(tzinfo=TZ) if d.tzinfo is None else d).astimezone(TZ)
        except: pass
    for f in ("%Y-%m-%d %H:%M:%S","%Y/%m/%d %H:%M:%S","%Y-%m-%dT%H:%M:%S"):
        try:return datetime.strptime(s,f).replace(tzinfo=TZ)
        except:pass
    return now()

def first(d,*keys):
    for k in keys:
        if isinstance(d,dict) and d.get(k) not in (None,""):return d[k]
    return ""

def info_of(p):
    if not isinstance(p,dict):return {}
    n=[p]
    for k in ("Data","data","Event","event","Record","record","Info","info","Params","params"):
        v=p.get(k)
        if isinstance(v,dict):n.append(v)
        elif isinstance(v,list):n.extend(x for x in v if isinstance(x,dict))
    z={"user_id":"","user_name":"","event_time":now(),"event_type":"","status":"","method":"","rec_no":"","code":"","action":""}
    for x in n:
        z["user_id"] or None
        z["user_id"]=z["user_id"] or str(first(x,"UserID","userId","user_id","PersonID","personId","EmployeeID","employeeId","personCode","ID"))
        z["user_name"]=z["user_name"] or str(first(x,"CardName","UserName","userName","user_name","PersonName","personName","Name","name"))
        t=first(x,"CreateTime","EventTime","eventTime","event_time","AlarmDate","alarmDate","Time","time","RealTime")
        if t and z["event_time"]==z["event_time"]: z["event_time"]=parse_time(t)
        z["event_type"]=z["event_type"] or str(first(x,"Type","EventType","eventType","event_type","OperateType","operateType"))
        z["status"]=z["status"] or str(first(x,"Status","status","Result","result","ErrorCode","errorCode"))
        z["method"]=z["method"] or str(first(x,"Method","method","VerifyMethod","verifyMethod"))
        z["rec_no"]=z["rec_no"] or str(first(x,"RecNo","RecordNo","recordNo","Seq","seq"))
        z["code"]=z["code"] or str(first(x,"Code","code","EventCode","eventCode")); z["action"]=z["action"] or str(first(x,"Action","action"))
    return z

def good(i):return i.get("status","").strip().lower() in SUCCESS
def direction(i):
    s=(str(i.get("event_type","")+" "+str(i.get("code","")))).lower()
    if any(x in s for x in ("exit","out","выход","leave")):return "EXIT"
    if any(x in s for x in ("entry","in","вход","enter")):return "ENTRY"
    return ""
def person_event(i):
    return bool(i.get("user_id") or i.get("user_name")) and i.get("code","").lower() not in IGNORE

def insert(p):
    i=info_of(p)
    if not person_event(i):return False,i
    raw=json.dumps(p,ensure_ascii=False,sort_keys=True,default=str); base="|".join(str(i[k]) for k in ("rec_no","user_id","user_name","event_time","event_type","status","method","code")); key=hashlib.sha256((base+"|"+raw).encode()).hexdigest()
    c=db(); cur=c.execute("INSERT OR IGNORE INTO attendance(event_key,user_id,user_name,event_time,event_type,status,method,direction,source,raw_payload) VALUES(?,?,?,?,?,?,?,?,?,?)",(key,i["user_id"],i["user_name"],i["event_time"].isoformat(),i["event_type"],i["status"],i["method"],"","dahua_http_push",raw)); okins=cur.rowcount==1; c.commit(); c.close(); return okins,i

def resolve(uid,t,explicit):
    if explicit:return explicit
    c=db(); r=c.execute("SELECT COUNT(*) n FROM attendance WHERE user_id=? AND event_time<? AND (status IS NULL OR status='' OR lower(status) IN (%s))"%(",".join("?" for _ in SUCCESS)),[str(uid),t.isoformat(),*SUCCESS]).fetchone(); c.close(); return "EXIT" if r["n"]%2 else "ENTRY"
def duplicate(uid,t):
    c=db(); r=c.execute("SELECT event_time FROM attendance WHERE user_id=? AND event_time<? ORDER BY event_time DESC,id DESC LIMIT 1",(str(uid),t.isoformat())).fetchone(); c.close()
    if not r:return False
    try:return abs((t-datetime.fromisoformat(r["event_time"])).total_seconds())<60
    except:return False

def schedule(i):
    if not LOOP or not APP or not good(i):return
    asyncio.run_coroutine_threadsafe(notify(i),LOOP)
async def notify(i):
    uid=i["user_id"]
    if not uid or duplicate(uid,i["event_time"]):return
    d=resolve(uid,i["event_time"],direction(i)); c=db(); c.execute("UPDATE attendance SET direction=? WHERE user_id=? AND event_time=?",(d,uid,i["event_time"].isoformat())); links=c.execute("SELECT chat_id FROM telegram_users WHERE dahua_user_id=?",(uid,)).fetchall(); c.commit(); c.close()
    targets={int(x["chat_id"]) for x in links};
    if ADMIN_CHAT_ID:
        try:targets.add(int(ADMIN_CHAT_ID))
        except:pass
    text=("🟢 <b>ВХОД</b>" if d=="ENTRY" else "🔴 <b>ВЫХОД</b>")+f"\n\n👤 {i['user_name'] or uid}\n🆔 ID: {uid}\n🕐 {i['event_time'].strftime('%d.%m.%Y %H:%M:%S')}"
    if i["method"]:text+=f"\n🔐 Метод: {i['method']}"
    for chat in targets:
        try:await APP.bot.send_message(chat_id=chat,text=text,parse_mode="HTML")
        except Exception:log.exception("telegram send failed chat=%s",chat)

def body(raw,ct):
    if not raw:return {}
    s=raw.decode("utf-8","replace").strip(); ct=(ct or "").lower()
    if "json" in ct or s.startswith(("{","[")):
        try:return json.loads(s)
        except:pass
    if "xml" in ct or s.startswith("<"):
        try:
            root=ET.fromstring(s); return {e.tag.split("}")[-1]:(e.text or "").strip() for e in root.iter() if e is not root and (e.text or "").strip()}
        except:pass
    if "multipart/" in ct:
        for part in raw.split(b"\r\n--"):
            p=part.find(b"\r\n\r\n")
            if p>=0:
                try:return json.loads(part[p+4:].strip().rstrip(b"-"))
                except:pass
    q=parse_qs(s,keep_blank_values=True)
    if q:return {k:v[-1] if v else "" for k,v in q.items()}
    out={}
    for line in s.splitlines():
        if "=" in line:
            k,v=line.split("=",1);out[k.strip()]=v.strip()
    return out or {"raw":s[:20000]}

def plist(p):
    if isinstance(p,list):return [x for x in p if isinstance(x,dict)]
    if not isinstance(p,dict):return []
    for k in ("Events","events","Records","records"):
        if isinstance(p.get(k),list):return [x for x in p[k] if isinstance(x,dict)]
    return [p]

class DahuaHandler(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"; server_version="FUNLANDIA-STAFF/4.0"
    def reply(self,code=200,text="OK"):
        b=text.encode()
        try:self.send_response(code);self.send_header("Content-Type","text/plain; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.send_header("Connection","close");self.end_headers();self.wfile.write(b);self.wfile.flush()
        except:pass
    def read_chunked(self):
        out=[]
        while True:
            line=self.rfile.readline().strip()
            if not line:continue
            try:n=int(line.split(b";",1)[0],16)
            except:break
            if n==0:break
            out.append(self.rfile.read(n));self.rfile.read(2)
        return b"".join(out)
    def read_body(self):
        if "chunked" in self.headers.get("Transfer-Encoding","").lower():return self.read_chunked()
        try:n=int(self.headers.get("Content-Length","0") or 0)
        except:n=0
        if n<=0:return b""
        old=self.connection.gettimeout(); self.connection.settimeout(10); data=b""
        try:
            while len(data)<n:
                x=self.rfile.read(n-len(data))
                if not x:break
                data+=x
        except:log.exception("body read")
        finally:
            try:self.connection.settimeout(old)
            except:pass
        return data
    def do_GET(self):
        log.info("GET %s",urlparse(self.path).path);self.reply(200,"FUNLANDIA STAFF OK")
    def do_POST(self):
        raw=self.read_body(); path=urlparse(self.path).path; log.info("POST %s type=%s bytes=%s preview=%r",path,self.headers.get("Content-Type",""),len(raw),raw[:2000].decode("utf-8","replace"))
        count=0
        try:
            for p in plist(body(raw,self.headers.get("Content-Type",""))):
                ins,i=insert(p)
                if i.get("user_id") or i.get("user_name"):log.info("DAHUA EVENT inserted=%s id=%s name=%s time=%s code=%s type=%s status=%s method=%s",ins,i["user_id"],i["user_name"],i["event_time"].isoformat(),i["code"],i["event_type"],i["status"],i["method"])
                if ins:count+=1;schedule(i)
        except Exception:log.exception("Dahua processing")
        log.info("DAHUA PUSH processed=%s new-events=%s",path,count);self.reply(200,"OK")
    def log_message(self,*a):pass

def http_server():ThreadingHTTPServer(("0.0.0.0",PORT),DahuaHandler).serve_forever()
def on_start(app):
    global LOOP,APP;LOOP=asyncio.get_running_loop();APP=app

def link_id(update,context):
    pass

async def start(update,context):
    u=update.effective_user;t=now().isoformat();c=db();c.execute("INSERT INTO telegram_users(chat_id,username,first_name,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,updated_at=excluded.updated_at",(update.effective_chat.id,u.username if u else "",u.first_name if u else "",t,t));c.commit();c.close();await update.message.reply_text("👷 <b>FUNLANDIA — БОТ СОТРУДНИКОВ</b>\n\nDahua подключён напрямую.\nВыберите раздел ниже.",parse_mode="HTML",reply_markup=MENU)
async def help_cmd(update,context):await update.message.reply_text("/link ID — привязать Telegram к сотруднику Dahua\n/me — мои записи\n/report YYYY-MM-DD — дневной отчёт\n/last — последние события",reply_markup=MENU)
async def link(update,context):
    if ADMIN_CHAT_ID and str(update.effective_chat.id)!=ADMIN_CHAT_ID:return await update.message.reply_text("🔒 Привязку выполняет руководитель.",reply_markup=MENU)
    if not context.args:return await update.message.reply_text("Использование: /link ID",reply_markup=MENU)
    uid=context.args[0].strip();u=update.effective_user;t=now().isoformat();c=db();c.execute("INSERT INTO telegram_users(chat_id,dahua_user_id,username,first_name,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET dahua_user_id=excluded.dahua_user_id,updated_at=excluded.updated_at",(update.effective_chat.id,uid,u.username if u else "",u.first_name if u else "",t,t));c.commit();c.close();await update.message.reply_text(f"✅ Telegram привязан к ID Dahua <b>{uid}</b>.",parse_mode="HTML",reply_markup=MENU)
def linked(chat):
    c=db();r=c.execute("SELECT dahua_user_id FROM telegram_users WHERE chat_id=?",(chat,)).fetchone();c.close();return r["dahua_user_id"] if r else None

def day_rows(day,uid=None):
    c=db();sql="SELECT * FROM attendance WHERE event_time LIKE ?";a=[day+"%"]
    if uid:sql+=" AND user_id=?";a.append(str(uid))
    rows=c.execute(sql+" ORDER BY event_time,id",a).fetchall();c.close();return [r for r in rows if (r["status"] or "").lower() in SUCCESS]
def presence(uid,day):
    rs=day_rows(day,uid);opened=None;first=None;worked=0
    for r in rs:
        t=datetime.fromisoformat(r["event_time"]);d=r["direction"] or direction({"event_type":r["event_type"],"code":""})
        if not d:d="ENTRY" if opened is None else "EXIT"
        if d=="ENTRY":
            first=first or t;opened=t
        elif opened:
            if t>=opened:worked+=int((t-opened).total_seconds())
            opened=None
    if opened:worked+=max(0,int((now()-opened).total_seconds()))
    return bool(opened),first,datetime.fromisoformat(rs[-1]["event_time"]) if rs and not opened else None,worked
def dur(s):
    h,m=divmod(max(0,int(s)),3600);m//=60;return f"{h} ч {m:02d} мин" if h else f"{m} мин"

async def me(update,context):
    uid=linked(update.effective_chat.id)
    if not uid:return await update.message.reply_text("🔗 Telegram ещё не привязан. Руководитель: /link ID",reply_markup=MENU)
    day=now().strftime("%Y-%m-%d");rs=day_rows(day,uid);c=db();r=c.execute("SELECT user_name FROM attendance WHERE user_id=? ORDER BY id DESC LIMIT 1",(uid,)).fetchone();c.close();name=r["user_name"] if r and r["user_name"] else uid;present,first,last,w=presence(uid,day)
    text=f"👤 <b>{name}</b>\n📅 {now().strftime('%d.%m.%Y')}\n\n"+"\n".join(f"• {datetime.fromisoformat(x['event_time']).strftime('%H:%M:%S')} — {x['direction'] or 'проход'}" for x in rs)+f"\n\n⏱ Отработано: {dur(w)}\nСостояние: {'🟢 на работе' if present else '🔴 не на работе'}"
    await update.message.reply_text(text,parse_mode="HTML",reply_markup=MENU)
async def today(update,context):
    day=now().strftime("%Y-%m-%d");c=db();ids=c.execute("SELECT DISTINCT user_id FROM attendance WHERE event_time LIKE ? AND user_id<>''",(day+"%",)).fetchall();c.close();cur=[]
    for x in ids:
        p,f,_,_=presence(x["user_id"],day)
        if p:
            c=db();r=c.execute("SELECT user_name FROM attendance WHERE user_id=? ORDER BY id DESC LIMIT 1",(x["user_id"],)).fetchone();c.close();cur.append((r["user_name"] if r and r["user_name"] else x["user_id"],f))
    text=f"📊 <b>Сегодня</b>\n\n👥 Отметились: {len(ids)}\n🟢 Сейчас на работе: {len(cur)}"+(("\n\n"+"\n".join(f"• {n} — с {t.strftime('%H:%M')}" for n,t in cur)) if cur else "")
    await update.message.reply_text(text,parse_mode="HTML",reply_markup=MENU)
async def current(update,context):return await today(update,context)
async def report(update,context):
    if not ADMIN_CHAT_ID or str(update.effective_chat.id)!=ADMIN_CHAT_ID:return await update.message.reply_text("🔒 Отчёт доступен руководителю.",reply_markup=MENU)
    day=context.args[0] if context.args else now().strftime("%Y-%m-%d");c=db();ids=c.execute("SELECT DISTINCT user_id FROM attendance WHERE event_time LIKE ? AND user_id<>''",(day+"%",)).fetchall();c.close();lines=[f"📋 <b>Отчёт {day}</b>",""]
    for x in ids:
        p,f,l,w=presence(x["user_id"],day);c=db();r=c.execute("SELECT user_name FROM attendance WHERE user_id=? ORDER BY id DESC LIMIT 1",(x["user_id"],)).fetchone();c.close();n=r["user_name"] if r and r["user_name"] else x["user_id"];lines.append(f"👤 {n} (ID {x['user_id']})\n   Вход: {f.strftime('%H:%M') if f else '—'} | Выход: {l.strftime('%H:%M') if l else '—'} | {dur(w)}")
    await update.message.reply_text("\n".join(lines),parse_mode="HTML",reply_markup=MENU)
async def week(update,context):
    if not ADMIN_CHAT_ID or str(update.effective_chat.id)!=ADMIN_CHAT_ID:return await update.message.reply_text("🔒 Отчёт доступен руководителю.",reply_markup=MENU)
    await update.message.reply_text("📅 Недельный отчёт: используйте /report YYYY-MM-DD для конкретного дня. Расширенный сводный отчёт подключается после первых реальных событий.",reply_markup=MENU)
async def month(update,context):
    if not ADMIN_CHAT_ID or str(update.effective_chat.id)!=ADMIN_CHAT_ID:return await update.message.reply_text("🔒 Отчёт доступен руководителю.",reply_markup=MENU)
    await update.message.reply_text("🗓 Месячный отчёт: система готова собирать данные; сводная форма будет рассчитана из реальных проходов.",reply_markup=MENU)
async def last(update,context):
    c=db();rs=c.execute("SELECT * FROM attendance ORDER BY id DESC LIMIT 15").fetchall();c.close();await update.message.reply_text("Записей пока нет." if not rs else "\n".join(f"• {x['event_time'][11:19]} — {x['user_name'] or x['user_id']} — {x['direction'] or x['event_type'] or 'проход'}" for x in rs),reply_markup=MENU)
async def buttons(update,context):
    m={"📊 Сегодня":today,"👥 Сейчас на работе":current,"👤 Мои записи":me,"📋 Мой отчёт":report,"📅 Неделя":week,"🗓 Месяц":month,"ℹ️ Помощь":help_cmd};f=m.get(update.message.text.strip());
    if f:await f(update,context)

def main():
    if not BOT_TOKEN:raise RuntimeError("BOT_TOKEN is not set")
    init_db();threading.Thread(target=http_server,daemon=True).start();app=Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    for cmd,fn in (("start",start),("help",help_cmd),("link",link),("me",me),("report",report),("week",week),("month",month),("last",last)):app.add_handler(CommandHandler(cmd,fn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,buttons));log.info("FUNLANDIA STAFF 4.0 STARTED");app.run_polling(drop_pending_updates=False)
if __name__=="__main__":main()
