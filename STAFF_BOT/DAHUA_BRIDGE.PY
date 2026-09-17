
import os,re,json,sqlite3,hashlib,logging,asyncio
from datetime import datetime,timedelta,timezone
from io import BytesIO
import requests
from requests.auth import HTTPDigestAuth
from telegram import Update,ReplyKeyboardMarkup,InlineKeyboardButton,InlineKeyboardMarkup
from telegram.ext import Application,CommandHandler,MessageHandler,ContextTypes,CallbackQueryHandler,filters
import qrcode

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("funlandia_staff_secure")
BOT_TOKEN=os.getenv("BOT_TOKEN","").strip()
DAHUA_URL=os.getenv("DAHUA_URL","https://192.168.1.202").rstrip("/")
DAHUA_USER=os.getenv("DAHUA_USER","admin").strip()
DAHUA_PASSWORD=os.getenv("DAHUA_PASSWORD","").strip()
DB_PATH=os.getenv("STAFF_DB_PATH","/data/staff.db")
ADMIN_ID=os.getenv("STAFF_ADMIN_CHAT_ID","").strip()
CONTROL_IDS={x.strip() for x in os.getenv("STAFF_CONTROL_IDS","").split(",") if x.strip()}
TZ=timezone(timedelta(hours=5))
POLL=int(os.getenv("DAHUA_POLL_SECONDS","10"))
EXTRA_MEAL_COST=int(os.getenv("EXTRA_MEAL_COST","0"))
LUNCH_START=int(os.getenv("LUNCH_START","10:00").split(":")[0])*60+int(os.getenv("LUNCH_START","10:00").split(":")[1])
LUNCH_END=int(os.getenv("LUNCH_END","15:00").split(":")[0])*60+int(os.getenv("LUNCH_END","15:00").split(":")[1])
DINNER_START=int(os.getenv("DINNER_START","17:00").split(":")[0])*60+int(os.getenv("DINNER_START","17:00").split(":")[1])
DINNER_END=int(os.getenv("DINNER_END","22:00").split(":")[0])*60+int(os.getenv("DINNER_END","22:00").split(":")[1])

def now(): return datetime.now(TZ)
def db():
    c=sqlite3.connect(DB_PATH,timeout=30); c.row_factory=sqlite3.Row; return c

def init_db():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS employees(
      dahua_id TEXT PRIMARY KEY,name TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,
      telegram_id INTEGER,role TEXT NOT NULL DEFAULT 'employee',created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS attendance(
      rec_no TEXT PRIMARY KEY,user_id TEXT NOT NULL,name TEXT NOT NULL,event_time TEXT NOT NULL,
      event_type TEXT NOT NULL,status INTEGER NOT NULL,raw TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS meals(
      id INTEGER PRIMARY KEY AUTOINCREMENT,dahua_id TEXT NOT NULL,name TEXT NOT NULL,
      meal_type TEXT NOT NULL,meal_date TEXT NOT NULL,requested_at TEXT NOT NULL,
      served_at TEXT,returned_at TEXT,status TEXT NOT NULL DEFAULT 'requested',
      extra INTEGER NOT NULL DEFAULT 0, UNIQUE(dahua_id,meal_type,meal_date))""")
    c.execute("""CREATE TABLE IF NOT EXISTS access_requests(
      telegram_id INTEGER PRIMARY KEY,username TEXT,first_name TEXT,requested_role TEXT NOT NULL,
      created_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending')""")
    c.execute("""CREATE TABLE IF NOT EXISTS registration_requests(
      telegram_id INTEGER PRIMARY KEY,dahua_id TEXT NOT NULL,name TEXT NOT NULL,
      username TEXT,created_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending')""")
    c.execute("CREATE TABLE IF NOT EXISTS user_roles(telegram_id INTEGER PRIMARY KEY,role TEXT NOT NULL)")
    c.execute("""CREATE TABLE IF NOT EXISTS staff_requests(
      id INTEGER PRIMARY KEY AUTOINCREMENT,staff_id TEXT UNIQUE NOT NULL,
      last_name TEXT NOT NULL,first_name TEXT NOT NULL,middle_name TEXT NOT NULL,
      phone TEXT NOT NULL,created_by INTEGER NOT NULL,created_at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'waiting_face',dahua_id TEXT)""")
    c.commit(); c.close()

def tg_send(chat_id,text,markup=None):
    if not chat_id or not BOT_TOKEN:return
    try:
        p={"chat_id":int(chat_id),"text":text}
        if markup:p["reply_markup"]=markup
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json=p,timeout=8,proxies={"http":None,"https":None})
    except Exception: pass

def parse_time(v):
    s=str(v or "").strip()
    if s.isdigit() and len(s)>=9:
        n=int(s); n=n/1000 if n>10_000_000_000 else n
        return datetime.fromtimestamp(n,timezone.utc).astimezone(TZ)
    s=s.replace("Z","+00:00")
    for fmt in (None,"%Y-%m-%d %H:%M:%S","%Y/%m/%d %H:%M:%S"):
        try:
            d=datetime.fromisoformat(s) if fmt is None else datetime.strptime(s,fmt)
            return (d if d.tzinfo else d.replace(tzinfo=TZ)).astimezone(TZ)
        except Exception: pass
    return now()

def dahua_get(path,params):
    r=requests.get(DAHUA_URL+path,params=params,auth=HTTPDigestAuth(DAHUA_USER,DAHUA_PASSWORD),verify=False,timeout=15)
    r.raise_for_status(); return r

def dahua_user(uid):
    try:
        r=dahua_get("/cgi-bin/Attendance.cgi",{"action":"getUser","UserID":str(uid)})
        txt=r.text.strip()
        try:
            data=r.json()
            obj=data.get("UserInfo",data)
            name=obj.get("UserName") or obj.get("Name")
            if name:return str(name)
        except Exception: pass
        m=re.search(r'"(?:UserName|Name)"\s*:\s*"([^"]+)"',txt)
        if m:return m.group(1)
    except Exception as e: log.warning("Dahua getUser %s: %s",uid,e)
    return None

def dahua_users():
    """Return access-control users currently known by Dahua."""
    try:
        r=dahua_get("/cgi-bin/Attendance.cgi",{"action":"findUser","Offset":"0","Count":"100"})
        data=r.json()
        return data.get("UserInfo",[]) if isinstance(data,dict) else []
    except Exception as e:
        log.warning("Dahua findUser failed: %s",e)
        return []

def normalize_name(*parts):
    return " ".join(str(x or "").strip().lower().split())

def next_staff_id(c):
    rows=c.execute("SELECT staff_id FROM staff_requests ORDER BY id DESC LIMIT 1").fetchall()
    n=0
    if rows:
        m=re.search(r"(\d+)$",rows[0]["staff_id"] or "")
        if m:n=int(m.group(1))
    return f"EMP-{n+1:03d}"

def pending_face_matches(c):
    users=dahua_users()
    if not users:return []
    out=[]
    pending=c.execute("SELECT * FROM staff_requests WHERE status='waiting_face' ORDER BY id").fetchall()
    used={str(r["dahua_id"]) for r in c.execute("SELECT dahua_id FROM employees WHERE dahua_id IS NOT NULL").fetchall()}
    for req in pending:
        wanted=normalize_name(req["last_name"],req["first_name"],req["middle_name"])
        matches=[]
        for u in users:
            uid=str(u.get("UserID","")).strip(); name=str(u.get("UserName","")).strip()
            if uid and uid not in used and normalize_name(name)==wanted:
                matches.append((uid,name))
        if len(matches)==1:out.append((req,matches[0][0],matches[0][1]))
        elif len(matches)>1:out.append((req,None,"MULTIPLE"))
    return out

def get_records(start,end):
    p={"action":"find","name":"AccessControlCardRec","StartTime":str(int(start.timestamp())),"EndTime":str(int(end.timestamp())),"count":"1024"}
    r=dahua_get("/cgi-bin/recordFinder.cgi",p)
    rows={}
    for line in r.text.replace("\r","").splitlines():
        m=re.match(r"records\[(\d+)\]\.([^=]+)=(.*)$",line)
        if m: rows.setdefault(m.group(1),{})[m.group(2)]=m.group(3)
    return list(rows.values())

def ensure_employee(c,uid,name):
    if not uid:return
    row=c.execute("SELECT dahua_id,name FROM employees WHERE dahua_id=?",(uid,)).fetchone()
    if not row:
        c.execute("INSERT INTO employees(dahua_id,name,active,telegram_id,role,created_at) VALUES(?,?,?,?,?,?)",(uid,name or uid,1,None,"employee",now().isoformat()))
    elif name and (not row["name"] or row["name"]==uid):
        c.execute("UPDATE employees SET name=? WHERE dahua_id=?",(name,uid))

def import_records(records):
    c=db(); new=[]
    for x in records:
        uid=str(x.get("UserID","")).strip()
        if not uid: continue
        if int(x.get("Status","1") or 1)!=1 or int(x.get("ErrorCode","0") or 0)!=0: continue
        rec=str(x.get("RecNo","")).strip() or hashlib.sha1(json.dumps(x,sort_keys=True).encode()).hexdigest()
        tm=parse_time(x.get("CreateTime"))
        typ=str(x.get("Type","")).strip()
        if typ not in ("Entry","Exit"): typ="Entry"
        name=str(x.get("CardName","")).strip() or dahua_user(uid) or uid
        ensure_employee(c,uid,name)
        try:
            c.execute("INSERT INTO attendance VALUES(?,?,?,?,?,?,?)",(rec,uid,name,tm.isoformat(),typ,1,json.dumps(x,ensure_ascii=False)))
            new.append((uid,name,tm,typ))
        except sqlite3.IntegrityError: pass
    c.commit(); c.close()
    return new

def last_events(uid,date=None):
    c=db(); q="SELECT * FROM attendance WHERE user_id=?"; args=[str(uid)]
    if date:q+=" AND date(event_time)=?";args.append(date)
    q+=" ORDER BY event_time"
    rows=c.execute(q,args).fetchall();c.close();return rows

def shift_for(uid,date):
    rows=last_events(uid,date)
    ins=[r for r in rows if r["event_type"]=="Entry"];outs=[r for r in rows if r["event_type"]=="Exit"]
    if not ins:return "—"
    e=datetime.fromisoformat(ins[0]["event_time"]); x=datetime.fromisoformat(outs[-1]["event_time"]) if outs else None
    eh=e.hour+e.minute/60; xh=(x.hour+x.minute/60) if x else None
    if xh is not None and xh>=21.75 and 9.75<=eh<=10.25:return "Нестандартная"
    if xh is not None and xh>=21.25:return "2-я"
    if xh is not None and xh<=20.75:return "1-я"
    return "1-я" if eh<12.5 else "2-я"

def role(uid):
    s=str(uid)
    if ADMIN_ID and s==ADMIN_ID:return "owner"
    if s in CONTROL_IDS:return "control"
    c=db();r=c.execute("SELECT role FROM user_roles WHERE telegram_id=?",(int(uid),)).fetchone()
    if r:c.close();return r["role"]
    r=c.execute("SELECT role FROM employees WHERE telegram_id=? AND active=1",(int(uid),)).fetchone();c.close()
    return r["role"] if r else "none"

def keyboard(r):
    if r=="owner":
        return ReplyKeyboardMarkup([
            ["👥 Сотрудники","➕ Добавить сотрудника"],
            ["📊 Контроль","🍽 Питание"],
            ["📊 Отчёты","📱 QR столовой"]],resize_keyboard=True)
    if r=="control":
        return ReplyKeyboardMarkup([
            ["👥 Сейчас на работе"],
            ["🔴 Опоздали","⚠️ Ранее ушли"],
            ["🍽 Сейчас на обеде"],
            ["➕ Добавить сотрудника"]],resize_keyboard=True)
    if r=="canteen":
        return ReplyKeyboardMarkup([
            ["🍽 Сегодня питание","📅 Неделя"],
            ["🗓 Месяц","📅 1–15"],
            ["📅 16–конец месяца"],
            ["📱 Проверить QR"]],resize_keyboard=True)
    if r=="employee":
        return ReplyKeyboardMarkup([
            ["👤 Мои записи","📋 Мой отчёт"],
            ["🍽 Питание","📱 QR столовой"],
            ["ℹ️ Помощь"]],resize_keyboard=True)
    return ReplyKeyboardMarkup([["🔐 Получить доступ"]],resize_keyboard=True)

async def start(update,ctx):
    r=role(update.effective_user.id)
    if ctx.args and ctx.args[0]=="meal":
        if r=="employee":return await meal_menu(update,ctx)
        await update.message.reply_text("🔒 Сначала получите подтверждённый доступ.",reply_markup=keyboard(r));return
    await update.message.reply_text(f"👋 Staff Bot Funlandia\nРоль: {r}",reply_markup=keyboard(r))

async def access_request(update,ctx):
    u=update.effective_user
    c=db();c.execute("INSERT OR REPLACE INTO access_requests VALUES(?,?,?,?,?,?)",(u.id,u.username,u.first_name,"employee",now().isoformat(),"pending"));c.commit();c.close()
    if ADMIN_ID:
        mk={"inline_keyboard":[[
            {"text":"👤 Сотрудник","callback_data":f"access:employee:{u.id}"},
            {"text":"🍽 Столовая","callback_data":f"access:canteen:{u.id}"}],
            [{"text":"📊 Контроль","callback_data":f"access:control:{u.id}"},
             {"text":"❌ Отклонить","callback_data":f"access:deny:{u.id}"}]]}
        tg_send(ADMIN_ID,f"🆕 Запрос доступа\n👤 {u.first_name or ''} @{u.username or '—'}\n🆔 Telegram ID: {u.id}",mk)
    await update.message.reply_text("⏳ Заявка отправлена администратору.")

async def access_cb(update,ctx):
    q=update.callback_query;await q.answer()
    if role(q.from_user.id)!="owner":return await q.edit_message_text("🔒 Только владелец.")
    _,act,tid=q.data.split(":");tid=int(tid);c=db()
    if act=="deny":
        c.execute("UPDATE access_requests SET status='denied' WHERE telegram_id=?",(tid,));c.commit();c.close();tg_send(tid,"❌ Доступ отклонён.");return await q.edit_message_text("❌ Отклонено.")
    c.execute("INSERT OR REPLACE INTO user_roles VALUES(?,?)",(tid,act));c.execute("UPDATE access_requests SET status='approved',requested_role=? WHERE telegram_id=?",(act,tid));c.commit();c.close()
    tg_send(tid,f"✅ Доступ подтверждён.\nРоль: {act}")
    await q.edit_message_text(f"✅ Доступ выдан: {act}")

async def registration_input(update,ctx):
    await update.message.reply_text("🔒 Самостоятельная регистрация Face ID отключена. Новый сотрудник добавляется только владельцем или контролем.")

async def reg_cb(update,ctx):
    q=update.callback_query;await q.answer()
    if role(q.from_user.id)!="owner":return await q.edit_message_text("🔒 Только владелец.")
    _,act,req_id=q.data.split(":");req_id=int(req_id);c=db();req=c.execute("SELECT * FROM staff_requests WHERE id=?",(req_id,)).fetchone()
    if not req:c.close();return await q.edit_message_text("Заявка не найдена.")
    if act=="no":
        c.execute("UPDATE staff_requests SET status='rejected' WHERE id=?",(req_id));c.commit();c.close()
        tg_send(req["created_by"],f"❌ Владелец отклонил сотрудника: {req['last_name']} {req['first_name']} {req['middle_name']}")
        return await q.edit_message_text("❌ Сотрудник отклонён.")
    if not req["dahua_id"]:
        c.close();return await q.edit_message_text("❌ Face ID ещё не зарегистрирован в Dahua.")
    name=f"{req['last_name']} {req['first_name']} {req['middle_name']}"
    c.execute("INSERT OR REPLACE INTO employees(dahua_id,name,active,telegram_id,role,created_at) VALUES(?,?,?,?,?,?)",(req["dahua_id"],name,1,None,"employee",now().isoformat()))
    c.execute("UPDATE staff_requests SET status='approved' WHERE id=?",(req_id,));c.commit();c.close()
    tg_send(req["created_by"],f"✅ Владелец подтвердил приём сотрудника.\n\n👤 {name}\n🆔 {req['staff_id']}\n🔐 Dahua Face ID: {req['dahua_id']}\n🍽 Питание подключено автоматически.")
    return await q.edit_message_text(f"✅ Сотрудник принят.\n{name}\n{req['staff_id']}\nDahua Face ID: {req['dahua_id']}")

async def employees(update,ctx):
    if role(update.effective_user.id)!="owner":return
    c=db();rows=c.execute("SELECT * FROM employees ORDER BY active DESC,name").fetchall();c.close()
    if not rows:return await update.message.reply_text("Сотрудников пока нет.")
    for e in rows[:100]:
        st="🟢" if e["active"] else "🔴"
        mk={"inline_keyboard":[[{"text":"🚫 Уволить" if e["active"] else "♻️ Активировать","callback_data":f"emp:{'off' if e['active'] else 'on'}:{e['dahua_id']}"}]]}
        await update.message.reply_text(f"{st} {e['name']}\n🆔 Dahua Face ID: {e['dahua_id']}\nTelegram: {e['telegram_id'] or '—'}",reply_markup=mk)

async def emp_cb(update,ctx):
    q=update.callback_query;await q.answer()
    if role(q.from_user.id)!="owner":return await q.edit_message_text("🔒 Только владелец.")
    _,act,uid=q.data.split(":");c=db()
    if act=="off":
        c.execute("UPDATE employees SET active=0,telegram_id=NULL WHERE dahua_id=?",(uid,));msg="🚫 Сотрудник уволен. Питание и активный доступ отключены. История сохранена."
    else:
        c.execute("UPDATE employees SET active=1 WHERE dahua_id=?",(uid,));msg="♻️ Сотрудник повторно активирован. Питание снова включено."
    c.commit();c.close();await q.edit_message_text(msg)

def staff_name(req):
    return f"{req['last_name']} {req['first_name']} {req['middle_name']}"

async def owner_add_start(update,ctx):
    if role(update.effective_user.id) not in ("owner","control"):return
    ctx.user_data["add_staff_step"]="last"
    ctx.user_data["add_staff"]={}
    await update.message.reply_text("➕ Добавление сотрудника\n\nВведите ФАМИЛИЮ:")

async def owner_add_input(update,ctx):
    r=role(update.effective_user.id)
    if r not in ("owner","control") or not ctx.user_data.get("add_staff_step"): return False
    text=(update.message.text or "").strip()
    step=ctx.user_data["add_staff_step"]; data=ctx.user_data["add_staff"]
    if step=="last": data["last_name"]=text;ctx.user_data["add_staff_step"]="first";await update.message.reply_text("Введите ИМЯ:");return True
    if step=="first": data["first_name"]=text;ctx.user_data["add_staff_step"]="middle";await update.message.reply_text("Введите ОТЧЕСТВО:");return True
    if step=="middle": data["middle_name"]=text;ctx.user_data["add_staff_step"]="phone";await update.message.reply_text("Введите номер телефона:");return True
    if step=="phone":
        data["phone"]=text
        c=db();sid=next_staff_id(c)
        c.execute("INSERT INTO staff_requests(staff_id,last_name,first_name,middle_name,phone,created_by,created_at,status) VALUES(?,?,?,?,?,?,?,?)",(sid,data["last_name"],data["first_name"],data["middle_name"],data["phone"],update.effective_user.id,now().isoformat(),"waiting_face"));req_id=c.execute("SELECT last_insert_rowid() id").fetchone()["id"];c.commit();c.close()
        ctx.user_data.pop("add_staff_step",None);ctx.user_data.pop("add_staff",None)
        name=f"{data['last_name']} {data['first_name']} {data['middle_name']}"
        await update.message.reply_text(f"✅ Данные сохранены.\n\n👤 {name}\n📞 {data['phone']}\n🆔 {sid}\n\n📸 Теперь зарегистрируйте лицо сотрудника на терминале Dahua.\n\nПосле регистрации бот автоматически найдёт его по ФИО. Номер Face ID вводить не нужно.")
        if r=="owner":
            await update.message.reply_text("ℹ️ Так как заявку создал владелец, после обнаружения Face ID сотрудник будет активирован автоматически.")
        else:
            await update.message.reply_text("ℹ️ После регистрации лица готовая заявка придёт владельцу на окончательное подтверждение.")
        return True
    return False

async def report_menu(update,ctx):
    if role(update.effective_user.id)!="owner":return
    await update.message.reply_text("📊 Отчёты владельца",reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Приход/уход — Сегодня",callback_data="report:att_today")],
        [InlineKeyboardButton("👥 Приход/уход — 1–15",callback_data="report:att_1"),InlineKeyboardButton("👥 16–конец",callback_data="report:att_2")],
        [InlineKeyboardButton("👥 Приход/уход — Месяц",callback_data="report:att_month")],
        [InlineKeyboardButton("🍽 Питание — Сегодня",callback_data="report:meal_today")],
        [InlineKeyboardButton("🍽 Питание — 1–15",callback_data="report:meal_1"),InlineKeyboardButton("🍽 Питание — 16–конец",callback_data="report:meal_2")],
        [InlineKeyboardButton("🍽 Питание — Месяц",callback_data="report:meal_month")]]))

async def report_cb(update,ctx):
    q=update.callback_query;await q.answer()
    if role(q.from_user.id)!="owner":return
    kind=q.data.split(":",1)[1];d=now()
    if kind.startswith("att_"):
        k=kind[4:]
        if k=="today":start,end=d.date(),d.date()
        elif k=="1":start,end=d.replace(day=1).date(),d.replace(day=15).date()
        elif k=="2":
            import calendar
            start,end=d.replace(day=16).date(),d.replace(day=calendar.monthrange(d.year,d.month)[1]).date()
        else:start,end=month_range();start,end=start.date(),min(end,now()).date()
        c=db();emps=c.execute("SELECT * FROM employees ORDER BY name").fetchall();c.close();lines=[]
        for e in emps:
            c=db();rows=c.execute("SELECT * FROM attendance WHERE user_id=? AND date(event_time) BETWEEN ? AND ? ORDER BY event_time",(e["dahua_id"],start.isoformat(),end.isoformat())).fetchall();c.close()
            byday={}
            for r in rows:byday.setdefault(r["event_time"][:10],[]).append(r)
            if not byday:continue
            days=sum(1 for rs in byday.values() if any(x["event_type"]=="Entry" for x in rs));late=early=0
            for day,rs in byday.items():
                ins=[x for x in rs if x["event_type"]=="Entry"];outs=[x for x in rs if x["event_type"]=="Exit"];sh=shift_for(e["dahua_id"],day)
                if ins:
                    t=datetime.fromisoformat(ins[0]["event_time"]);limit=10 if sh in ("1-я","Нестандартная") else 13
                    if t.hour*60+t.minute>limit*60+5:late+=1
                if outs:
                    t=datetime.fromisoformat(outs[-1]["event_time"]);limit=21 if sh=="1-я" else 22
                    if t.hour<limit:early+=1
            lines.append(f"👤 {e['name']} — дней: {days}, ⏰ опозданий: {late}, ⚠️ ранних уходов: {early}")
        await q.edit_message_text(f"📊 ПРИХОД/УХОД\n{start:%d.%m.%Y} — {end:%d.%m.%Y}\n\n"+"\n".join(lines) if lines else f"📊 ПРИХОД/УХОД\n{start:%d.%m.%Y} — {end:%d.%m.%Y}\n\nНет данных.")
        return
    k=kind[5:]
    if k=="today":start=end=d.date()
    elif k=="1":start,end=d.replace(day=1).date(),d.replace(day=15).date()
    elif k=="2":
        import calendar
        start,end=d.replace(day=16).date(),d.replace(day=calendar.monthrange(d.year,d.month)[1]).date()
    else:start,end=d.replace(day=1).date(),d.date()
    c=db();rows=c.execute("SELECT name,meal_type,COUNT(*) n,SUM(extra) extra FROM meals WHERE meal_date BETWEEN ? AND ? GROUP BY name,meal_type ORDER BY name,meal_type",(start.isoformat(),end.isoformat())).fetchall();tot=c.execute("SELECT COUNT(*) n,SUM(extra) extra FROM meals WHERE meal_date BETWEEN ? AND ?",(start.isoformat(),end.isoformat())).fetchone();c.close()
    text=[f"🍽 ПИТАНИЕ — {start:%d.%m.%Y} — {end:%d.%m.%Y}",f"Всего талонов: {tot['n'] or 0}",f"➕ Дополнительных: {tot['extra'] or 0}",""]
    text += [f"👤 {r['name']} — {r['meal_type']}: {r['n']} (доп.: {r['extra'] or 0})" for r in rows] or ["Нет записей."]
    await q.edit_message_text("\n".join(text))

def meal_entitlement(uid,kind):
    date=now().date().isoformat();sh=shift_for(uid,date)
    if kind=="Обед":return sh in ("1-я","Нестандартная")
    return sh in ("1-я","2-я","Нестандартная")

async def meal_menu(update,ctx):
    tg=update.effective_user.id;c=db();e=c.execute("SELECT * FROM employees WHERE telegram_id=? AND active=1",(tg,)).fetchone();c.close()
    if not e:return await update.message.reply_text("🔒 Вы не зарегистрированы для питания.")
    date=now().date().isoformat()
    c=db();rows=c.execute("SELECT meal_type,status,extra FROM meals WHERE dahua_id=? AND meal_date=?",(e["dahua_id"],date)).fetchall();c.close()
    have={r["meal_type"]:r for r in rows}
    buttons=[]
    for kind in ("Обед","Ужин"):
        if kind in have:
            r=have[kind];label=f"{'🥗' if kind=='Обед' else '🍽'} {kind}: {r['status']}"
            if r["status"]=="served": buttons.append([InlineKeyboardButton("🔙 Вернулся с "+kind.lower(),callback_data=f"mealreturn:{kind}")])
        else:
            extra=0 if meal_entitlement(e["dahua_id"],kind) else 1
            cost=EXTRA_MEAL_COST if extra else 0
            label=f"{'🥗' if kind=='Обед' else '🍽'} {kind}{' — ДОП.' if extra else ''}{f' ({cost:,} сум)' if cost else ''}"
            buttons.append([InlineKeyboardButton(label,callback_data=f"meal:{kind}:{extra}")])
    await update.message.reply_text(f"🍽 Питание\n👤 {e['name']}\n🔄 Смена: {shift_for(e['dahua_id'],date)}",reply_markup=InlineKeyboardMarkup(buttons))

async def meal_cb(update,ctx):
    q=update.callback_query;await q.answer();tg=q.from_user.id
    c=db();e=c.execute("SELECT * FROM employees WHERE telegram_id=? AND active=1",(tg,)).fetchone();c.close()
    if not e:return await q.edit_message_text("🔒 Доступ запрещён.")
    _,kind,extra=q.data.split(":");date=now().date().isoformat()
    if not (LUNCH_START<=now().hour*60+now().minute<=LUNCH_END or DINNER_START<=now().hour*60+now().minute<=DINNER_END):
        return await q.edit_message_text("⏰ Сейчас столовая вне времени питания.")
    if kind=="Обед" and not meal_entitlement(e["dahua_id"],kind) and not extra:
        extra=1
    c=db()
    try:
        c.execute("INSERT INTO meals(dahua_id,name,meal_type,meal_date,requested_at,extra) VALUES(?,?,?,?,?,?)",(e["dahua_id"],e["name"],kind,date,now().isoformat(),int(extra)))
        c.commit()
    except sqlite3.IntegrityError:
        c.close();return await q.edit_message_text("ℹ️ Этот приём пищи уже оформлен сегодня.")
    c.close()
    await q.edit_message_text(f"✅ Заявка на {kind.lower()} принята.\n\n{'⚠️ Это дополнительное питание.' if int(extra) else 'Это питание по норме.'}\nОжидайте выдачу.")
    notify_canteen(e["name"],kind,int(extra))

def notify_canteen(name,kind,extra):
    c=db();rows=c.execute("SELECT telegram_id FROM user_roles WHERE role='canteen'").fetchall();c.close()
    for r in rows:tg_send(r["telegram_id"],f"🍽 НОВАЯ ЗАЯВКА\n{name}\n{kind}{' — ДОП.' if extra else ''}")

async def canteen(update,ctx):
    if role(update.effective_user.id)!="canteen":return
    await canteen_period_report(update,ctx,"today")

async def canteen_period_report(update,ctx,kind):
    if role(update.effective_user.id)!="canteen":return
    d=now()
    if kind=="today":start=end=d.date()
    elif kind=="week":start=(d-timedelta(days=6)).date();end=d.date()
    elif kind=="month":start=d.replace(day=1).date();end=d.date()
    elif kind=="1":start=d.replace(day=1).date();end=d.replace(day=15).date()
    else:
        import calendar
        start=d.replace(day=16).date();end=d.replace(day=calendar.monthrange(d.year,d.month)[1]).date()
    c=db();rows=c.execute("SELECT name,meal_type,COUNT(*) n,SUM(extra) extra FROM meals WHERE meal_date BETWEEN ? AND ? GROUP BY name,meal_type ORDER BY name,meal_type",(start.isoformat(),end.isoformat())).fetchall();tot=c.execute("SELECT COUNT(*) n,SUM(extra) extra FROM meals WHERE meal_date BETWEEN ? AND ?",(start.isoformat(),end.isoformat())).fetchone();c.close()
    text=[f"🍽 ПИТАНИЕ\n{start:%d.%m.%Y} — {end:%d.%m.%Y}",f"Всего талонов: {tot['n'] or 0}",f"Дополнительных: {tot['extra'] or 0}",""]
    if not rows:text.append("Нет записей.")
    else:
        for r in rows:text.append(f"👤 {r['name']} — {r['meal_type']}: {r['n']} (доп.: {r['extra'] or 0})")
    await update.message.reply_text("\n".join(text))

async def serve_cb(update,ctx):
    q=update.callback_query;await q.answer()
    if role(q.from_user.id)!="canteen":
        return
    try:
        mid=int(q.data.split(":")[1])
    except (ValueError,IndexError):
        return await q.edit_message_text("❌ Неверная заявка.")
    c=db()
    c.execute("UPDATE meals SET served_at=?,status='served' WHERE id=? AND status='requested'",(now().isoformat(),mid))
    r=c.execute("SELECT * FROM meals WHERE id=?",(mid,)).fetchone()
    employee=c.execute("SELECT telegram_id FROM employees WHERE dahua_id=? AND active=1",(r["dahua_id"],)).fetchone() if r else None
    c.commit();c.close()
    if not r:
        return await q.edit_message_text("❌ Заявка не найдена.")
    if r["status"]=="served" and employee and employee["telegram_id"]:
        tg_send(employee["telegram_id"],f"🍽 {r['meal_type']} выдан.\nПосле еды нажмите «Вернулся с {r['meal_type'].lower()}» в разделе «🍽 Питание».")
    await q.edit_message_text(f"✅ Выдано: {r['name']} — {r['meal_type']}")

async def return_meal_cb(update,ctx):
    q=update.callback_query;await q.answer();tg=q.from_user.id
    c=db();e=c.execute("SELECT * FROM employees WHERE telegram_id=? AND active=1",(tg,)).fetchone()
    if not e:c.close();return
    kind=q.data.split(":")[1];date=now().date().isoformat()
    c.execute("UPDATE meals SET returned_at=?,status='returned' WHERE dahua_id=? AND meal_type=? AND meal_date=? AND status='served'",(now().isoformat(),e["dahua_id"],kind,date));c.commit();c.close()
    await q.edit_message_text(f"🔙 Возврат с {kind.lower()} отмечен.")

async def reports(update,ctx):
    if role(update.effective_user.id)!="owner":return
    date=now().date().isoformat();c=db()
    rows=c.execute("SELECT meal_type,COUNT(*) n,SUM(extra) extra FROM meals WHERE meal_date=? GROUP BY meal_type",(date,)).fetchall();c.close()
    text=[f"📊 ПИТАНИЕ {now():%d.%m.%Y}"]
    for r in rows:text.append(f"{r['meal_type']}: {r['n']} шт. (доп.: {r['extra'] or 0})")
    await update.message.reply_text("\n".join(text))

async def control(update,ctx):
    if role(update.effective_user.id) not in ("owner","control"):
        return
    date=now().date().isoformat()
    c=db();emps=c.execute("SELECT * FROM employees WHERE active=1 ORDER BY name").fetchall();c.close()
    at=late=early=0
    at_lines=[];meal_lines=[]
    for e in emps:
        rows=last_events(e["dahua_id"],date)
        if not rows:
            continue
        if rows[-1]["event_type"]=="Entry":
            at+=1; at_lines.append(f"🟢 {e['name']}")
        ins=[r for r in rows if r["event_type"]=="Entry"];outs=[r for r in rows if r["event_type"]=="Exit"]
        sh=shift_for(e["dahua_id"],date)
        if ins:
            first=datetime.fromisoformat(ins[0]["event_time"]);start=10 if sh in ("1-я","Нестандартная") else 13
            if first.hour*60+first.minute>start*60+5:
                late+=1
        if outs:
            last=datetime.fromisoformat(outs[-1]["event_time"]);limit=21 if sh=="1-я" else 22
            if last.hour<limit:
                early+=1
    c=db()
    l=c.execute("SELECT COUNT(*) n FROM meals WHERE meal_date=? AND meal_type='Обед' AND status='served'",(date,)).fetchone()["n"]
    onmeal_rows=c.execute("SELECT name FROM meals WHERE meal_date=? AND meal_type='Обед' AND status='served' ORDER BY served_at",(date,)).fetchall()
    c.close()
    meal_lines=[f"🍴 {r['name']}" for r in onmeal_rows]
    text=[f"📊 КОНТРОЛЬ — {now():%d.%m.%Y}","",f"👥 Сейчас на работе: {at}",f"⏰ Опоздали: {late}",f"⚠️ Ранее ушли: {early}","",f"🍽 Сейчас на обеде: {l}"]
    if at_lines:
        text += ["","👥 НА РАБОТЕ:"] + at_lines
    if meal_lines:
        text += ["","🍴 СЕЙЧАС НА ОБЕДЕ:"] + meal_lines
    await update.message.reply_text("\n".join(text))

def period_bounds(kind):
    d=now().date()
    if kind=="today":
        return d,d
    if kind=="week":
        start=d-timedelta(days=d.weekday())
        return start,d
    start=d.replace(day=1)
    return start,d

def fmt_period(start,end):
    if start==end:return start.strftime("%d.%m.%Y")
    return f"{start:%d.%m.%Y} — {end:%d.%m.%Y}"

async def employee_period_report(update,ctx,kind):
    uid=update.effective_user.id
    c=db();e=c.execute("SELECT * FROM employees WHERE telegram_id=? AND active=1",(uid,)).fetchone();c.close()
    if not e:return await update.message.reply_text("🔒 Нет активной привязки сотрудника.")
    start,end=period_bounds(kind)
    c=db();rows=c.execute("SELECT * FROM attendance WHERE user_id=? AND date(event_time) BETWEEN ? AND ? ORDER BY event_time",(e["dahua_id"],start.isoformat(),end.isoformat())).fetchall();c.close()
    days={}
    for r in rows:days.setdefault(r["event_time"][:10],[]).append(r)
    present=sum(1 for rs in days.values() if any(x["event_type"]=="Entry" for x in rs))
    late=early=0;lines=[]
    for day,rs in sorted(days.items()):
        ins=[x for x in rs if x["event_type"]=="Entry"];outs=[x for x in rs if x["event_type"]=="Exit"];sh=shift_for(e["dahua_id"],day)
        if ins:
            first=datetime.fromisoformat(ins[0]["event_time"]);limit=10 if sh in ("1-я","Нестандартная") else 13
            if first.hour*60+first.minute>limit*60+5:late+=1
        if outs:
            last=datetime.fromisoformat(outs[-1]["event_time"]);limit=21 if sh=="1-я" else 22
            if last.hour<limit:early+=1
        first_t=datetime.fromisoformat(ins[0]["event_time"]).strftime("%H:%M") if ins else "—"
        last_t=datetime.fromisoformat(outs[-1]["event_time"]).strftime("%H:%M") if outs else "—"
        lines.append(f"{day[8:10]}.{day[5:7]}  {first_t} → {last_t}  ({sh})")
    text=[f"📋 ОТЧЁТ — {e['name']}",f"📅 {fmt_period(start,end)}","",f"👥 Дни с приходом: {present}",f"⏰ Опоздания: {late}",f"⚠️ Ранний уход: {early}","",*lines[-31:]]
    await update.message.reply_text("\n".join(text))

async def employee_help(update,ctx):
    if role(update.effective_user.id)!="employee":return
    await update.message.reply_text("ℹ️ Staff Bot\n\n👤 Мои записи — сегодняшние проходы.\n📋 Мой отчёт — сводка за текущий месяц.\n📅 Сегодня / 📅 Неделя / 🗓 Месяц — отчёты по приходу и уходу.\n🍽 Питание — обед/ужин и дополнительные талоны.\n📱 QR столовой — ваш QR для питания.\nПитание подключается автоматически после принятия сотрудника.")

async def control_period(update,ctx,kind):
    if role(update.effective_user.id) not in ("owner","control"):return
    start,end=period_bounds(kind)
    c=db();emps=c.execute("SELECT * FROM employees WHERE active=1 ORDER BY name").fetchall();c.close()
    present_days=late=early=0
    for e in emps:
        c=db();rows=c.execute("SELECT * FROM attendance WHERE user_id=? AND date(event_time) BETWEEN ? AND ? ORDER BY event_time",(e["dahua_id"],start.isoformat(),end.isoformat())).fetchall();c.close()
        byday={}
        for r in rows:byday.setdefault(r["event_time"][:10],[]).append(r)
        for day,rs in byday.items():
            if any(x["event_type"]=="Entry" for x in rs):present_days+=1
            ins=[x for x in rs if x["event_type"]=="Entry"];outs=[x for x in rs if x["event_type"]=="Exit"];sh=shift_for(e["dahua_id"],day)
            if ins:
                first=datetime.fromisoformat(ins[0]["event_time"]);limit=10 if sh in ("1-я","Нестандартная") else 13
                if first.hour*60+first.minute>limit*60+5:late+=1
            if outs:
                last=datetime.fromisoformat(outs[-1]["event_time"]);limit=21 if sh=="1-я" else 22
                if last.hour<limit:early+=1
    await update.message.reply_text(f"📊 КОНТРОЛЬ — {fmt_period(start,end)}\n\n👥 Активных сотрудников: {len(emps)}\n📥 Дни с приходом: {present_days}\n⏰ Опоздания: {late}\n⚠️ Ранний уход: {early}")

async def current_on_work(update,ctx):
    if role(update.effective_user.id) not in ("owner","control"):return
    date=now().date().isoformat();c=db();emps=c.execute("SELECT * FROM employees WHERE active=1 ORDER BY name").fetchall();c.close();lines=[]
    for e in emps:
        rows=last_events(e["dahua_id"],date)
        if rows and rows[-1]["event_type"]=="Entry":lines.append(f"🟢 {e['name']}")
    await update.message.reply_text("👥 СЕЙЧАС НА РАБОТЕ\n\n"+("\n".join(lines) if lines else "Сейчас сотрудников нет."))

async def control_exceptions(update,ctx,kind):
    if role(update.effective_user.id) not in ("owner","control"):return
    date=now().date().isoformat();c=db();emps=c.execute("SELECT * FROM employees WHERE active=1 ORDER BY name").fetchall();c.close();lines=[]
    for e in emps:
        rows=last_events(e["dahua_id"],date);ins=[x for x in rows if x["event_type"]=="Entry"];outs=[x for x in rows if x["event_type"]=="Exit"];sh=shift_for(e["dahua_id"],date)
        if kind=="late" and ins:
            t=datetime.fromisoformat(ins[0]["event_time"]);limit=10 if sh in ("1-я","Нестандартная") else 13
            if t.hour*60+t.minute>limit*60+5:lines.append(f"⏰ {e['name']} — {t:%H:%M}")
        if kind=="early" and outs:
            t=datetime.fromisoformat(outs[-1]["event_time"]);limit=21 if sh=="1-я" else 22
            if t.hour<limit:lines.append(f"⚠️ {e['name']} — {t:%H:%M}")
    title="🔴 ОПОЗДАНИЯ" if kind=="late" else "⚠️ РАННИЙ УХОД"
    await update.message.reply_text(title+"\n\n"+("\n".join(lines) if lines else "Нет записей."))

async def qr(update,ctx):
    if role(update.effective_user.id) not in ("owner","employee"):return
    me=await ctx.bot.get_me();url=f"https://t.me/{me.username}?start=meal"
    img=qrcode.make(url);bio=BytesIO();bio.name="FUNLANDIA_QR_STOLOVAYA.png";img.save(bio,"PNG");bio.seek(0)
    await update.message.reply_photo(photo=bio,caption="📱 QR-код столовой\n\nСотрудник сканирует код → открывается Staff Bot → система проверяет его Telegram-доступ.")

async def text_handler(update,ctx):
    t=(update.message.text or "").strip();r=role(update.effective_user.id)
    if ctx.user_data.get("add_staff_step"):
        if await owner_add_input(update,ctx):return
    if t=="🔐 Получить доступ":return await access_request(update,ctx)
    if t=="👥 Сотрудники":return await employees(update,ctx)
    if t=="➕ Добавить сотрудника":return await owner_add_start(update,ctx)
    if t=="📊 Контроль" and r=="owner":return await control(update,ctx)
    if t=="👥 Сейчас на работе":return await current_on_work(update,ctx)
    if t in ("🔴 Опоздали","⚠️ Ранее ушли"):
        return await control_exceptions(update,ctx,"late" if t.startswith("🔴") else "early")
    if t=="🍽 Сейчас на обеде":
        return await control(update,ctx)
    if t=="📊 Отчёты":return await report_menu(update,ctx)
    if t=="🍽 Питание":return await meal_menu(update,ctx)
    if t=="📱 QR столовой":return await qr(update,ctx)
    if t=="📱 Проверить QR":return await canteen(update,ctx)
    if t=="🍽 Сегодня питание":return await canteen_period_report(update,ctx,"today")
    if t=="📅 Неделя":
        if r=="canteen":return await canteen_period_report(update,ctx,"week")
        if r=="employee":return await employee_period_report(update,ctx,"week")
    if t=="🗓 Месяц":
        if r=="canteen":return await canteen_period_report(update,ctx,"month")
        if r=="employee":return await employee_period_report(update,ctx,"month")
    if t=="📅 1–15":return await canteen_period_report(update,ctx,"1")
    if t=="📅 16–конец месяца":return await canteen_period_report(update,ctx,"2")
    if t=="📋 Мой отчёт":return await employee_period_report(update,ctx,"month")
    if t=="ℹ️ Помощь":return await employee_help(update,ctx)
    if t=="👤 Мои записи":
        uid=update.effective_user.id;c=db();e=c.execute("SELECT * FROM employees WHERE telegram_id=? AND active=1",(uid,)).fetchone();c.close()
        if not e:return await update.message.reply_text("🔒 Нет активной привязки сотрудника.")
        rows=last_events(e["dahua_id"],now().date().isoformat());out=[f"👤 {e['name']}"]
        out += [f"{'🟢' if x['event_type']=='Entry' else '🔴'} {datetime.fromisoformat(x['event_time']):%H:%M} — {'Вход' if x['event_type']=='Entry' else 'Выход'}" for x in rows]
        return await update.message.reply_text("\n".join(out))
    await update.message.reply_text("Используйте кнопки меню.",reply_markup=keyboard(r))


async def registration_start(update,ctx):
    await update.message.reply_text("ℹ️ Отдельная регистрация питания больше не нужна. Питание подключается автоматически после принятия сотрудника.")

async def error(update,ctx):log.exception("Telegram error: %s",ctx.error)

def month_range(year=None, month=None):
    d=now()
    year=year or d.year
    month=month or d.month
    start=datetime(year,month,1,tzinfo=TZ)
    if month==12:
        end=datetime(year+1,1,1,tzinfo=TZ)
    else:
        end=datetime(year,month+1,1,tzinfo=TZ)
    return start,end

def sync_month(year=None, month=None):
    start,end=month_range(year,month)
    # Do not request future records when syncing the current month.
    if end>now():
        end=now()
    records=get_records(start,end)
    new=import_records(records)
    return len(records),len(new),start,end

async def sync_command(update,ctx):
    uid=update.effective_user.id
    if role(uid) not in ("owner","control"):
        return await update.message.reply_text("🔒 Доступ запрещён.")
    await update.message.reply_text("🔄 Начинаю загрузку записей Dahua за текущий месяц...\nЭто может занять некоторое время.")
    try:
        total,new,start,end=sync_month()
        await update.message.reply_text(
            f"✅ Синхронизация завершена.\n\n"
            f"📅 Период: {start:%d.%m.%Y} — {end:%d.%m.%Y %H:%M}\n"
            f"📥 Получено из Dahua: {total}\n"
            f"🆕 Добавлено новых: {new}\n"
            f"💾 Дубликаты автоматически пропущены."
        )
    except Exception as e:
        log.exception("Manual month sync failed")
        await update.message.reply_text(f"❌ Ошибка синхронизации: {e}")

async def check_staff_face_registrations():
    c=db();matches=pending_face_matches(c)
    for req,uid,found_name in matches:
        if uid is None:
            tg_send(req["created_by"],f"⚠️ Не удалось однозначно определить Face ID для {staff_name(req)}: в Dahua найдено несколько совпадений ФИО. Нужна проверка владельца.")
            continue
        c.execute("UPDATE staff_requests SET dahua_id=?,status='face_ready' WHERE id=?",(uid,req["id"]))
        name=staff_name(req)
        if str(req["created_by"])==str(ADMIN_ID):
            c.execute("INSERT OR REPLACE INTO employees(dahua_id,name,active,telegram_id,role,created_at) VALUES(?,?,?,?,?,?)",(uid,name,1,None,"employee",now().isoformat()))
            c.execute("UPDATE staff_requests SET status='approved' WHERE id=?",(req["id"],))
            tg_send(req["created_by"],f"✅ Сотрудник зарегистрирован автоматически.\n\n👤 {name}\n🆔 {req['staff_id']}\n🔐 Dahua Face ID: {uid}\n🍽 Питание подключено.")
        else:
            mk={"inline_keyboard":[[{"text":"✅ ПРИНЯТЬ","callback_data":f"staff:ok:{req['id']}"},{"text":"❌ ОТКЛОНИТЬ","callback_data":f"staff:no:{req['id']}"}]]}
            tg_send(ADMIN_ID,f"🆕 СОТРУДНИК ГОТОВ К ОКОНЧАТЕЛЬНОМУ ПОДТВЕРЖДЕНИЮ\n\n👤 {name}\n📞 {req['phone']}\n🆔 {req['staff_id']}\n🔐 Dahua Face ID: {uid}\n📸 Face ID зарегистрирован: ✅\n\nКонтроль полностью завершил регистрацию. Принять сотрудника на работу?",mk)
    c.commit();c.close()

async def poller(app):
    last_full_sync_date=None
    try:
        total,new,start,end=sync_month();last_full_sync_date=now().date();log.info("Initial month sync: %s records, %s new",total,new)
    except Exception as e:log.exception("Initial month sync failed: %s",e)
    while True:
        try:
            current_date=now().date()
            if last_full_sync_date!=current_date:
                sync_month();last_full_sync_date=current_date
            await check_staff_face_registrations()
            end=now();start=end-timedelta(minutes=10);new=import_records(get_records(start,end))
            if new:log.info("Imported %s new Dahua records",len(new))
        except Exception as e:log.warning("Dahua poll failed: %s",e)
        await asyncio.sleep(POLL)

async def post_init(app):
    asyncio.create_task(poller(app))

def main():
    if not BOT_TOKEN:raise RuntimeError("BOT_TOKEN is not set")
    init_db()
    log.info("Starting Funlandia Staff Bot; Dahua=%s; poll=%ss", DAHUA_URL, POLL)
    app=Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("access",access_request))
    app.add_handler(CommandHandler("sync",sync_command))
    app.add_handler(CallbackQueryHandler(access_cb,pattern=r"^access:"))
    app.add_handler(CallbackQueryHandler(report_cb,pattern=r"^report:"))
    app.add_handler(CallbackQueryHandler(reg_cb,pattern=r"^reg:"))
    app.add_handler(CallbackQueryHandler(staff_cb,pattern=r"^staff:"))
    app.add_handler(CallbackQueryHandler(emp_cb,pattern=r"^emp:"))
    app.add_handler(CallbackQueryHandler(meal_cb,pattern=r"^meal:"))
    app.add_handler(CallbackQueryHandler(return_meal_cb,pattern=r"^mealreturn:"))
    app.add_handler(CallbackQueryHandler(serve_cb,pattern=r"^serve:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_handler))
    app.add_error_handler(error)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__":main()
