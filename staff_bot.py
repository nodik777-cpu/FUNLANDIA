import os, json, re, sqlite3, hashlib, logging, threading, calendar, socket, subprocess, shutil, time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as ET
import requests
from requests.auth import HTTPDigestAuth
from telegram import ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("funlandia_staff")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("STAFF_DB_PATH", "staff_attendance.db")
ADMIN_CHAT_ID = os.getenv("STAFF_ADMIN_CHAT_ID", os.getenv("ADMIN_CHAT_ID", "")).strip()
SHIFT_START = os.getenv("SHIFT_START", "09:00")
TZ = timezone(timedelta(hours=5))

# Dahua P2P -> local tunnel -> CGI polling.
DAHUA_SERIAL = os.getenv("DAHUA_SERIAL", "AB03665PAJ06685").strip()
DAHUA_USER = os.getenv("DAHUA_USER", "admin").strip()
DAHUA_PASSWORD = os.getenv("DAHUA_PASSWORD", "").strip()
P2P_LOCAL_PORT = int(os.getenv("P2P_LOCAL_PORT", "18080"))
P2P_POLL_SECONDS = int(os.getenv("P2P_POLL_SECONDS", "15"))
P2P_APP = os.getenv("DAHUA_P2P_APP", "dmss").strip().lower()
P2P_ENABLED = os.getenv("DAHUA_P2P_ENABLED", "1").strip().lower() not in {"0", "false", "no"}

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
    if v is None or str(v).strip() == "": return now().isoformat()
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
    out=[]
    if isinstance(x,dict):
        out.append(x)
        for v in x.values():
            if isinstance(v,(dict,list)): out.extend(collect_dicts(v))
    elif isinstance(x,list):
        for v in x: out.extend(collect_dicts(v))
    return out


def normalize(payload):
    ds=collect_dicts(payload); uid=name=tm=typ=status=rec=method=""
    for d in ds:
        uid=uid or str(pick(d,"UserID","userId","user_id","PersonID","personId","personCode","EmployeeID","CardNo","No"))
        name=name or str(pick(d,"CardName","UserName","userName","user_name","PersonName","personName","Name","name"))
        tm=tm or str(pick(d,"CreateTime","EventTime","eventTime","Time","time","alarmDate","DateTime"))
        typ=typ or str(pick(d,"Type","EventType","eventType","event_type","InOut","inOut","Direction","direction","OperateType","operateType"))
        status=status or str(pick(d,"Status","Result","result","ErrorCode","errorCode","syncFlags"))
        rec=rec or str(pick(d,"RecNo","RecordNo","recordNo","Sequence","seq"))
        method=method or str(pick(d,"Method","method","OpenMethod","openMethod"))
    return {"user_id":uid.strip(),"user_name":name.strip(),"event_time":parse_time(tm),"type_raw":typ.strip(),"status":status.strip(),"rec_no":rec.strip(),"method":method.strip()}


def event_type(info):
    s=(info.get("type_raw") or "").lower().strip()
    if s in {"1","in","entry","entrance","вход","входить"} or "entry" in s or "вход" in s:return "Вход"
    if s in {"2","out","exit","выход"} or "exit" in s or "выход" in s:return "Выход"
    return ""


def successful(info):
    s=str(info.get("status","")).lower().strip()
    if not s:return True
    if s in SUCCESS:return True
    if s in {"0","false","fail","failed","error","denied","нет разрешения","не выполнено"}:return False
    if re.fullmatch(r"-?\d+",s):return int(s)==0
    return True


def infer_type(uid, explicit):
    if explicit:return explicit
    c=db(); r=c.execute("SELECT event_type FROM attendance WHERE user_id=? ORDER BY event_time DESC,id DESC LIMIT 1",(uid,)).fetchone(); c.close()
    return "Выход" if r and r["event_type"]=="Вход" else "Вход"


def telegram_send(chat_id,text):
    if not BOT_TOKEN or not chat_id:return
    try:
        r=requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":int(chat_id),"text":text},timeout=8)
        if r.status_code!=200:log.warning("Telegram sendMessage HTTP %s",r.status_code)
    except Exception as e:log.warning("Telegram notification failed: %s",e)


def notify(info,etype):
    c=db(); rows=c.execute("SELECT chat_id FROM telegram_users WHERE dahua_user_id=?",(info["user_id"],)).fetchall(); c.close()
    if not rows:return
    icon="🟢" if etype=="Вход" else "🔴"; tm=datetime.fromisoformat(info["event_time"]).strftime("%d.%m.%Y %H:%M:%S")
    text=f"{icon} {etype.upper()}\n\n👤 {info['user_name'] or info['user_id']}\n🆔 ID: {info['user_id']}\n🕐 {tm}"
    if info.get("method"):text+=f"\nМетод: {info['method']}"
    for r in rows:threading.Thread(target=telegram_send,args=(r["chat_id"],text),daemon=True).start()


def save_event(info, raw, source="dahua_p2p"):
    if not info["user_id"] and not info["user_name"]:return False
    if not successful(info):return False
    et=event_type(info) or infer_type(info["user_id"],"")
    base="|".join([info["rec_no"],info["user_id"],info["user_name"],info["event_time"],et,info["method"]])
    key=hashlib.sha256((base+"|"+raw).encode()).hexdigest()
    c=db(); cur=c.execute("""INSERT OR IGNORE INTO attendance
      (event_key,user_id,user_name,event_time,event_type,status,source,raw_payload,created_at)
      VALUES(?,?,?,?,?,?,?,?,?)""",(key,info["user_id"],info["user_name"],info["event_time"],et,info["status"],source,raw,now().isoformat()))
    inserted=cur.rowcount==1; c.commit(); c.close()
    if inserted:notify({**info,"event_type":et},et)
    return inserted


def parse_records_text(text):
    rows={}
    for line in text.replace("\r","").split("\n"):
        m=re.match(r"records\[(\d+)\]\.([^=]+)=(.*)$",line)
        if m:rows.setdefault(int(m.group(1)),{})[m.group(2)]=m.group(3)
    if rows:return [rows[k] for k in sorted(rows)]
    # Some firmware returns a single record without the records[index] prefix.
    one={}
    for line in text.replace("\r","").split("\n"):
        if "=" in line and not line.startswith("totalCount") and not line.startswith("found"):
            k,v=line.split("=",1); one[k.strip()]=v.strip()
    return [one] if one else []


def query_dahua_records(base_url, start_ts, end_ts):
    url=base_url+"/cgi-bin/recordFinder.cgi"
    params={"action":"find","name":"AccessControlCardRec","StartTime":str(int(start_ts)),"EndTime":str(int(end_ts)),"count":"1024"}
    auth=HTTPDigestAuth(DAHUA_USER,DAHUA_PASSWORD)
    r=requests.get(url,params=params,auth=auth,timeout=12)
    if r.status_code in (401,403):
        r=requests.get(url,params=params,auth=(DAHUA_USER,DAHUA_PASSWORD),timeout=12)
    r.raise_for_status()
    return parse_records_text(r.text),r.text


def p2p_command():
    return ["go","run","github.com/undervolter/dh-fwd@main","--app",P2P_APP,"-t","1","-u",DAHUA_USER,"-P",DAHUA_PASSWORD,"-p",f"{P2P_LOCAL_PORT}:80",DAHUA_SERIAL]


def p2p_worker():
    if not P2P_ENABLED:return
    if not DAHUA_PASSWORD:
        log.warning("P2P disabled until DAHUA_PASSWORD is set in Railway")
        return
    if not shutil.which("go"):
        log.error("P2P cannot start: Go runtime is not available in Railway")
        return
    last_ts=int(time.time())-86400
    while True:
        proc=None
        try:
            log.info("Starting Dahua P2P tunnel SN=%s app=%s local_port=%s",DAHUA_SERIAL,P2P_APP,P2P_LOCAL_PORT)
            proc=subprocess.Popen(p2p_command(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            deadline=time.time()+90
            ready=False
            while time.time()<deadline:
                if proc.poll() is not None:raise RuntimeError(f"P2P process exited with code {proc.returncode}")
                try:
                    with socket.create_connection(("127.0.0.1",P2P_LOCAL_PORT),timeout=1):ready=True;break
                except OSError:time.sleep(1)
            if not ready:raise RuntimeError("P2P local tunnel did not open")
            log.info("Dahua P2P tunnel is ready on 127.0.0.1:%s",P2P_LOCAL_PORT)
            base=f"http://127.0.0.1:{P2P_LOCAL_PORT}"
            while proc.poll() is None:
                end=int(time.time())+5
                try:
                    records,raw=query_dahua_records(base,last_ts-3,end)
                    newmax=last_ts
                    inserted=0
                    for rec in records:
                        info=normalize(rec)
                        if not info["user_id"] and not info["user_name"]:continue
                        ct=rec.get("CreateTime","")
                        try:
                            t=int(float(ct)); newmax=max(newmax,t)
                        except Exception:
                            try:newmax=max(newmax,int(datetime.fromisoformat(info["event_time"]).timestamp()))
                            except Exception:pass
                        info["rec_no"]=str(rec.get("RecNo",info["rec_no"]))
                        info["method"]=str(rec.get("Method",info["method"]))
                        if save_event(info,json.dumps(rec,ensure_ascii=False,sort_keys=True),"dahua_p2p"):inserted+=1
                    if newmax>last_ts:last_ts=newmax
                    if inserted:log.info("P2P attendance: %s new records",inserted)
                except Exception as e:
                    log.warning("P2P attendance poll failed: %s",e)
                time.sleep(max(5,P2P_POLL_SECONDS))
        except Exception as e:
            log.error("P2P worker: %s",e)
        finally:
            if proc is not None:
                try:proc.terminate()
                except Exception:pass
        time.sleep(10)


def parse_xml(raw):
    try:
        root=ET.fromstring(raw.decode("utf-8","replace")); out={}
        for e in root.iter():
            if e is not root and (e.text or "").strip():out[e.tag.split("}")[-1]]=e.text.strip()
        return out
    except Exception:return {}


def parse_body(raw,ct):
    if not raw:return {}
    s=raw.decode("utf-8","replace").strip(); ct=(ct or "").lower()
    if "json" in ct or s.startswith("{") or s.startswith("["):
        try:return json.loads(s)
        except Exception:pass
    if "xml" in ct or s.startswith("<"):
        x=parse_xml(raw)
        if x:return x
    q=parse_qs(s,keep_blank_values=True)
    if q:return {k:v[-1] for k,v in q.items()}
    return {k.strip():v.strip() for k,v in (line.split("=",1) for line in s.splitlines() if "=" in line)} or {"raw":s[:10000]}


class Handler(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"; server_version="FUNLANDIA-STAFF/4.0"
    def reply(self,code=200,text="OK"):
        b=text.encode()
        try:
            self.send_response(code);self.send_header("Content-Type","text/plain; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.send_header("Connection","close");self.end_headers();self.wfile.write(b);self.wfile.flush()
        except Exception:pass
    def do_GET(self):self.reply(200,"FUNLANDIA STAFF OK")
    def do_POST(self):
        try:
            n=int(self.headers.get("Content-Length","0") or 0);raw=self.rfile.read(n) if n else b"";p=parse_body(raw,self.headers.get("Content-Type",""))
            info=normalize(p)
            if info["user_id"] or info["user_name"]:save_event(info,json.dumps(p,ensure_ascii=False,sort_keys=True),"dahua_http_push")
            self.reply(200,"OK")
        except Exception as e:log.exception("Dahua webhook error: %s",e);self.reply(200,"OK")
    def log_message(self,*args):pass


def server():ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()

def is_admin(u):return bool(ADMIN_CHAT_ID and str(u.effective_chat.id)==ADMIN_CHAT_ID)
def linked(chat_id):
    c=db();r=c.execute("SELECT dahua_user_id FROM telegram_users WHERE chat_id=?",(chat_id,)).fetchone();c.close();return r["dahua_user_id"] if r else None

def parse_dt(s):
    try:return datetime.fromisoformat(s)
    except Exception:return None

def day_rows(day,uid=None):
    c=db();q="SELECT * FROM attendance WHERE event_time LIKE ?";a=[day+"%"]
    if uid:q+=" AND user_id=?";a.append(str(uid))
    rows=c.execute(q+" ORDER BY event_time,id",a).fetchall();c.close();return rows

def state(rows):
    present=False;opened=None;first=None;last=None;worked=0
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
            opened=None;present=False
    if opened:worked+=max(0,int((now()-opened).total_seconds()))
    return present,first,last,worked

def dur(sec):
    h,m=divmod(max(0,int(sec)),3600);m//=60
    return f"{h} ч {m:02d} мин" if h else f"{m} мин"

def people(day):
    c=db();rows=c.execute("SELECT * FROM attendance WHERE event_time LIKE ? ORDER BY event_time,id",(day+"%",)).fetchall();c.close();g={}
    for r in rows:g.setdefault(r["user_id"],[]).append(r)
    out=[]
    for uid,rs in g.items():
        p,f,l,w=state(rs);out.append((uid,rs[-1]["user_name"] or uid,p,f,l,w))
    return out

def dashboard():
    ps=people(now().date().isoformat());cur=[x for x in ps if x[2]]
    lines=[f"📊 FUNLANDIA — {now().date().isoformat()}","",f"👥 Отметились: {len(ps)}",f"🟢 Сейчас на работе: {len(cur)}"]
    if cur:lines += ["","🟢 СЕЙЧАС"]+[f"• {x[1]} — с {x[3].strftime('%H:%M') if x[3] else '—'}" for x in cur]
    return "\n".join(lines)

async def start(u,c):
    x=u.effective_user;t=now().isoformat();con=db();con.execute("""INSERT INTO telegram_users(chat_id,username,first_name,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,updated_at=excluded.updated_at""",(u.effective_chat.id,x.username if x else "",x.first_name if x else "",t,t));con.commit();con.close()
    await u.message.reply_text("👷 FUNLANDIA — БОТ СОТРУДНИКОВ\n\nDahua P2P: " + ("подключается автоматически." if DAHUA_PASSWORD else "ожидает пароль в Railway.") + "\nПривяжите Telegram к ID Dahua командой /link ID.",reply_markup=MENU)

async def link(u,c):
    if ADMIN_CHAT_ID and not is_admin(u):return await u.message.reply_text("🔒 Привязку выполняет руководитель.",reply_markup=MENU)
    if not c.args:return await u.message.reply_text("Использование: /link ID",reply_markup=MENU)
    uid=c.args[0].strip();x=u.effective_user;t=now().isoformat();con=db();con.execute("""INSERT INTO telegram_users(chat_id,dahua_user_id,username,first_name,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET dahua_user_id=excluded.dahua_user_id,updated_at=excluded.updated_at""",(u.effective_chat.id,uid,x.username if x else "",x.first_name if x else "",t,t));r=con.execute("SELECT user_name FROM attendance WHERE user_id=? ORDER BY id DESC LIMIT 1",(uid,)).fetchone();con.commit();con.close();await u.message.reply_text(f"✅ Telegram привязан к {r['user_name'] if r else uid} (ID {uid}).",reply_markup=MENU)

async def today_cmd(u,c):await u.message.reply_text(dashboard(),reply_markup=MENU)
async def current_cmd(u,c):await u.message.reply_text(dashboard(),reply_markup=MENU)

async def me_cmd(u,c):
    uid=linked(u.effective_chat.id)
    if not uid:return await u.message.reply_text("⚠️ Telegram ещё не привязан. Используйте /link ID.",reply_markup=MENU)
    rows=day_rows(now().date().isoformat(),uid)
    if not rows:return await u.message.reply_text("📋 Сегодня записей нет.",reply_markup=MENU)
    lines=[f"👤 {rows[-1]['user_name'] or uid}",""]
    for r in rows:
        d=parse_dt(r["event_time"]);lines.append(f"{'🟢' if r['event_type']=='Вход' else '🔴'} {r['event_type']} — {d.strftime('%H:%M:%S') if d else r['event_time']}")
    p,f,l,w=state(rows);lines += ["",f"⏱ Отработано: {dur(w)}",f"📍 Статус: {'НА РАБОТЕ' if p else 'НЕ НА РАБОТЕ'}"]
    await u.message.reply_text("\n".join(lines),reply_markup=MENU)

async def report_cmd(u,c):
    uid=linked(u.effective_chat.id)
    if not uid:return await u.message.reply_text("⚠️ Сначала /link ID.",reply_markup=MENU)
    d=now().date();start=d-timedelta(days=6);total=0;days=0;items=[]
    while start<=d:
        rs=day_rows(start.isoformat(),uid)
        if rs:
            p,f,l,w=state(rs);total+=w;days+=1;items.append((start,f,l,w))
        start+=timedelta(days=1)
    if not items:return await u.message.reply_text("📋 За последние 7 дней записей нет.",reply_markup=MENU)
    lines=["📋 МОЙ ОТЧЁТ",f"Рабочих дней: {days}",f"Отработано: {dur(total)}",""]
    for d,f,l,w in items:lines.append(f"{d.strftime('%d.%m')} — {f.strftime('%H:%M') if f else '—'} / {l.strftime('%H:%M') if l else '—'} — {dur(w)}")
    await u.message.reply_text("\n".join(lines),reply_markup=MENU)

async def period_cmd(u,c,kind):
    if not is_admin(u):return await u.message.reply_text("🔒 Отчёт доступен руководителю.",reply_markup=MENU)
    t=now().date();start=t-timedelta(days=t.weekday()) if kind=='week' else t.replace(day=1);groups={};d=start
    while d<=t:
        for uid,name,p,f,l,w in people(d.isoformat()):
            z=groups.setdefault(uid,[name,0,0]);z[0]=name;z[1]+=1;z[2]+=w
        d+=timedelta(days=1)
    title='НЕДЕЛЬНЫЙ' if kind=='week' else 'МЕСЯЧНЫЙ';lines=[f"📊 {title} ОТЧЁТ",f"{start.strftime('%d.%m.%Y')} — {t.strftime('%d.%m.%Y')}",""]
    if not groups:lines.append("Записей нет.")
    for uid,(name,days,w) in sorted(groups.items(),key=lambda x:x[1][0].lower()):lines += [f"👤 {name}",f"   Дней: {days} | Время: {dur(w)}",""]
    await u.message.reply_text("\n".join(lines).strip(),reply_markup=MENU)

async def help_cmd(u,c):await u.message.reply_text("ℹ️ Команды:\n/link ID — привязать Telegram к сотруднику Dahua\n/today — сегодня\n/me — мои записи\n/report — мой отчёт\n\nРуководитель: /week и /month",reply_markup=MENU)

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
    if not BOT_TOKEN:raise RuntimeError("BOT_TOKEN is not set")
    init_db()
    threading.Thread(target=server,daemon=True,name="dahua-http").start()
    threading.Thread(target=p2p_worker,daemon=True,name="dahua-p2p").start()
    app=Application.builder().token(BOT_TOKEN).build()
    for cmd,fn in [('start',start),('link',link),('today',today_cmd),('me',me_cmd),('report',report_cmd),('help',help_cmd)]:app.add_handler(CommandHandler(cmd,fn))
    app.add_handler(CommandHandler('week',lambda u,c:period_cmd(u,c,'week')))
    app.add_handler(CommandHandler('month',lambda u,c:period_cmd(u,c,'month')))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,buttons))
    log.info("FUNLANDIA STAFF BOT 4.0 STARTED; Dahua P2P=%s",P2P_ENABLED)
    app.run_polling(drop_pending_updates=False)

if __name__=='__main__':main()
