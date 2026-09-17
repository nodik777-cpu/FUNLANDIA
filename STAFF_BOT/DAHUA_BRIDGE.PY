
import os,re,json,sqlite3,hashlib,logging,asyncio,base64
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
    for col, typ in (("internal_id","TEXT"),("phone","TEXT")):
        try: c.execute(f"ALTER TABLE employees ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError: pass
    for col, typ in (("phone","TEXT"),("internal_id","TEXT")):
        try: c.execute(f"ALTER TABLE registration_requests ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError: pass
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


def next_internal_id():
    c=db()
    rows=c.execute("SELECT internal_id FROM employees WHERE internal_id IS NOT NULL").fetchall()
    c.close()
    nums=[]
    for r in rows:
        m=re.fullmatch(r"MP-(\d+)",str(r["internal_id"] or ""))
        if m: nums.append(int(m.group(1)))
    return f"MP-{(max(nums) if nums else 0)+1:03d}"

def next_dahua_user_id():
    c=db(); vals=[]
    for r in c.execute("SELECT dahua_id FROM employees").fetchall():
        try: vals.append(int(str(r["dahua_id"])))
        except: pass
    for r in c.execute("SELECT user_id FROM attendance").fetchall():
        try: vals.append(int(str(r["user_id"])))
        except: pass
    c.close()
    return str(max(vals+[0])+1)

def save_registration_photo(user_id,name,photo_bytes):
    if len(photo_bytes)>200*1024: raise ValueError("Фото больше 200 KB.")
    payload={"UserID":str(user_id),"Info":{"UserName":str(name)[:32],
        "PhotoData":[base64.b64encode(photo_bytes).decode("ascii")]}}
    r=requests.post(DAHUA_URL+"/cgi-bin/FaceInfoManager.cgi",
        params={"action":"add"},json=payload,
        auth=HTTPDigestAuth(DAHUA_USER,DAHUA_PASSWORD),
        verify=False,timeout=25)
    r.raise_for_status()
    if r.text.strip().upper()!="OK":
        raise RuntimeError(f"Dahua ответил: {r.text.strip()[:300]}")
    return True

def try_dahua_capture(user_id,name):
    endpoint=os.getenv("DAHUA_FACE_CAPTURE_URL","").strip()
    if not endpoint:
        return False
    try:
        r=requests.post(endpoint,json={"UserID":str(user_id),"UserName":str(name)},
            auth=HTTPDigestAuth(DAHUA_USER,DAHUA_PASSWORD),
            verify=False,timeout=20)
        return r.ok and r.text.strip().upper() in ("OK","SUCCESS","TRUE")
    except Exception:
        return False

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

def get_records(start,end):
    p={"action":"find","name":"AccessControlCardRec","StartTime":str(int(start.timestamp())),"EndTime":str(int(end.timestamp())),"count":"1024"}
    r=dahua_get("/cgi-bin/recordFinder.cgi",p)
    rows={}
    for line in r.text.replace("\r","").splitlines():
        m=re.match(r"records\[(\d+)\]\.([^=]+)=(.*)$",line)
        if m: rows.setdefault(m.group(1),{})[m.group(2)]=m.group(3)
    return list(rows.values())

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
        return ReplyKeyboardMarkup([["👥 Управление сотрудниками","➕ Добавить сотрудника"],
                                     ["📊 Контроль","🍽 Питание"],
                                     ["📊 Отчёты","📱 QR столовой"]],resize_keyboard=True)
    if r=="control":
        return ReplyKeyboardMarkup([["👥 Сейчас на работе"],["🔴 Опоздали","⚠️ Ранее ушли"],
                                     ["🍽 Сейчас на обеде"],["➕ Добавить сотрудника"]],resize_keyboard=True)
    if r=="canteen":
        return ReplyKeyboardMarkup([["🍽 Сегодня питание","📅 Неделя"],
                                     ["🗓 Месяц","📅 1–15"],["📅 16–конец месяца","📱 Проверить QR"]],resize_keyboard=True)
    if r=="employee":
        return ReplyKeyboardMarkup([["👤 Мои записи","📋 Мой отчёт"],
                                     ["🍽 Питание","📱 QR столовой"],["ℹ️ Помощь"]],resize_keyboard=True)
    return ReplyKeyboardMarkup([["📝 Регистрация"],["🔐 Запросить доступ"]],resize_keyboard=True)

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

async def registration_start(update,ctx):
    if role(update.effective_user.id) not in ("none","employee"): return
    ctx.user_data.clear(); ctx.user_data["reg_fio"]=True
    await update.message.reply_text("📝 Регистрация сотрудника\n\nШаг 1 из 3\nВведите ФИО сотрудника:")

async def registration_input(update,ctx):
    if role(update.effective_user.id) not in ("none","employee"): return
    text=(update.message.text or "").strip()
    if ctx.user_data.get("reg_fio"):
        if len(text)<3: return await update.message.reply_text("❌ Введите корректное ФИО.")
        ctx.user_data["fio"]=text; ctx.user_data.pop("reg_fio",None); ctx.user_data["reg_phone"]=True
        return await update.message.reply_text("Шаг 2 из 3\nВведите номер телефона:")
    if ctx.user_data.get("reg_phone"):
        phone=re.sub(r"[^0-9+() -]","",text)
        if len(re.sub(r"\D","",phone))<9: return await update.message.reply_text("❌ Неверный номер телефона.")
        ctx.user_data["phone"]=phone; ctx.user_data.pop("reg_phone",None)
        return await update.message.reply_text(
            f"Шаг 3 из 3\n\n👤 ФИО: {ctx.user_data['fio']}\n📞 Телефон: {phone}\n\nЗарегистрируйте лицо:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📷 Зарегистрировать Face ID",callback_data="face:start")],
                [InlineKeyboardButton("📱 Отправить фото через Telegram",callback_data="face:telegram")]
            ]))

async def face_cb(update,ctx):
    q=update.callback_query; await q.answer()
    if role(q.from_user.id) not in ("none","employee"): return
    if not ctx.user_data.get("fio") or not ctx.user_data.get("phone"):
        return await q.edit_message_text("❌ Сначала заполните ФИО и телефон.")
    if q.data=="face:start":
        ok=try_dahua_capture(next_dahua_user_id(),ctx.user_data["fio"])
        if ok:
            return await q.edit_message_text("📷 Команда регистрации отправлена на Dahua. Встаньте перед терминалом и дождитесь захвата лица.")
        return await q.edit_message_text("📷 Прямой запуск камеры для этой прошивки пока не подтверждён.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📱 Отправить фото через Telegram",callback_data="face:telegram")]]))
    ctx.user_data["await_face_photo"]=True
    await q.edit_message_text("📱 Отправьте ОДНО фото лица. Лицо по центру, один человек, хорошее освещение.")

async def face_photo_handler(update,ctx):
    if not ctx.user_data.get("await_face_photo"): return
    uid=update.effective_user.id
    if role(uid) not in ("none","employee"): return
    try:
        fio=ctx.user_data["fio"]; phone=ctx.user_data["phone"]
        f=await update.message.photo[-1].get_file()
        bio=BytesIO(); await f.download_to_memory(out=bio)
        photo=bio.getvalue()
        internal_id=next_internal_id(); dahua_id=next_dahua_user_id()
        save_registration_photo(dahua_id,fio,photo)
        c=db()
        c.execute("INSERT OR REPLACE INTO employees(dahua_id,name,active,telegram_id,role,created_at,internal_id,phone) VALUES(?,?,?,?,?,?,?,?)",
                  (dahua_id,fio,1,uid,"employee",now().isoformat(),internal_id,phone))
        c.execute("INSERT OR REPLACE INTO registration_requests(telegram_id,dahua_id,name,username,created_at,status,phone,internal_id) VALUES(?,?,?,?,?,?,?,?)",
                  (uid,dahua_id,fio,update.effective_user.username,now().isoformat(),"pending",phone,internal_id))
        c.commit(); c.close()
        if ADMIN_ID:
            tg_send(ADMIN_ID,f"🆕 НОВЫЙ СОТРУДНИК — подтверждение\n\n🆔 {internal_id}\n👤 {fio}\n📞 {phone}\n🔢 Dahua ID: {dahua_id}",
                    {"inline_keyboard":[[{"text":"✅ Подтвердить","callback_data":f"reg:ok:{uid}"},
                                         {"text":"❌ Отклонить","callback_data":f"reg:no:{uid}"}]]})
        ctx.user_data.clear()
        await update.message.reply_text(f"✅ Face ID зарегистрирован в Dahua.\n\n🆔 {internal_id}\n👤 {fio}\n📞 {phone}\n\nЗаявка отправлена владельцу.")
    except Exception as e:
        log.exception("Face registration failed")
        await update.message.reply_text(f"❌ Не удалось зарегистрировать лицо в Dahua.\nТехнический ответ: {e}")

async def reg_cb(update,ctx):
    q=update.callback_query;await q.answer()
    if role(q.from_user.id)!="owner":return await q.edit_message_text("🔒 Только владелец.")
    _,act,tid=q.data.split(":");tid=int(tid);c=db()
    req=c.execute("SELECT * FROM registration_requests WHERE telegram_id=?",(tid,)).fetchone()
    if not req:c.close();return await q.edit_message_text("Заявка не найдена.")
    if act=="no":
        c.execute("UPDATE registration_requests SET status='denied' WHERE telegram_id=?",(tid,));c.commit();c.close();tg_send(tid,"❌ Регистрация питания отклонена.");return await q.edit_message_text("❌ Регистрация отклонена.")
    c.execute("UPDATE employees SET active=1,telegram_id=?,role='employee' WHERE dahua_id=?",(tid,req["dahua_id"]))
    if c.rowcount == 0:
        c.execute("INSERT OR REPLACE INTO employees(dahua_id,name,active,telegram_id,role,created_at,phone,internal_id) VALUES(?,?,?,?,?,?,?,?)",
                  (req["dahua_id"],req["name"],1,tid,"employee",now().isoformat(),req["phone"],req["internal_id"]))
    else:
        c.execute("UPDATE employees SET phone=?,internal_id=? WHERE dahua_id=?",(req["phone"],req["internal_id"],req["dahua_id"]))
    c.execute("UPDATE registration_requests SET status='approved' WHERE telegram_id=?",(tid,));c.commit();c.close()
    tg_send(tid,f"✅ Вы зарегистрированы для питания.\n\n👤 {req['name']}\n🍽 Теперь можно пользоваться QR-кодом столовой.")
    await q.edit_message_text(f"✅ Сотрудник подтверждён:\n{req['name']}\nFace ID: {req['dahua_id']}")

async def employees(update,ctx):
    if role(update.effective_user.id)!="owner":return
    c=db();rows=c.execute("SELECT * FROM employees ORDER BY active DESC,name").fetchall();c.close()
    if not rows:return await update.message.reply_text("Сотрудников пока нет.")
    for e in rows[:50]:
        st="🟢" if e["active"] else "🔴"
        mk={"inline_keyboard":[[{"text":"🚫 Отключить" if e["active"] else "♻️ Активировать","callback_data":f"emp:{'off' if e['active'] else 'on'}:{e['dahua_id']}"}]]}
        await update.message.reply_text(f"{st} {e['name']}\nFace ID: {e['dahua_id']}\nTelegram: {e['telegram_id'] or '—'}",reply_markup=mk)

async def emp_cb(update,ctx):
    q=update.callback_query;await q.answer()
    if role(q.from_user.id)!="owner":return await q.edit_message_text("🔒 Только владелец.")
    _,act,uid=q.data.split(":");c=db()
    if act=="off":c.execute("UPDATE employees SET active=0,telegram_id=NULL WHERE dahua_id=?",(uid,));msg="🚫 Питание отключено."
    else:c.execute("UPDATE employees SET active=1 WHERE dahua_id=?",(uid,));msg="♻️ Питание снова разрешено."
    c.commit();c.close();await q.edit_message_text(msg)


async def owner_add_start(update,ctx):
    if role(update.effective_user.id)!="owner": return
    ctx.user_data.clear(); ctx.user_data["owner_fio"]=True
    await update.message.reply_text("➕ Добавление сотрудника\n\nВведите ФИО:")

async def owner_add_input(update,ctx):
    if role(update.effective_user.id)!="owner": return False
    text=(update.message.text or "").strip()
    if ctx.user_data.get("owner_fio"):
        ctx.user_data["owner_name"]=text; ctx.user_data.pop("owner_fio",None); ctx.user_data["owner_phone"]=True
        await update.message.reply_text("Введите номер телефона:"); return True
    if ctx.user_data.get("owner_phone"):
        phone=re.sub(r"[^0-9+() -]","",text)
        if len(re.sub(r"\D","",phone))<9: await update.message.reply_text("❌ Неверный номер."); return True
        fio=ctx.user_data["owner_name"]; internal_id=next_internal_id(); dahua_id=next_dahua_user_id()
        c=db(); c.execute("INSERT OR REPLACE INTO employees(dahua_id,name,active,telegram_id,role,created_at,internal_id,phone) VALUES(?,?,?,?,?,?,?,?)",
                           (dahua_id,fio,1,None,"employee",now().isoformat(),internal_id,phone)); c.commit(); c.close()
        ctx.user_data.clear()
        await update.message.reply_text(f"✅ Сотрудник создан.\n\n🆔 {internal_id}\n👤 {fio}\n📞 {phone}\n🔢 Dahua ID: {dahua_id}")
        return True
    return False

async def report_menu(update,ctx):
    if role(update.effective_user.id)!="owner": return
    await update.message.reply_text("📊 Отчёты за питание:",reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("1–15 число",callback_data="report:1"),InlineKeyboardButton("16–конец месяца",callback_data="report:2")]
    ]))

async def report_cb(update,ctx):
    q=update.callback_query;await q.answer()
    if role(q.from_user.id)!="owner":return
    part=int(q.data.split(":")[1]);d=now();start_day=1 if part==1 else 16
    end_day=15 if part==1 else 31
    start=f"{d.year:04d}-{d.month:02d}-{start_day:02d}"
    if part==1:end=f"{d.year:04d}-{d.month:02d}-15"
    else:
        import calendar
        end=f"{d.year:04d}-{d.month:02d}-{calendar.monthrange(d.year,d.month)[1]:02d}"
    c=db();rows=c.execute("SELECT meal_type,COUNT(*) n,SUM(extra) extra FROM meals WHERE meal_date BETWEEN ? AND ? GROUP BY meal_type",(start,end)).fetchall()
    total=c.execute("SELECT COUNT(*) n,SUM(extra) extra FROM meals WHERE meal_date BETWEEN ? AND ?",(start,end)).fetchone()
    c.close()
    text=[f"📊 ПИТАНИЕ: {start_day}–{end.split('-')[-1]}.{d.month:02d}.{d.year}",f"Всего: {total['n'] or 0}",f"Дополнительных: {total['extra'] or 0}",f"Сумма удержания: {(total['extra'] or 0)*EXTRA_MEAL_COST:,} сум"]
    for r in rows:text.append(f"{r['meal_type']}: {r['n']} (доп.: {r['extra'] or 0})")
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
    date=now().date().isoformat();c=db();rows=c.execute("SELECT * FROM meals WHERE meal_date=? ORDER BY status='served',requested_at",(date,)).fetchall();c.close()
    if not rows:return await update.message.reply_text("Сегодня заявок на питание нет.")
    for r in rows:
        if r["status"]=="returned":continue
        mk={"inline_keyboard":[[{"text":"🍽 Выдано","callback_data":f"serve:{r['id']}"}]]} if r["status"]=="requested" else None
        await update.message.reply_text(f"{'🥗' if r['meal_type']=='Обед' else '🍽'} {r['name']}\n{r['meal_type']}{' ⚠️ ДОП.' if r['extra'] else ''}\nСтатус: {r['status']}",reply_markup=mk)

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
    l=c.execute("SELECT COUNT(*) n FROM meals WHERE meal_date=? AND meal_type='Обед' AND status IN ('requested','served')",(date,)).fetchone()["n"]
    d=c.execute("SELECT COUNT(*) n FROM meals WHERE meal_date=? AND meal_type='Ужин' AND status IN ('requested','served')",(date,)).fetchone()["n"]
    onmeal_rows=c.execute("SELECT name,meal_type FROM meals WHERE meal_date=? AND status='served' ORDER BY served_at",(date,)).fetchall()
    c.close()
    meal_lines=[f"🍴 {r['name']} — {r['meal_type']}" for r in onmeal_rows]
    text=[f"📊 КОНТРОЛЬ — {now():%d.%m.%Y}","",f"👥 Сейчас на работе: {at}",f"⏰ Опоздали: {late}",f"⚠️ Ранний уход: {early}","",f"🥗 Обед: {l}",f"🍽 Ужин: {d}",f"🍴 Сейчас на питании: {len(meal_lines)}"]
    if at_lines:
        text += ["","👥 НА РАБОТЕ:"] + at_lines
    if meal_lines:
        text += ["","🍴 СЕЙЧАС НА ПИТАНИИ:"] + meal_lines
    await update.message.reply_text("\n".join(text))

async def qr(update,ctx):
    if role(update.effective_user.id)!="owner":return
    me=await ctx.bot.get_me();url=f"https://t.me/{me.username}?start=meal"
    img=qrcode.make(url);bio=BytesIO();bio.name="FUNLANDIA_QR_STOLOVAYA.png";img.save(bio,"PNG");bio.seek(0)
    await update.message.reply_photo(photo=bio,caption="📱 QR-код столовой\n\nСотрудник сканирует код → открывается Staff Bot → система проверяет его Telegram-доступ.")

async def text_handler(update,ctx):
    t=(update.message.text or "").strip(); r=role(update.effective_user.id)
    if r=="owner" and (ctx.user_data.get("owner_fio") or ctx.user_data.get("owner_phone")):
        if await owner_add_input(update,ctx): return
    if r in ("none","employee") and (ctx.user_data.get("reg_fio") or ctx.user_data.get("reg_phone")):
        return await registration_input(update,ctx)
    if t=="🔐 Запросить доступ": return await access_request(update,ctx)
    if t in ("📝 Регистрация","📝 Регистрация для питания"): return await registration_start(update,ctx)
    if t in ("👥 Управление сотрудниками","👥 Сотрудники"): return await employees(update,ctx)
    if t=="➕ Добавить сотрудника": return await owner_add_start(update,ctx)
    if t in ("📊 Контроль","👥 Сейчас на работе","🔴 Опоздали","⚠️ Ранее ушли","🍽 Сейчас на обеде"):
        return await control(update,ctx)
    if t=="🍽 Питание": return await meal_menu(update,ctx)
    if t in ("🍽 Сегодня питание","📊 Сегодня питание"): return await reports(update,ctx)
    if t=="📊 Отчёты": return await report_menu(update,ctx)
    if t in ("📱 QR столовой","📱 Проверить QR"): return await qr(update,ctx)
    if t=="👤 Мои записи":
        c=db(); e=c.execute("SELECT * FROM employees WHERE telegram_id=? AND active=1",(update.effective_user.id,)).fetchone(); c.close()
        if not e: return await update.message.reply_text("Нет привязанного сотрудника.")
        rows=last_events(e["dahua_id"],now().date().isoformat())
        out=[f"👤 {e['name']}",f"🆔 {e['internal_id'] or '—'}",f"📞 {e['phone'] or '—'}"]
        out += [f"{'🟢' if x['event_type']=='Entry' else '🔴'} {datetime.fromisoformat(x['event_time']):%H:%M}" for x in rows]
        return await update.message.reply_text("\n".join(out))
    if t=="📋 Мой отчёт":
        c=db(); e=c.execute("SELECT * FROM employees WHERE telegram_id=? AND active=1",(update.effective_user.id,)).fetchone()
        if not e: c.close(); return await update.message.reply_text("Нет привязанного сотрудника.")
        rows=c.execute("SELECT meal_type,COUNT(*) n,SUM(extra) extra FROM meals WHERE dahua_id=? AND meal_date=? GROUP BY meal_type",(e["dahua_id"],now().date().isoformat())).fetchall(); c.close()
        return await update.message.reply_text("\n".join([f"📋 Мой отчёт — {now():%d.%m.%Y}"]+[f"{x['meal_type']}: {x['n']} (доп.: {x['extra'] or 0})" for x in rows]))
    await update.message.reply_text("Используйте кнопки меню.",reply_markup=keyboard(r))

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

async def poller(app):
    # При каждом запуске бот сначала загружает весь текущий календарный месяц.
    try:
        total,new,start,end=sync_month()
        log.info("Initial month sync: period=%s..%s received=%s new=%s",
                 start.isoformat(),end.isoformat(),total,new)
    except Exception as e:
        log.exception("Initial month sync failed: %s",e)

    # Затем регулярно проверяем небольшой перекрывающийся интервал,
    # чтобы новые проходы попадали в базу практически сразу.
    while True:
        try:
            end=now()
            start=end-timedelta(minutes=5)
            new=import_records(get_records(start,end))
            if new:log.info("Imported %s new Dahua records",len(new))
        except Exception as e:
            log.warning("Dahua poll failed: %s",e)
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
    app.add_handler(CallbackQueryHandler(emp_cb,pattern=r"^emp:"))
    app.add_handler(CallbackQueryHandler(meal_cb,pattern=r"^meal:"))
    app.add_handler(CallbackQueryHandler(return_meal_cb,pattern=r"^mealreturn:"))
    app.add_handler(CallbackQueryHandler(serve_cb,pattern=r"^serve:"))
    app.add_handler(CallbackQueryHandler(face_cb,pattern=r"^face:"))
    app.add_handler(MessageHandler(filters.PHOTO,face_photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_handler))
    app.add_error_handler(error)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__":main()
