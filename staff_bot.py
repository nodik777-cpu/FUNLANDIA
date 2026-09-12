import os,json,hashlib,logging,sqlite3,threading,asyncio,socket,html
from datetime import datetime,timezone,timedelta,date
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from telegram import Update,ReplyKeyboardMarkup
from telegram.ext import Application,CommandHandler,MessageHandler,ContextTypes,filters

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log=logging.getLogger("funlandia_staff")
BOT_TOKEN=os.getenv("BOT_TOKEN","").strip()
PORT=int(os.getenv("PORT","8080"))
DB_PATH=os.getenv("STAFF_DB_PATH","staff_attendance.db")
# Admin ID is intentionally isolated to this Staff service. Environment variable may override it.
ADMIN_CHAT_ID=os.getenv("STAFF_ADMIN_CHAT_ID","1697712497").strip()
SHIFT_START=os.getenv("SHIFT_START","09:00").strip()
TZ=timezone(timedelta(hours=5))
MENU=ReplyKeyboardMarkup([["📊 Сегодня","👥 Сейчас на работе"],["📅 Неделя","🗓 Месяц"],["👤 Мои записи","📋 Мой отчёт"],["ℹ️ Помощь"]],resize_keyboard=True)
SUCCESS={"","1","true","success","succeeded","ok","выполнено","passed","allow","allowed"}
IGNORE={"doorstatus","keepalive","heartbeat","pulse"}
LOOP=None;APP=None

def now():return datetime.now(TZ)
def db():
 c=sqlite3.connect(DB_PATH,timeout=30);c.row_factory=sqlite3.Row;return c

def init_db():
 c=db();c.execute("CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY,event_key TEXT UNIQUE,user_id TEXT,user_name TEXT,event_time TEXT,event_type TEXT,status TEXT,method TEXT,direction TEXT,source TEXT,raw_payload TEXT)")
 c.execute("CREATE TABLE IF NOT EXISTS telegram_users(chat_id INTEGER PRIMARY KEY,dahua_user_id TEXT,username TEXT,first_name TEXT,created_at TEXT,updated_at TEXT)")
 c.execute("CREATE INDEX IF NOT EXISTS idx_att ON attendance(user_id,event_time)");c.commit();c.close()

def parse_time(v):
 if v in (None,""):return now()
 s=str(v).strip()
 if s.isdigit():
  try:
   n=int(s)
   if n>100000000:return datetime.fromtimestamp(n,timezone.utc).astimezone(TZ)
  except:pass
 s=s.replace("Z","+00:00")
 for x in (s,s.replace("/","-")):
  try:
   d=datetime.fromisoformat(x);return (d.replace(tzinfo=TZ) if d.tzinfo is None else d).astimezone(TZ)
  except:pass
 for f in ("%Y-%m-%d %H:%M:%S","%Y/%m/%d %H:%M:%S","%Y-%m-%dT%H:%M:%S"):
  try:return datetime.strptime(s,f).replace(tzinfo=TZ)
  except:pass
 return now()

def first(d,*keys):
 if not isinstance(d,dict):return ""
 for k in keys:
  if d.get(k) not in (None,""):return d[k]
 return ""

def flatten(p):
 if not isinstance(p,dict):return {}
 ds=[p]
 for k in ("Data","data","Event","event","Record","record","Info","info","Params","params","AccessControl","accessControl"):
  v=p.get(k)
  if isinstance(v,dict):ds.append(v)
  elif isinstance(v,list):ds.extend(x for x in v if isinstance(x,dict))
 z={"user_id":"","user_name":"","event_time":now(),"event_type":"","status":"","method":"","rec_no":"","code":"","action":""}
 for d in ds:
  z["user_id"] or None;z["user_id"]=z["user_id"] or str(first(d,"UserID","userId","user_id","PersonID","personId","EmployeeID","employeeId","personCode","ID"))
  z["user_name"]=z["user_name"] or str(first(d,"CardName","UserName","userName","user_name","PersonName","personName","Name","name"))
  t=first(d,"CreateTime","EventTime","eventTime","event_time","AlarmDate","alarmDate","Time","time","RealTime")
  if t:z["event_time"]=parse_time(t)
  z["event_type"]=z["event_type"] or str(first(d,"Type","EventType","eventType","event_type","OperateType","operateType"))
  z["status"]=z["status"] or str(first(d,"Status","status","Result","result","ErrorCode","errorCode","syncFlags"))
  z["method"]=z["method"] or str(first(d,"Method","method","VerifyMethod","verifyMethod"))
  z["rec_no"]=z["rec_no"] or str(first(d,"RecNo","RecordNo","recordNo","Seq","seq"))
  z["code"]=z["code"] or str(first(d,"Code","code","EventCode","eventCode"));z["action"]=z["action"] or str(first(d,"Action","action"))
 return z

def good(i):return str(i.get("status","")).strip().lower() in SUCCESS
def direction(i):
 s=(str(i.get("event_type","")+" "+i.get("code","")+" "+i.get("action","")).lower())
 if any(x in s for x in ("exit","out","выход","leave")):return "EXIT"
 if any(x in s for x in ("entry","in","вход","enter")):return "ENTRY"
 return ""
def person_event(i):return bool(i.get("user_id") or i.get("user_name")) and str(i.get("code","")).lower() not in IGNORE

def insert(p):
 i=flatten(p)
 if not person_event(i):return False,i
 raw=json.dumps(p,ensure_ascii=False,sort_keys=True,default=str);base="|".join(str(i[k]) for k in ("rec_no","user_id","user_name","event_time","event_type","status","method","code"));key=hashlib.sha256((base+"|"+raw).encode()).hexdigest()
 c=db();cur=c.execute("INSERT OR IGNORE INTO attendance(event_key,user_id,user_name,event_time,event_type,status,method,direction,source,raw_payload) VALUES(?,?,?,?,?,?,?,?,?,?)",(key,i["user_id"],i["user_name"],i["event_time"].isoformat(),i["event_type"],i["status"],i["method"],"","dahua_http_push",raw));ins=cur.rowcount==1;c.commit();c.close();return ins,i

def previous(uid,t):
 c=db();r=c.execute("SELECT * FROM attendance WHERE user_id=? AND event_time<? AND (status IS NULL OR status='' OR lower(status) IN (%s)) ORDER BY event_time DESC,id DESC LIMIT 1"%(",".join("?" for _ in SUCCESS)),[str(uid),t.isoformat(),*SUCCESS]).fetchone();c.close();return r

def resolve(uid,t,explicit):
 if explicit:return explicit
 c=db();r=c.execute("SELECT COUNT(*) n FROM attendance WHERE user_id=? AND event_time<? AND (status IS NULL OR status='' OR lower(status) IN (%s))"%(",".join("?" for _ in SUCCESS)),[str(uid),t.isoformat(),*SUCCESS]).fetchone();c.close();return "EXIT" if r["n"]%2 else "ENTRY"

def duplicate(uid,t):
 r=previous(uid,t)
 if not r:return False
 try:return abs((t-datetime.fromisoformat(r["event_time"])).total_seconds())<60
 except:return False

def schedule(i):
 if LOOP and APP and good(i):asyncio.run_coroutine_threadsafe(notify(i),LOOP)
async def notify(i):
 uid=i["user_id"]
 if not uid or duplicate(uid,i["event_time"]):return
 d=resolve(uid,i["event_time"],direction(i));c=db();c.execute("UPDATE attendance SET direction=? WHERE user_id=? AND event_time=?",(d,uid,i["event_time"].isoformat()));links=c.execute("SELECT chat_id FROM telegram_users WHERE dahua_user_id=?",(uid,)).fetchall();c.commit();c.close()
 targets={int(x["chat_id"]) for x in links}
 try:targets.add(int(ADMIN_CHAT_ID))
 except:pass
 name=html.escape(i["user_name"] or uid);text=("🟢 <b>ВХОД</b>" if d=="ENTRY" else "🔴 <b>ВЫХОД</b>")+f"\n\n👤 {name}\n🆔 ID: {html.escape(uid)}\n🕐 {i['event_time'].strftime('%d.%m.%Y %H:%M:%S')}"
 if i["method"]:text+=f"\n🔐 Метод: {html.escape(i['method'])}"
 for chat in targets:
  try:await APP.bot.send_message(chat_id=chat,text=text,parse_mode="HTML")
  except Exception:log.exception("Telegram send failed chat=%s",chat)

def parse_body(raw,ct):
 if not raw:return {}
 s=raw.decode("utf-8","replace").strip();ct=(ct or "").lower()
 if "json" in ct or s.startswith(("{","[")):
  try:return json.loads(s)
  except:pass
 if "xml" in ct or s.startswith("<"):
  try:
   import xml.etree.ElementTree as ET;root=ET.fromstring(s);return {e.tag.split("}")[-1]:(e.text or "").strip() for e in root.iter() if e is not root and (e.text or "").strip()}
  except:pass
 if "multipart/" in ct:
  for part in raw.split(b"\r\n--"):
   p=part.find(b"\r\n\r\n")
   if p>=0:
    b=part[p+4:].strip().rstrip(b"-")
    try:return json.loads(b.decode("utf-8","replace"))
    except:pass
 q=parse_qs(s,keep_blank_values=True)
 if q:return {k:v[-1] if v else "" for k,v in q.items()}
 out={}
 for line in s.splitlines():
  if "=" in line:k,v=line.split("=",1);out[k.strip()]=v.strip()
 return out or {"raw":s[:20000]}

def payloads(p):
 if isinstance(p,list):return [x for x in p if isinstance(x,dict)]
 if not isinstance(p,dict):return []
 for k in ("Events","events","Records","records"):
  if isinstance(p.get(k),list):return [x for x in p[k] if isinstance(x,dict)]
 return [p]

class Handler(BaseHTTPRequestHandler):
 protocol_version="HTTP/1.1";server_version="FUNLANDIA-STAFF/5.0"
 def reply(self,text="OK"):
  b=text.encode()
  try:self.send_response(200);self.send_header("Content-Type","text/plain; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.send_header("Connection","close");self.end_headers();self.wfile.write(b);self.wfile.flush()
  except:pass
 def read_body(self):
  te=self.headers.get("Transfer-Encoding","").lower()
  if "chunked" in te:
   out=[]
   while True:
    line=self.rfile.readline().strip()
    if not line:continue
    try:n=int(line.split(b";",1)[0],16)
    except:break
    if n==0:break
    out.append(self.rfile.read(n));self.rfile.read(2)
   return b"".join(out)
  try:n=int(self.headers.get("Content-Length","0") or 0)
  except:n=0
  if n<=0:return b""
  old=self.connection.gettimeout();self.connection.settimeout(10);data=b""
  try:
   while len(data)<n:
    x=self.rfile.read(n-len(data))
    if not x:break
    data+=x
  except Exception:log.exception("Dahua body read")
  finally:
   try:self.connection.settimeout(old)
   except:pass
  return data
 def do_GET(self):log.info("DAHUA GET %s",urlparse(self.path).path);self.reply("FUNLANDIA STAFF OK")
 def do_POST(self):
  raw=self.read_body();path=urlparse(self.path).path;log.info("DAHUA POST path=%s type=%s bytes=%s preview=%r",path,self.headers.get("Content-Type",""),len(raw),raw[:2000].decode("utf-8","replace"))
  n=0
  try:
   for p in payloads(parse_body(raw,self.headers.get("Content-Type",""))):
    ins,i=insert(p)
    if i.get("user_id") or i.get("user_name"):log.info("DAHUA EVENT inserted=%s id=%s name=%s time=%s code=%s type=%s status=%s method=%s",ins,i.get("user_id"),i.get("user_name"),i.get("event_time"),i.get("code"),i.get("event_type"),i.get("status"),i.get("method"))
    if ins:n+=1;schedule(i)
  except Exception:log.exception("Dahua processing")
  log.info("DAHUA PUSH processed=%s new-events=%s",path,n);self.reply()
 def log_message(self,*a):pass

def http_server():ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()

def admin(update):return bool(ADMIN_CHAT_ID and str(update.effective_chat.id)==ADMIN_CHAT_ID)
def linked(chat):
 c=db();r=c.execute("SELECT dahua_user_id FROM telegram_users WHERE chat_id=?",(chat,)).fetchone();c.close();return r["dahua_user_id"] if r else None

def rows(day,uid=None):
 c=db();sql="SELECT * FROM attendance WHERE event_time LIKE ?";a=[day+"%"]
 if uid:sql+=" AND user_id=?";a.append(str(uid))
 r=c.execute(sql+" ORDER BY event_time,id",a).fetchall();c.close();return [x for x in r if str(x["status"] or "").lower() in SUCCESS]

def calc(rs):
 opened=None;first=None;worked=0;last=None
 for r in rs:
  t=datetime.fromisoformat(r["event_time"]);d=r["direction"] or direction({"event_type":r["event_type"],"code":""})
  if not d:d="ENTRY" if opened is None else "EXIT"
  if d=="ENTRY":first=first or t;opened=t
  elif opened:
   if t>=opened:worked+=int((t-opened).total_seconds())
   last=t;opened=None
 if opened:worked+=max(0,int((now()-opened).total_seconds()))
 return opened is not None,first,last,worked

def fmtsec(s):h,m=divmod(max(0,int(s)),3600);m//=60;return f"{h} ч {m:02d} мин" if h else f"{m} мин"
def lateness(t):
 try:h,m=map(int,SHIFT_START.split(":"));start=t.replace(hour=h,minute=m,second=0,microsecond=0);return max(0,int((t-start).total_seconds()/60))
 except:return 0

async def start(u,c):
 x=u.effective_user;t=now().isoformat();con=db();con.execute("INSERT INTO telegram_users(chat_id,username,first_name,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,updated_at=excluded.updated_at",(u.effective_chat.id,x.username if x else "",x.first_name if x else "",t,t));con.commit();con.close();await u.message.reply_text("👷 <b>Бот сотрудников FUNLANDIA</b>\nDahua подключён напрямую.\n\nВыберите раздел.",parse_mode="HTML",reply_markup=MENU)
async def link(u,c):
 if ADMIN_CHAT_ID and not admin(u):return await u.message.reply_text("🔒 Привязку выполняет руководитель.",reply_markup=MENU)
 if not c.args:return await u.message.reply_text("Использование: /link ID",reply_markup=MENU)
 uid=c.args[0].strip();x=u.effective_user;t=now().isoformat();con=db();con.execute("INSERT INTO telegram_users(chat_id,dahua_user_id,username,first_name,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET dahua_user_id=excluded.dahua_user_id,updated_at=excluded.updated_at",(u.effective_chat.id,uid,x.username if x else "",x.first_name if x else "",t,t));con.commit();con.close();await u.message.reply_text(f"✅ Telegram привязан к ID Dahua <b>{html.escape(uid)}</b>.",parse_mode="HTML",reply_markup=MENU)
async def today(u,c):await u.message.reply_text(dashboard(),reply_markup=MENU)
def dashboard(day=None):
 day=day or now().strftime("%Y-%m-%d");groups={}
 for r in rows(day):groups.setdefault(str(r["user_id"] or r["user_name"]),[]).append(r)
 ps=[]
 for uid,rs in groups.items():present,fi,lo,w=calc(rs);ps.append((present,rs[-1]["user_name"] or uid,fi,lo,w))
 lines=[f"📊 <b>Сегодня {day}</b>",f"👥 Отметились: {len(ps)}",f"🟢 Сейчас на работе: {sum(1 for x in ps if x[0])}",""]
 for p in sorted(ps,key=lambda x:(not x[0],x[1].lower())):lines.append(("🟢" if p[0] else "🔴")+f" {html.escape(p[1])} — {fmtsec(p[4])}")
 return "\n".join(lines)
async def current(u,c):await u.message.reply_text(dashboard(),reply_markup=MENU)
async def me(u,c):
 uid=linked(u.effective_chat.id)
 if not uid:return await u.message.reply_text("Сначала руководитель должен привязать ваш Telegram к ID Dahua.",reply_markup=MENU)
 rs=rows(now().strftime("%Y-%m-%d"),uid)
 if not rs:return await u.message.reply_text("Сегодня записей пока нет.",reply_markup=MENU)
 lines=["👤 <b>Мои записи сегодня</b>"]
 for r in rs:lines.append(f"{('🟢' if r['direction']=='ENTRY' else '🔴' if r['direction']=='EXIT' else '•')} {datetime.fromisoformat(r['event_time']).strftime('%H:%M:%S')} — {r['direction'] or 'проход'}")
 await u.message.reply_text("\n".join(lines),parse_mode="HTML",reply_markup=MENU)
async def myreport(u,c):
 uid=linked(u.effective_chat.id)
 if not uid:return await u.message.reply_text("Telegram ещё не привязан к ID Dahua.",reply_markup=MENU)
 rs=rows(now().strftime("%Y-%m-%d"),uid);p,fi,lo,w=calc(rs);await u.message.reply_text(f"📋 <b>Мой отчёт</b>\n\nВход: {fi.strftime('%H:%M:%S') if fi else '—'}\nСтатус: {'🟢 на работе' if p else '🔴 не на работе'}\nОтработано: {fmtsec(w)}\nОпоздание: {lateness(fi) if fi else 0} мин",parse_mode="HTML",reply_markup=MENU)
def period(start,end):
 out={};d=start
 while d<=end:
  for r in rows(d.isoformat()):
   uid=str(r["user_id"] or r["user_name"]);x=out.setdefault(uid,{"name":r["user_name"] or uid,"days":0,"worked":0,"late":0})
   # Count each employee-day once; calculate time from that day's records.
  d+=timedelta(days=1)
 for uid,x in out.items():pass
 # rebuild accurately
 out={};d=start
 while d<=end:
  groups={}
  for r in rows(d.isoformat()):groups.setdefault(str(r["user_id"] or r["user_name"]),[]).append(r)
  for uid,rs in groups.items():
   p,fi,lo,w=calc(rs);x=out.setdefault(uid,{"name":rs[-1]["user_name"] or uid,"days":0,"worked":0,"late":0});x["days"]+=1;x["worked"]+=w;x["late"]+=lateness(fi) if fi else 0
  d+=timedelta(days=1)
 return sorted(out.values(),key=lambda x:x["name"].lower())
async def weekly(u,c):
 if not admin(u):return await u.message.reply_text("🔒 Недельный отчёт доступен только администратору.",reply_markup=MENU)
 today=now().date();start=today-timedelta(days=today.weekday());ps=period(start,today);text="📅 <b>Недельный отчёт</b>\n\n"+"\n".join(f"👤 {html.escape(x['name'])}\n   Дней: {x['days']} | Время: {fmtsec(x['worked'])} | Опоздание: {x['late']} мин" for x in ps) if ps else "📅 <b>Недельный отчёт</b>\n\nНет записей.";await u.message.reply_text(text,parse_mode="HTML",reply_markup=MENU)
async def monthly(u,c):
 if not admin(u):return await u.message.reply_text("🔒 Месячный отчёт доступен только администратору.",reply_markup=MENU)
 today=now().date();start=today.replace(day=1);ps=period(start,today);text="🗓 <b>Месячный отчёт</b>\n\n"+"\n".join(f"👤 {html.escape(x['name'])}\n   Дней: {x['days']} | Время: {fmtsec(x['worked'])} | Опоздание: {x['late']} мин" for x in ps) if ps else "🗓 <b>Месячный отчёт</b>\n\nНет записей.";await u.message.reply_text(text,parse_mode="HTML",reply_markup=MENU)
async def help_cmd(u,c):await u.message.reply_text("ℹ️ /link ID — привязка сотрудника\n/last — последние события\n/report YYYY-MM-DD — отчёт за день\n\nКнопки открывают основные отчёты.",reply_markup=MENU)
async def last(u,c):
 con=db();rs=con.execute("SELECT * FROM attendance ORDER BY event_time DESC,id DESC LIMIT 20").fetchall();con.close();await u.message.reply_text("📌 <b>Последние события</b>\n\n"+"\n".join(f"{r['event_time'][11:19]} — {html.escape(r['user_name'] or r['user_id'] or '?')} — {r['direction'] or 'проход'}" for r in rs) if rs else "Записей нет.",parse_mode="HTML",reply_markup=MENU)
async def report(u,c):
 if not admin(u):return await u.message.reply_text("🔒 Дневной отчёт доступен только администратору.",reply_markup=MENU)
 day=c.args[0] if c.args else now().strftime("%Y-%m-%d");await u.message.reply_text(dashboard(day),parse_mode="HTML",reply_markup=MENU)
async def buttons(u,c):
 t=u.message.text
 if t=="📊 Сегодня":return await today(u,c)
 if t=="👥 Сейчас на работе":return await current(u,c)
 if t=="📅 Неделя":return await weekly(u,c)
 if t=="🗓 Месяц":return await monthly(u,c)
 if t=="👤 Мои записи":return await me(u,c)
 if t=="📋 Мой отчёт":return await myreport(u,c)
 if t=="ℹ️ Помощь":return await help_cmd(u,c)
 await u.message.reply_text("Используйте кнопки меню.",reply_markup=MENU)

def main():
 global LOOP,APP
 if not BOT_TOKEN:raise RuntimeError("BOT_TOKEN is not set")
 init_db();threading.Thread(target=http_server,daemon=True,name="dahua-http").start()
 app=Application.builder().token(BOT_TOKEN).post_init(lambda a:set_globals(a)).build();APP=app
 for cmd,fn in (("start",start),("help",help_cmd),("today",today),("week",weekly),("month",monthly),("link",link),("me",me),("report",report),("last",last)):app.add_handler(CommandHandler(cmd,fn))
 app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,buttons));log.info("FUNLANDIA STAFF BOT STARTED admin=%s",ADMIN_CHAT_ID);app.run_polling(drop_pending_updates=False)
def set_globals(app):
 global LOOP,APP;LOOP=asyncio.get_running_loop();APP=app
if __name__=="__main__":main()
