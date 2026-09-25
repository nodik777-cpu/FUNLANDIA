import os, asyncio, base64
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from requests.auth import HTTPDigestAuth
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

BASE="/opt/funlandia"
load_dotenv(f"{BASE}/.env")
load_dotenv(f"{BASE}/.env.postgres")

TOKEN=os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID=int(os.getenv("OWNER_TELEGRAM_ID","1697712497"))
DAHUA_HOST=os.getenv("DAHUA_HOST","192.168.1.202")
DAHUA_USER=os.getenv("DAHUA_USER","admin")
DAHUA_PASSWORD=os.getenv("DAHUA_PASSWORD","")
TZ=ZoneInfo("Asia/Tashkent")
EXTRA_PRICE=Decimal("25000")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не найден в /opt/funlandia/.env")

DB={
 "dbname":os.getenv("POSTGRES_DB","funlandia"),
 "user":os.getenv("POSTGRES_USER","funlandia"),
 "password":os.getenv("POSTGRES_PASSWORD",""),
 "host":"127.0.0.1","port":5432
}

bot=Bot(TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp=Dispatcher(storage=MemoryStorage())

class Reg(StatesGroup):
    surname=State(); first=State(); patronymic=State(); phone=State()
    age=State(); gender=State(); photo=State()

class Fire(StatesGroup):
    name=State()

class CafeIssue(StatesGroup):
    employee=State(); meal=State()

def conn():
    return psycopg2.connect(**DB)

def fetch(sql,params=(),one=False):
    with conn() as c, c.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql,params)
        return cur.fetchone() if one else cur.fetchall()

def run(sql,params=()):
    with conn() as c, c.cursor() as cur:
        cur.execute(sql,params)
        return cur.rowcount

def kb(rows):
    b=ReplyKeyboardBuilder()
    for row in rows:
        for text in row:
            b.button(text=text)
        b.adjust(len(row))
    return b.as_markup(resize_keyboard=True)

OWNER_KB=kb([["📊 Контроль","👥 Сотрудники"],["🍽 Столовая","📑 Отчёты"],["⚙️ Настройки","📱 QR столовой"]])
MANAGER_KB=kb([["👥 Сейчас на работе"],["🍽 Сейчас на обеде"],["⏰ Опоздавшие","🚪 Ранний уход"],["➕ Зарегистрировать сотрудника"]])
CAFE_KB=kb([["🍲 Сегодня"],["📅 1–15","📅 16–конец месяца"]])
EMP_KB=kb([["📊 Моя посещаемость"],["🍽 Моя столовая"],["🎫 Мои дополнительные талоны"]])
REGISTER_KB=kb([["📝 Зарегистрироваться"]])
BACK_KB=kb([["⬅️ Назад"]])
CONTROL_KB=kb([["📋 Сегодня"],["⏰ Опоздавшие","🚪 Ранний уход"],["❌ Кто не пришёл"],["🍽 Сейчас в столовой","🎫 Доп. талоны"],["🔄 Обновить","⬅️ Назад"]])
EMPLOYEES_KB=kb([["➕ Зарегистрировать сотрудника"],["📋 Список сотрудников"],["⏳ Заявки"],["🚫 Уволить сотрудника"],["⬅️ Назад"]])
REPORTS_KB=kb([["📊 Посещаемость 1–15","📊 Посещаемость 16–конец"],["📊 Посещаемость месяц"],["🍽 Столовая 1–15","🍽 Столовая 16–конец"],["🍽 Столовая месяц"],["⬅️ Назад"]])
SETTINGS_KB=kb([["ℹ️ Правила системы"],["⬅️ Назад"]])

def user(tg):
    return fetch("""SELECT tu.*,e.full_name,e.dahua_user_id,e.registration_status,e.active employee_active
                    FROM telegram_users tu LEFT JOIN employees e ON e.id=tu.employee_id
                    WHERE tu.telegram_id=%s""",(tg,),True)

def now():
    return datetime.now(TZ)

def shift_for(dt):
    t=dt.astimezone(TZ).time()
    if dt.astimezone(TZ).weekday()==0:
        if time(8)<=t<time(12): return "FIRST"
        if t>=time(12): return "SECOND"
    else:
        if time(8)<=t<time(11): return "FIRST"
        if t>=time(12): return "SECOND"
    return None

def shift(code):
    return fetch("SELECT * FROM shifts WHERE code=%s",(code,),True)

def event_rows(day):
    return fetch("""SELECT e.full_name,e.dahua_user_id,
                    MIN(d.create_time) first_entry,MAX(d.create_time) last_exit
                    FROM employees e JOIN dahua_events d ON d.user_id=e.dahua_user_id
                    WHERE e.active=true AND e.registration_status='ACTIVE'
                    AND d.status=1
                    AND (d.create_time AT TIME ZONE 'Asia/Tashkent')::date=%s
                    GROUP BY e.full_name,e.dahua_user_id ORDER BY first_entry""",(day,))

def attendance(day):
    out=[]
    for r in event_rows(day):
        first=r["first_entry"].astimezone(TZ)
        last=r["last_exit"].astimezone(TZ)
        code=shift_for(first)
        if not code: continue
        s=shift(code)
        late=max(0,int((first.replace(tzinfo=None)-datetime.combine(day,s["start_time"])).total_seconds()/60))
        early=0
        if day<date.today() or now().time()>=s["end_time"]:
            early=max(0,int((datetime.combine(day,s["end_time"])-last.replace(tzinfo=None)).total_seconds()/60))
        out.append({**r,"first":first,"last":last,"shift":code,"late":late,"early":early})
    return out

def hm(x):
    return x.astimezone(TZ).strftime("%H:%M") if x else "—"

def period(which):
    d=now().date(); first=d.replace(day=1)
    last=(first.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1)
    if which=="first": return first,first.replace(day=15)
    if which=="second": return first.replace(day=16),last
    return first,last

def dahua_face_add(uid,name,image_bytes):
    b64=base64.b64encode(image_bytes).decode()
    payload={"UserID":str(uid),"Info":{"UserName":name,"PhotoData":[b64]}}
    r=requests.post(
        f"https://{DAHUA_HOST}/cgi-bin/FaceInfoManager.cgi?action=add",
        auth=HTTPDigestAuth(DAHUA_USER,DAHUA_PASSWORD),
        json=payload,verify=False,timeout=30)
    return r

def dahua_face_remove(uid):
    return requests.get(
        f"https://{DAHUA_HOST}/cgi-bin/FaceInfoManager.cgi?action=remove&UserID={uid}",
        auth=HTTPDigestAuth(DAHUA_USER,DAHUA_PASSWORD),
        verify=False,timeout=15)

def next_dahua_id():
    a=fetch("SELECT COALESCE(MAX(dahua_user_id),0) mx FROM employees",one=True)["mx"]
    b=fetch("SELECT COALESCE(MAX(dahua_user_id),0) mx FROM employee_registration_requests",one=True)["mx"]
    return max(int(a or 0),int(b or 0))+1

async def home(m):
    u=user(m.from_user.id)
    if not u:
        await m.answer("👋 <b>FUNLANDIA STAFF</b>\n\nДля начала зарегистрируйтесь.",reply_markup=REGISTER_KB); return
    if u["role"]=="OWNER": await m.answer("👑 <b>ВЛАДЕЛЕЦ</b>",reply_markup=OWNER_KB)
    elif u["role"]=="MANAGER": await m.answer("📊 <b>МЕНЕДЖЕР</b>",reply_markup=MANAGER_KB)
    elif u["role"]=="CAFETERIA": await m.answer("🍽 <b>СТОЛОВАЯ</b>",reply_markup=CAFE_KB)
    elif u["role"]=="EMPLOYEE" and u["employee_id"] and u["registration_status"]=="ACTIVE":
        await m.answer(f"👤 <b>{u['full_name']}</b>",reply_markup=EMP_KB)
    else:
        await m.answer("⏳ Ваша заявка ожидает подтверждения владельца.",reply_markup=REGISTER_KB)

@dp.message(CommandStart())
async def start(m:Message,state:FSMContext):
    await state.clear()
    await home(m)

@dp.message(Command("menu"))
async def menu(m:Message): await home(m)

@dp.message(Command("cancel"))
async def cancel(m:Message,state:FSMContext):
    await state.clear(); await home(m)

@dp.message(F.text=="⬅️ Назад")
async def back(m:Message,state:FSMContext):
    await state.clear(); await home(m)

async def start_reg(m,state,owner_mode=False,manager_mode=False):
    u=user(m.from_user.id)
    if u and u["employee_id"]:
        await m.answer("❌ Этот Telegram уже связан с сотрудником."); return
    p=fetch("SELECT id FROM employee_registration_requests WHERE claimed_telegram_id=%s AND status='WAITING_APPROVAL'",(m.from_user.id,),True)
    if p: await m.answer("⏳ Заявка уже отправлена владельцу."); return
    await state.update_data(owner_mode=owner_mode,manager_mode=manager_mode)
    await state.set_state(Reg.surname)
    await m.answer("Введите <b>фамилию</b>:",reply_markup=BACK_KB)

@dp.message(F.text=="📝 Зарегистрироваться")
async def self_reg(m:Message,state:FSMContext): await start_reg(m,state)

@dp.message(F.text=="➕ Зарегистрировать сотрудника")
async def register_employee(m:Message,state:FSMContext):
    u=user(m.from_user.id)
    if not u or u["role"] not in ("OWNER","MANAGER"):
        return
    await start_reg(m,state,u["role"]=="OWNER",u["role"]=="MANAGER")

@dp.message(StateFilter(Reg.surname))
async def reg_surname(m:Message,state:FSMContext):
    await state.update_data(surname=m.text.strip()); await state.set_state(Reg.first); await m.answer("Введите <b>имя</b>:")

@dp.message(StateFilter(Reg.first))
async def reg_first(m:Message,state:FSMContext):
    await state.update_data(first=m.text.strip()); await state.set_state(Reg.patronymic); await m.answer("Введите <b>отчество</b>:")

@dp.message(StateFilter(Reg.patronymic))
async def reg_pat(m:Message,state:FSMContext):
    await state.update_data(patronymic=m.text.strip()); await state.set_state(Reg.phone); await m.answer("Введите <b>номер телефона</b> вручную:")

@dp.message(StateFilter(Reg.phone))
async def reg_phone(m:Message,state:FSMContext):
    await state.update_data(phone=m.text.strip()); await state.set_state(Reg.age); await m.answer("Введите <b>возраст</b>:")

@dp.message(StateFilter(Reg.age))
async def reg_age(m:Message,state:FSMContext):
    try: age=int(m.text.strip())
    except: return await m.answer("Введите возраст числом.")
    if age<14 or age>100: return await m.answer("Возраст должен быть от 14 до 100.")
    await state.update_data(age=age); await state.set_state(Reg.gender); await m.answer("Введите пол: <b>М</b> или <b>Ж</b>:")

@dp.message(StateFilter(Reg.gender))
async def reg_gender(m:Message,state:FSMContext):
    g=m.text.strip().upper()
    if g not in ("М","Ж","M","F"): return await m.answer("Введите М или Ж.")
    await state.update_data(gender="М" if g in ("М","M") else "Ж")
    await state.set_state(Reg.photo)
    await m.answer("📸 Отправьте фотографию лица одним фото.")

@dp.message(StateFilter(Reg.photo),F.photo)
async def reg_photo(m:Message,state:FSMContext):
    d=await state.get_data()
    name=f"{d['surname']} {d['first']} {d['patronymic']}".strip()
    uid=next_dahua_id()
    try:
        tgfile=await bot.get_file(m.photo[-1].file_id)
        import io
        buf=io.BytesIO()
        await bot.download_file(tgfile.file_path,buf)
        resp=dahua_face_add(uid,name,buf.getvalue())
        if not resp.ok or "error" in resp.text.lower():
            await m.answer(f"❌ Dahua не принял фотографию. HTTP {resp.status_code}\n{resp.text[:400]}")
            return
    except Exception as e:
        await m.answer(f"❌ Ошибка Dahua: {e}"); return

    if d["owner_mode"]:
        with conn() as c, c.cursor() as cur:
            cur.execute("""INSERT INTO employees
                (dahua_user_id,full_name,active,is_test,hired_at,registration_status,registered_at)
                VALUES(%s,%s,true,false,%s,'ACTIVE',NOW()) RETURNING id""",(uid,name,date.today()))
            eid=cur.fetchone()[0]
            # Owner registration creates the employee but never changes the owner's Telegram role.
        await state.clear()
        await m.answer(f"✅ <b>СОТРУДНИК АКТИВИРОВАН</b>\n\n👤 {name}\n🆔 Dahua ID: {uid}\n📱 {d['phone']}\n🎂 {d['age']}\n⚧ {d['gender']}",reply_markup=EMP_KB)
        return

    claimed=None if d["manager_mode"] else m.from_user.id
    creator=m.from_user.id
    run("""INSERT INTO employee_registration_requests
        (full_name,dahua_user_id,phone,claimed_telegram_id,created_by_telegram_id,status)
        VALUES(%s,%s,%s,%s,%s,'WAITING_APPROVAL')""",
        (name,uid,d["phone"],claimed,creator))
    req=fetch("SELECT * FROM employee_registration_requests WHERE dahua_user_id=%s ORDER BY id DESC LIMIT 1",(uid,),True)
    await state.clear()
    await m.answer("⏳ Заявка отправлена владельцу на подтверждение.")
    txt=f"🔔 <b>НОВАЯ ЗАЯВКА</b>\n\n👤 {name}\n🆔 Dahua ID: {uid}\n📱 {d['phone']}\n🎂 {d['age']}\n⚧ {d['gender']}\n\nРегистратор: {creator}"
    await bot.send_message(OWNER_ID,txt,reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить",callback_data=f"approve:{req['id']}"),
         InlineKeyboardButton(text="❌ Отклонить",callback_data=f"reject:{req['id']}")]]))

@dp.message(StateFilter(Reg.photo))
async def no_photo(m:Message): await m.answer("Пожалуйста, отправьте именно фотографию.")

@dp.callback_query(F.data.startswith("approve:"))
async def approve(c:CallbackQuery):
    if c.from_user.id!=OWNER_ID: return await c.answer("Нет доступа",show_alert=True)
    rid=int(c.data.split(":")[1])
    r=fetch("SELECT * FROM employee_registration_requests WHERE id=%s",(rid,),True)
    if not r or r["status"]!="WAITING_APPROVAL": return await c.answer("Заявка уже обработана",show_alert=True)
    with conn() as dbx,dbx.cursor() as cur:
        cur.execute("""INSERT INTO employees
            (dahua_user_id,full_name,active,is_test,hired_at,registration_status,registered_at)
            VALUES(%s,%s,true,false,%s,'ACTIVE',NOW()) RETURNING id""",(r["dahua_user_id"],r["full_name"],date.today()))
        eid=cur.fetchone()[0]
        cur.execute("UPDATE employee_registration_requests SET status='APPROVED',updated_at=NOW() WHERE id=%s",(rid,))
        if r["claimed_telegram_id"]:
            cur.execute("""INSERT INTO telegram_users(telegram_id,role,employee_id,active,phone)
                VALUES(%s,'EMPLOYEE',%s,true,%s)
                ON CONFLICT(telegram_id) DO UPDATE SET employee_id=EXCLUDED.employee_id,
                role='EMPLOYEE',active=true,phone=EXCLUDED.phone,updated_at=NOW()""",
                (r["claimed_telegram_id"],eid,r["phone"]))
    await c.message.edit_text(c.message.text+"\n\n✅ <b>ОДОБРЕНО</b>")
    await c.answer("Одобрено")
    if r["claimed_telegram_id"]:
        await bot.send_message(r["claimed_telegram_id"],"✅ Регистрация одобрена.",reply_markup=EMP_KB)

@dp.callback_query(F.data.startswith("reject:"))
async def reject(c:CallbackQuery):
    if c.from_user.id!=OWNER_ID: return await c.answer("Нет доступа",show_alert=True)
    rid=int(c.data.split(":")[1])
    r=fetch("SELECT * FROM employee_registration_requests WHERE id=%s",(rid,),True)
    if not r or r["status"]!="WAITING_APPROVAL": return await c.answer("Заявка уже обработана",show_alert=True)
    run("UPDATE employee_registration_requests SET status='REJECTED',updated_at=NOW() WHERE id=%s",(rid,))
    try: dahua_face_remove(r["dahua_user_id"])
    except: pass
    await c.message.edit_text(c.message.text+"\n\n❌ <b>ОТКЛОНЕНО</b>"); await c.answer("Отклонено")
    if r["claimed_telegram_id"]:
        await bot.send_message(r["claimed_telegram_id"],"❌ Ваша заявка отклонена.",reply_markup=REGISTER_KB)

@dp.message(F.text=="📊 Контроль")
async def control(m:Message):
    if user(m.from_user.id)["role"]=="OWNER": await m.answer("📊 <b>КОНТРОЛЬ</b>",reply_markup=CONTROL_KB)

def control_text():
    d=now().date(); rows=attendance(d)
    if not rows:return "📋 <b>СЕГОДНЯ</b>\nНет успешных Face ID."
    return "📋 <b>СЕГОДНЯ</b>\n\n"+"\n".join(
        f"👤 {r['full_name']} — {hm(r['first'])} → {hm(r['last'])} | {r['shift']} | ⏰ {r['late']} мин."
        for r in rows)

@dp.message(F.text.in_({"📋 Сегодня","🔄 Обновить","👥 Сейчас на работе"}))
async def today(m:Message):
    u=user(m.from_user.id)
    if u and u["role"] in ("OWNER","MANAGER"): await m.answer(control_text(),reply_markup=CONTROL_KB if u["role"]=="OWNER" else MANAGER_KB)

def late_text():
    x=[r for r in attendance(now().date()) if r["late"]>0]
    return "⏰ <b>ОПОЗДАВШИЕ</b>\n\n"+("\n".join(f"• {r['full_name']} — {r['late']} мин." for r in x) if x else "Нет опоздавших.")

def early_text():
    x=[r for r in attendance(now().date()) if r["early"]>0]
    return "🚪 <b>РАННИЙ УХОД</b>\n\n"+("\n".join(f"• {r['full_name']} — {r['early']} мин." for r in x) if x else "Нет ранних уходов.")

@dp.message(F.text=="⏰ Опоздавшие")
async def late(m:Message):
    u=user(m.from_user.id)
    if u and u["role"] in ("OWNER","MANAGER"): await m.answer(late_text())

@dp.message(F.text=="🚪 Ранний уход")
async def early(m:Message):
    u=user(m.from_user.id)
    if u and u["role"] in ("OWNER","MANAGER"): await m.answer(early_text())

@dp.message(F.text=="❌ Кто не пришёл")
async def absent(m:Message):
    if m.from_user.id!=OWNER_ID:return
    present={r["dahua_user_id"] for r in event_rows(now().date())}
    em=fetch("SELECT full_name,dahua_user_id FROM employees WHERE active=true AND registration_status='ACTIVE' ORDER BY full_name")
    names=[e["full_name"] for e in em if e["dahua_user_id"] not in present]
    await m.answer("❌ <b>НЕ ПРИШЛИ</b>\n\n"+("\n".join("• "+x for x in names) if names else "Никого нет."))

@dp.message(F.text=="🎫 Доп. талоны")
async def extra_today(m:Message):
    if m.from_user.id!=OWNER_ID:return
    r=fetch("""SELECT COUNT(*) c,COALESCE(SUM(price),0) s FROM meal_transactions
               WHERE meal_date=%s AND status='ISSUED' AND ticket_type='EXTRA'""",(now().date(),),True)
    await m.answer(f"🎫 <b>ДОПОЛНИТЕЛЬНЫЕ ТАЛОНЫ</b>\n\nКоличество: {r['c']}\nСумма: {int(r['s']):,} сум".replace(","," "))

@dp.message(F.text=="👥 Сотрудники")
async def employees(m:Message):
    if m.from_user.id==OWNER_ID: await m.answer("👥 <b>СОТРУДНИКИ</b>",reply_markup=EMPLOYEES_KB)

@dp.message(F.text=="📋 Список сотрудников")
async def employee_list(m:Message):
    if m.from_user.id!=OWNER_ID:return
    rows=fetch("SELECT full_name,dahua_user_id,active FROM employees ORDER BY full_name")
    await m.answer("👥 <b>СПИСОК</b>\n\n"+"\n".join(f"• {r['full_name']} — Dahua {r['dahua_user_id']} — {'ACTIVE' if r['active'] else 'FIRED'}" for r in rows))

@dp.message(F.text=="⏳ Заявки")
async def requests(m:Message):
    if m.from_user.id!=OWNER_ID:return
    rows=fetch("SELECT * FROM employee_registration_requests WHERE status='WAITING_APPROVAL' ORDER BY id")
    if not rows:return await m.answer("⏳ Заявок нет.")
    for r in rows:
        await m.answer(f"👤 <b>{r['full_name']}</b>\n🆔 {r['dahua_user_id']}\n📱 {r['phone'] or '—'}",
                       reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Одобрить",callback_data=f"approve:{r['id']}"),InlineKeyboardButton(text="❌ Отклонить",callback_data=f"reject:{r['id']}")]]))

@dp.message(F.text=="🚫 Уволить сотрудника")
async def fire_start(m:Message,state:FSMContext):
    if m.from_user.id!=OWNER_ID:return
    await state.set_state(Fire.name); await m.answer("Введите точное ФИО сотрудника:",reply_markup=BACK_KB)

@dp.message(StateFilter(Fire.name))
async def fire_do(m:Message,state:FSMContext):
    if m.from_user.id!=OWNER_ID:return
    r=fetch("SELECT * FROM employees WHERE full_name=%s AND active=true",(m.text.strip(),),True)
    if not r:return await m.answer("Не найдено. Введите точное ФИО.")
    try: dahua_face_remove(r["dahua_user_id"])
    except: pass
    run("UPDATE employees SET active=false,registration_status='FIRED',fired_at=NOW() WHERE id=%s",(r["id"],))
    run("UPDATE telegram_users SET active=false WHERE employee_id=%s",(r["id"],))
    await state.clear(); await m.answer(f"🚫 {r['full_name']} уволен.",reply_markup=EMPLOYEES_KB)

def cafe_report(a,b):
    r=fetch("""SELECT COUNT(*) FILTER(WHERE meal_type='MEAL') lunch,
                      COUNT(*) FILTER(WHERE meal_type='DINNER') dinner,
                      COUNT(*) FILTER(WHERE ticket_type='EXTRA') extra,
                      COALESCE(SUM(price) FILTER(WHERE ticket_type='EXTRA'),0) amount
               FROM meal_transactions WHERE status='ISSUED' AND meal_date BETWEEN %s AND %s""",(a,b),True)
    return f"🍽 <b>СТОЛОВАЯ</b>\n\n🍲 Обед: {r['lunch'] or 0} человек\n🍽 Ужин: {r['dinner'] or 0} человек\n🎫 Дополнительные талоны: {r['extra'] or 0} человек\n💰 Сумма: {int(r['amount'] or 0):,} сум".replace(","," ")

@dp.message(F.text=="🍽 Столовая")
async def cafe(m:Message):
    u=user(m.from_user.id)
    if u and u["role"] in ("OWNER","CAFETERIA"): await m.answer("🍽 <b>СТОЛОВАЯ</b>",reply_markup=CAFE_KB)

@dp.message(F.text.in_({"🍲 Сегодня","📅 1–15","📅 16–конец месяца"}))
async def cafe_reports(m:Message):
    u=user(m.from_user.id)
    if not u or u["role"] not in ("OWNER","CAFETERIA"):return
    if m.text=="🍲 Сегодня": a=b=now().date()
    elif m.text=="📅 1–15": a,b=period("first")
    else:a,b=period("second")
    await m.answer(cafe_report(a,b))

@dp.message(F.text=="📑 Отчёты")
async def reports(m:Message):
    if m.from_user.id==OWNER_ID: await m.answer("📑 <b>ОТЧЁТЫ</b>",reply_markup=REPORTS_KB)

def att_report(a,b):
    em=fetch("SELECT full_name,dahua_user_id FROM employees WHERE active=true OR fired_at IS NULL ORDER BY full_name")
    lines=[f"📊 <b>ПОСЕЩАЕМОСТЬ {a.strftime('%d.%m')}–{b.strftime('%d.%m')}</b>",""]
    d=a
    while d<=b:
        rows=attendance(d)
        by={r["dahua_user_id"]:r for r in rows}
        for e in em:
            if e["dahua_user_id"] in by:
                pass
        d+=timedelta(days=1)
    for e in em:
        days=late=early=0; d=a
        while d<=b:
            r=next((x for x in attendance(d) if x["dahua_user_id"]==e["dahua_user_id"]),None)
            if r: days+=1; late+=r["late"]; early+=r["early"]
            d+=timedelta(days=1)
        lines.append(f"• {e['full_name']} — дней: {days}, опоздание: {late} мин., ранний уход: {early} мин.")
    return "\n".join(lines)

@dp.message(F.text.in_({"📊 Посещаемость 1–15","📊 Посещаемость 16–конец","📊 Посещаемость месяц","🍽 Столовая 1–15","🍽 Столовая 16–конец","🍽 Столовая месяц"}))
async def report_action(m:Message):
    if m.from_user.id!=OWNER_ID:return
    which="first" if "1–15" in m.text else "second" if "16–конец" in m.text else "month"
    a,b=period(which)
    await m.answer(att_report(a,b) if "Посещаемость" in m.text else cafe_report(a,b))

@dp.message(F.text=="📱 QR столовой")
async def qr(m:Message):
    if m.from_user.id==OWNER_ID:
        await m.answer("📱 <b>QR СТОЛОВОЙ</b>\n\nПостоянная ссылка:\n<code>https://t.me/FunlandiaStaffBot?start=cafeteria</code>\n\nQR используется только для столовой.")

@dp.message(F.text=="⚙️ Настройки")
async def settings(m:Message):
    if m.from_user.id==OWNER_ID: await m.answer("⚙️ <b>НАСТРОЙКИ</b>",reply_markup=SETTINGS_KB)

@dp.message(F.text=="ℹ️ Правила системы")
async def rules(m:Message):
    if m.from_user.id==OWNER_ID:
        await m.answer("• Face ID — источник посещаемости.\n• Первый успешный Face ID — приход.\n• Последний успешный — уход.\n• 08:00–10:59 — 1-я смена.\n• С 12:00 — 2-я смена.\n• В понедельник 08:00–11:59 — 1-я, с 12:00 — 2-я.\n• Столовая отдельно.\n• Доп. талон — 25 000 сум.")

@dp.message(F.text=="📊 Моя посещаемость")
async def my_att(m:Message):
    u=user(m.from_user.id)
    if not u or not u["employee_id"]:return await m.answer("Профиль не активирован.")
    r=next((x for x in attendance(now().date()) if x["dahua_user_id"]==u["dahua_user_id"]),None)
    if not r:return await m.answer("Сегодня успешного Face ID ещё нет.")
    await m.answer(f"📊 <b>МОЯ ПОСЕЩАЕМОСТЬ</b>\n\n🕘 Приход: {hm(r['first'])}\n📋 Смена: {r['shift']}\n⏰ Опоздание: {r['late']} минут\n🚪 Уход: {hm(r['last'])}\n⚠️ Ранний уход: {r['early']} минут")

@dp.message(F.text=="🍽 Моя столовая")
async def my_cafe(m:Message):
    u=user(m.from_user.id)
    if not u or not u["employee_id"]:return await m.answer("Профиль не активирован.")
    r=fetch("""SELECT COUNT(*) FILTER(WHERE meal_type='MEAL') lunch,
                      COUNT(*) FILTER(WHERE meal_type='DINNER') dinner,
                      COUNT(*) FILTER(WHERE ticket_type='EXTRA') extra
               FROM meal_transactions WHERE employee_id=%s AND meal_date=%s AND status='ISSUED'""",(u["employee_id"],now().date()),True)
    await m.answer(f"🍽 <b>МОЯ СТОЛОВАЯ</b>\n\n🍲 Обед: {r['lunch'] or 0}\n🍽 Ужин: {r['dinner'] or 0}\n🎫 Доп. талоны: {r['extra'] or 0}")

@dp.message(F.text=="🎫 Мои дополнительные талоны")
async def my_extra(m:Message):
    u=user(m.from_user.id)
    if not u or not u["employee_id"]:return await m.answer("Профиль не активирован.")
    a,b=period("month")
    r=fetch("""SELECT COUNT(*) c,COALESCE(SUM(price),0) s FROM meal_transactions
               WHERE employee_id=%s AND meal_date BETWEEN %s AND %s AND ticket_type='EXTRA' AND status='ISSUED'""",(u["employee_id"],a,b),True)
    await m.answer(f"🎫 <b>МОИ ДОПОЛНИТЕЛЬНЫЕ ТАЛОНЫ</b>\n\nКоличество: {r['c']}\nСумма: {int(r['s'] or 0):,} сум".replace(","," "))

@dp.message(F.text=="🍽 Сейчас на обеде")
async def manager_lunch(m:Message):
    u=user(m.from_user.id)
    if not u or u["role"] not in ("OWNER","MANAGER"):return
    rows=fetch("""SELECT e.full_name,mt.meal_type,MAX(mt.issued_at) issued
                  FROM meal_transactions mt JOIN employees e ON e.id=mt.employee_id
                  WHERE mt.meal_date=%s AND mt.status='ISSUED'
                  GROUP BY e.full_name,mt.meal_type ORDER BY issued DESC""",(now().date(),))
    await m.answer("🍽 <b>СЕЙЧАС В СТОЛОВОЙ</b>\n\n"+("\n".join(f"• {r['full_name']} — {'обед' if r['meal_type']=='MEAL' else 'ужин'}" for r in rows) if rows else "Никого нет."))

@dp.message()
async def fallback(m:Message):
    await m.answer("Выберите пункт меню или /start.")

async def main():
    print("FUNLANDIA STAFF BOT STARTED")
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
