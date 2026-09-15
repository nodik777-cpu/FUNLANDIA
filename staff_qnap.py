import os, re, json, sqlite3, hashlib, logging, asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
import requests
from requests.auth import HTTPDigestAuth
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, CallbackQueryHandler, filters
import qrcode

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('funlandia_staff_qnap')

BOT_TOKEN = os.getenv('BOT_TOKEN','').strip()
DAHUA_URL = os.getenv('DAHUA_URL','https://192.168.1.202').rstrip('/')
DAHUA_USER = os.getenv('DAHUA_USER','admin').strip()
DAHUA_PASSWORD = os.getenv('DAHUA_PASSWORD','').strip()
DB_PATH = os.getenv('STAFF_DB_PATH','/data/staff.db')
ADMIN_ID = os.getenv('STAFF_ADMIN_CHAT_ID','').strip()
CONTROL_IDS = {x.strip() for x in os.getenv('STAFF_CONTROL_IDS','').split(',') if x.strip()}
TZ = timezone(timedelta(hours=5))
POLL = int(os.getenv('DAHUA_POLL_SECONDS','10'))
LUNCH_START = os.getenv('LUNCH_START','10:00')
LUNCH_END = os.getenv('LUNCH_END','15:00')
DINNER_START = os.getenv('DINNER_START','17:00')
DINNER_END = os.getenv('DINNER_END','22:00')
EXTRA_MEAL_COST = int(os.getenv('EXTRA_MEAL_COST','0'))


def now(): return datetime.now(TZ)

def db():
    c=sqlite3.connect(DB_PATH,timeout=30); c.row_factory=sqlite3.Row; return c

def init_db():
    c=db()
    c.execute('''CREATE TABLE IF NOT EXISTS employees(
      dahua_id TEXT PRIMARY KEY,name TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,
      telegram_id INTEGER,role TEXT NOT NULL DEFAULT 'employee',created_at TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS attendance(
      rec_no TEXT PRIMARY KEY,user_id TEXT NOT NULL,name TEXT NOT NULL,event_time TEXT NOT NULL,
      event_type TEXT NOT NULL,status INTEGER NOT NULL,raw TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS meals(
      id INTEGER PRIMARY KEY AUTOINCREMENT,dahua_id TEXT NOT NULL,name TEXT NOT NULL,
      meal_type TEXT NOT NULL,meal_date TEXT NOT NULL,requested_at TEXT NOT NULL,
      served_at TEXT,returned_at TEXT,status TEXT NOT NULL DEFAULT 'requested',extra INTEGER NOT NULL DEFAULT 0,
      UNIQUE(dahua_id,meal_type,meal_date))''')
    c.execute('''CREATE TABLE IF NOT EXISTS access_requests(
      telegram_id INTEGER PRIMARY KEY,username TEXT,first_name TEXT,requested_role TEXT NOT NULL,
      created_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending')''')
    c.execute('CREATE TABLE IF NOT EXISTS user_roles(telegram_id INTEGER PRIMARY KEY,role TEXT NOT NULL)')
    c.commit(); c.close()


def parse_time(v):
    s=str(v or '').strip()
    if s.isdigit() and len(s)>=9:
        n=int(s); n=n/1000 if n>10_000_000_000 else n
        return datetime.fromtimestamp(n,timezone.utc).astimezone(TZ)
    s=s.replace('Z','+00:00')
    for fmt in (None,'%Y-%m-%d %H:%M:%S','%Y/%m/%d %H:%M:%S'):
        try:
            d=datetime.fromisoformat(s) if fmt is None else datetime.strptime(s,fmt)
            return (d if d.tzinfo else d.replace(tzinfo=TZ)).astimezone(TZ)
        except Exception: pass
    return now()


def get_records(start,end):
    p={'action':'find','name':'AccessControlCardRec','StartTime':str(int(start.timestamp())),'EndTime':str(int(end.timestamp())),'count':'1024'}
    r=requests.get(DAHUA_URL+'/cgi-bin/recordFinder.cgi',params=p,auth=HTTPDigestAuth(DAHUA_USER,DAHUA_PASSWORD),verify=False,timeout=15)
    if r.status_code in (401,403): r=requests.get(DAHUA_URL+'/cgi-bin/recordFinder.cgi',params=p,auth=(DAHUA_USER,DAHUA_PASSWORD),verify=False,timeout=15)
    r.raise_for_status()
    rows={}
    for line in r.text.replace('\r','').splitlines():
        m=re.match(r'records\[(\d+)\]\.([^=]+)=(.*)$',line)
        if m: rows.setdefault(m.group(1),{})[m.group(2)]=m.group(3)
    return list(rows.values())


def import_records(records,notify=True):
    c=db(); new=[]
    for x in records:
        uid=str(x.get('UserID','')).strip(); name=str(x.get('CardName','')).strip() or uid
        if not uid: continue
        status=int(x.get('Status','1') or 1); err=int(x.get('ErrorCode','0') or 0)
        if status!=1 or err!=0: continue
        rec=str(x.get('RecNo','')).strip()
        if not rec: rec=hashlib.sha1(json.dumps(x,sort_keys=True).encode()).hexdigest()
        tm=parse_time(x.get('CreateTime'))
        typ=str(x.get('Type','')).strip()
        if typ not in ('Entry','Exit'): typ='Entry'
        try:
            c.execute('INSERT INTO attendance(rec_no,user_id,name,event_time,event_type,status,raw) VALUES(?,?,?,?,?,?,?)',
                      (rec,uid,name,tm.isoformat(),typ,1,json.dumps(x,ensure_ascii=False)))
            new.append((uid,name,tm,typ))
        except sqlite3.IntegrityError: pass
    c.commit(); c.close()
    if notify:
        for uid,name,tm,typ in new:
            if typ=='Entry': notify_entry(uid,name,tm)
    return len(new)


def tg_send(chat_id,text):
    if not chat_id or not BOT_TOKEN:return
    try: requests.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',json={'chat_id':int(chat_id),'text':text},timeout=8)
    except Exception: pass


def notify_entry(uid,name,tm):
    c=db(); r=c.execute('SELECT telegram_id FROM employees WHERE dahua_id=? AND telegram_id IS NOT NULL',(uid,)).fetchall(); c.close()
    text=f'🟢 ВХОД\n\n👤 {name}\n🆔 ID: {uid}\n🕐 {tm.strftime("%d.%m.%Y %H:%M")}'
    for row in r: tg_send(row['telegram_id'],text)


def last_events(uid,date=None):
    c=db(); q='SELECT * FROM attendance WHERE user_id=?'; args=[uid]
    if date: q+=' AND date(event_time)=?'; args.append(date)
    q+=' ORDER BY event_time'
    rows=c.execute(q,args).fetchall(); c.close(); return rows


def shift_for(uid,date):
    rows=last_events(uid,date)
    if not rows:return '—'
    ins=[r for r in rows if r['event_type']=='Entry']; outs=[r for r in rows if r['event_type']=='Exit']
    if not ins:return '—'
    e=datetime.fromisoformat(ins[0]['event_time']); x=datetime.fromisoformat(outs[-1]['event_time']) if outs else None
    eh=e.hour+e.minute/60; xh=(x.hour+x.minute/60) if x else None
    if xh is not None and xh>=21.75 and 9.75<=eh<=10.25:return 'Нестандартная'
    if xh is not None and xh>=21.25:return '2-я'
    if xh is not None and xh<=20.75:return '1-я'
    return '1-я' if eh<12.5 else '2-я'


def in_time(t):
    h,m=map(int,t.split(':')); return h*60+m

def meal_window(kind,dt):
    n=dt.hour*60+dt.minute
    a,b=(LUNCH_START,LUNCH_END) if kind=='Обед' else (DINNER_START,DINNER_END)
    return in_time(a)<=n<=in_time(b)


def role(uid):
    s=str(uid)
    if ADMIN_ID and s==ADMIN_ID:return 'owner'
    if s in CONTROL_IDS:return 'control'
    c=db(); r=c.execute('SELECT role FROM user_roles WHERE telegram_id=?',(int(uid),)).fetchone()
    if r: c.close(); return r['role']
    r=c.execute('SELECT role FROM employees WHERE telegram_id=? AND active=1',(int(uid),)).fetchone(); c.close()
    return r['role'] if r else 'none'


def kb_for(r):
    if r=='owner': return ReplyKeyboardMarkup([['👥 Сотрудники','📊 Контроль'],['🍽 Питание','📊 Отчёты'],['➕ Добавить сотрудника','🎫 Доп. талон'],['📱 QR столовой']],resize_keyboard=True)
    if r=='control': return ReplyKeyboardMarkup([['📊 Контроль'],['🍲 Обед сейчас','🍽 Ужин сейчас'],['👥 Сейчас на работе'],['🔴 Опоздания','⚠️ Ранний уход']],resize_keyboard=True)
    if r=='canteen': return ReplyKeyboardMarkup([['🍽 Столовая'],['📊 Сегодня питание']],resize_keyboard=True)
    if r=='employee': return ReplyKeyboardMarkup([['👤 Мои записи','🍽 Питание'],['ℹ️ Помощь']],resize_keyboard=True)
    return ReplyKeyboardMarkup([['🔐 Запросить доступ']],resize_keyboard=True)


async def start(update,ctx):
    if ctx.args and ctx.args[0]=='meal' and role(update.effective_user.id)=='employee': return await meal(update,ctx)
    r=role(update.effective_user.id)
    if r=='none':
        await update.message.reply_text('🔒 Доступ ограничен.\n\nЕсли вам нужен доступ, нажмите «Запросить доступ».',reply_markup=kb_for('none')); return
    await update.message.reply_text(f'Добро пожаловать в Staff Bot.\nРоль: {r}',reply_markup=kb_for(r))


async def access_request(update,ctx):
    u=update.effective_user
    c=db(); c.execute('INSERT OR REPLACE INTO access_requests VALUES(?,?,?,?,?,?)',(u.id,u.username,u.first_name,'employee',now().isoformat(),'pending')); c.commit(); c.close()
    if ADMIN_ID:
        text=f'🚨 ЗАПРОС ДОСТУПА\n👤 {u.first_name or ""} @{u.username or "—"}\n🆔 Telegram ID: {u.id}'
        markup={'inline_keyboard':[[{'text':'👤 Сотрудник','callback_data':f'access:employee:{u.id}'},{'text':'🍽 Столовая','callback_data':f'access:canteen:{u.id}'}],[{'text':'📊 Контроль','callback_data':f'access:control:{u.id}'},{'text':'❌ Отклонить','callback_data':f'access:deny:{u.id}'}]]}
        try: requests.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',json={'chat_id':int(ADMIN_ID),'text':text,'reply_markup':markup},timeout=8)
        except Exception: pass
    await update.message.reply_text('⏳ Запрос отправлен администратору.')


async def access_callback(update,ctx):
    q=update.callback_query; await q.answer()
    if role(q.from_user.id)!='owner': await q.edit_message_text('🔒 Только главный администратор.'); return
    _,action,tid=q.data.split(':'); tid=int(tid)
    c=db()
    if action=='deny':
        c.execute("UPDATE access_requests SET status='denied' WHERE telegram_id=?",(tid,)); c.commit(); c.close(); tg_send(tid,'❌ Доступ не предоставлен.'); await q.edit_message_text('❌ Запрос отклонён.'); return
    c.execute('INSERT OR REPLACE INTO user_roles(telegram_id,role) VALUES(?,?)',(tid,action)); c.execute("UPDATE access_requests SET status='approved',requested_role=? WHERE telegram_id=?",(action,tid)); c.commit(); c.close()
    tg_send(tid,f'✅ Доступ разрешён. Роль: {action}')
    await q.edit_message_text(f'✅ Доступ выдан: {action} для Telegram ID {tid}.')


async def link(update,ctx):
    if not ctx.args or not ctx.args[0]:
        await update.message.reply_text('Использование: /link ID_СОТРУДНИКА'); return
    uid=ctx.args[0]; c=db(); emp=c.execute('SELECT name FROM employees WHERE dahua_id=?',(uid,)).fetchone()
    if not emp:
        r=c.execute('SELECT name FROM attendance WHERE user_id=? ORDER BY event_time DESC LIMIT 1',(uid,)).fetchone()
        if not r: c.close(); await update.message.reply_text('ID пока не найден в Dahua. Сначала проведите сотрудника через Face ID.'); return
        c.execute('INSERT OR IGNORE INTO employees(dahua_id,name,telegram_id,role,created_at) VALUES(?,?,?,?,?)',(uid,r['name'],update.effective_user.id,'employee',now().isoformat()))
    else: c.execute('UPDATE employees SET telegram_id=?,name=? WHERE dahua_id=?',(update.effective_user.id,emp['name'],uid))
    c.commit(); c.close(); await update.message.reply_text(f'✅ Telegram привязан к ID {uid}.',reply_markup=kb_for('employee'))


async def today(update,ctx):
    uid=update.effective_user.id; c=db(); emp=c.execute('SELECT * FROM employees WHERE telegram_id=?',(uid,)).fetchone(); c.close()
    if not emp: await update.message.reply_text('Сначала привяжите Dahua ID командой /link ID.'); return
    rows=last_events(emp['dahua_id'],now().date().isoformat())
    if not rows: await update.message.reply_text('Сегодня записей нет.'); return
    text=[f'📅 {now():%d.%m.%Y}',f'👤 {emp["name"]}',f'🔄 Смена: {shift_for(emp["dahua_id"],now().date().isoformat())}']
    for r in rows: text.append(f'🕐 {datetime.fromisoformat(r["event_time"]):%H:%M} — {"Вход" if r["event_type"]=="Entry" else "Выход"}')
    await update.message.reply_text('\n'.join(text))


async def control(update,ctx):
    if role(update.effective_user.id) not in ('owner','control'): return
    date=now().date().isoformat(); c=db(); emps=c.execute('SELECT * FROM employees WHERE active=1 ORDER BY name').fetchall(); c.close()
    at_work=0; late=0; early=0
    for e in emps:
        rows=last_events(e['dahua_id'],date)
        if not rows: continue
        ins=[r for r in rows if r['event_type']=='Entry']; outs=[r for r in rows if r['event_type']=='Exit']
        if ins:
            last=rows[-1]
            if last['event_type']=='Entry': at_work+=1
            first=datetime.fromisoformat(ins[0]['event_time']); sh=shift_for(e['dahua_id'],date)
            start=10 if sh=='1-я' else 13 if sh=='2-я' else 10
            if first.hour*60+first.minute>start*60+5: late+=1
            if outs and datetime.fromisoformat(outs[-1]['event_time']).hour < (20 if sh=='1-я' else 22): early+=1
    c=db(); lunch=c.execute("SELECT COUNT(*) n FROM meals WHERE meal_date=? AND meal_type='Обед' AND status IN ('requested','served')",(date,)).fetchone()['n']; dinner=c.execute("SELECT COUNT(*) n FROM meals WHERE meal_date=? AND meal_type='Ужин' AND status IN ('requested','served')",(date,)).fetchone()['n']; c.close()
    await update.message.reply_text(f'📊 КОНТРОЛЬ — {now():%d.%m.%Y}\n\n👥 На работе: {at_work}\n🟢 Пришли вовремя: {max(at_work-late,0)}\n🔴 Опоздали: {late}\n⚠️ Рано ушли: {early}\n\n🍲 Сейчас на обеде: {lunch}\n🍽 Сейчас на ужине: {dinner}')


async def meal(update,ctx):
    u=update.effective_user; c=db(); e=c.execute('SELECT * FROM employees WHERE telegram_id=? AND active=1',(u.id,)).fetchone(); c.close()
    if not e: await update.message.reply_text('Сотрудник не привязан к Staff Bot. Обратитесь к администратору.'); return
    sh=shift_for(e['dahua_id'],now().date().isoformat()); buttons=[]
    if sh in ('1-я','Нестандартная'): buttons.append(InlineKeyboardButton('🍲 Обед',callback_data='meal:Обед'))
    buttons.append(InlineKeyboardButton('🍽 Ужин',callback_data='meal:Ужин'))
    await update.message.reply_text(f'👤 {e["name"]}\n🔄 Смена: {sh}\n\nВыберите питание:',reply_markup=InlineKeyboardMarkup([buttons]))


async def meal_callback(update,ctx):
    q=update.callback_query; await q.answer(); kind=q.data.split(':',1)[1]; u=q.from_user; c=db(); e=c.execute('SELECT * FROM employees WHERE telegram_id=? AND active=1',(u.id,)).fetchone(); c.close()
    if not e: await q.edit_message_text('Доступ закрыт.'); return
    date=now().date().isoformat(); sh=shift_for(e['dahua_id'],date); extra=(kind=='Обед' and sh=='2-я')
    c=db(); old=c.execute('SELECT * FROM meals WHERE dahua_id=? AND meal_type=? AND meal_date=?',(e['dahua_id'],kind,date)).fetchone()
    if old: c.close(); await q.edit_message_text(f'⚠️ {kind} сегодня уже зарегистрирован.\nСтатус: {old["status"]}'); return
    c.execute('INSERT INTO meals(dahua_id,name,meal_type,meal_date,requested_at,status,extra) VALUES(?,?,?,?,?,?,?)',(e['dahua_id'],e['name'],kind,date,now().isoformat(),'requested',int(extra))); c.commit(); c.close()
    if ADMIN_ID and extra: tg_send(ADMIN_ID,f'⚠️ ДОПОЛНИТЕЛЬНЫЙ ТАЛОН\n👤 {e["name"]}\n🍲 {kind}\n🕐 {now():%H:%M}\n🆔 {e["dahua_id"]}')
    await q.edit_message_text(f'⏳ Заявка принята.\n\n👤 {e["name"]}\n🍽 {kind}\n' + ('⚠️ Дополнительный талон' if extra else '🟢 По норме'))


async def canteen(update,ctx):
    if role(update.effective_user.id) not in ('owner','canteen'): return
    c=db(); rows=c.execute("SELECT * FROM meals WHERE meal_date=? AND status='requested' ORDER BY requested_at",(now().date().isoformat(),)).fetchall(); c.close()
    if not rows: await update.message.reply_text('🍽 Сейчас заявок на выдачу нет.'); return
    buttons=[[InlineKeyboardButton(f'✅ Выдать: {r["name"]} — {r["meal_type"]}',callback_data=f'serve:{r["id"]}')] for r in rows]
    await update.message.reply_text(f'🔔 ОЖИДАЮТ ВЫДАЧИ: {len(rows)}',reply_markup=InlineKeyboardMarkup(buttons))


async def serve(update,ctx):
    q=update.callback_query; await q.answer()
    if role(q.from_user.id) not in ('owner','canteen'): await q.edit_message_text('Доступ закрыт.'); return
    c=db(); r=c.execute('SELECT * FROM meals WHERE id=?',(int(q.data.split(':')[1]),)).fetchone()
    if not r: c.close(); await q.edit_message_text('Запись не найдена.'); return
    c.execute("UPDATE meals SET status='served',served_at=? WHERE id=? AND status='requested'",(now().isoformat(),r['id'])); c.commit(); c.close()
    await q.edit_message_text(f'✅ ВЫДАНО\n👤 {r["name"]}\n🍽 {r["meal_type"]}\n🕐 {now():%H:%M}' + ('\n⚠️ Дополнительный талон' if r['extra'] else ''))


async def qr_cmd(update,ctx):
    if role(update.effective_user.id)!='owner': return
    me=await ctx.bot.get_me(); url=f'https://t.me/{me.username}?start=meal'
    img=qrcode.make(url); bio=BytesIO(); img.save(bio,format='PNG'); bio.seek(0)
    await update.message.reply_photo(photo=bio,caption=f'🍽 QR-КОД СТОЛОВОЙ\n\n{url}\n\nРаспечатайте и разместите у входа/раздачи.')


async def reports(update,ctx):
    if role(update.effective_user.id)!='owner': return
    c=db(); d=now().date().isoformat(); rows=c.execute("SELECT meal_type,extra,COUNT(*) n FROM meals WHERE meal_date=? AND status IN ('served','requested') GROUP BY meal_type,extra",(d,)).fetchall(); c.close()
    lines=[f'📊 ПИТАНИЕ — {now():%d.%m.%Y}']; total=0; extra_count=0
    for r in rows:
        lines.append(f'{"🍲" if r["meal_type"]=="Обед" else "🍽"} {r["meal_type"]}: {r["n"]} (доп.: {r["n"] if r["extra"] else 0})'); total+=r['n']; extra_count+=r['n'] if r['extra'] else 0
    lines.append(f'\n🎫 Всего: {total}\n⚠️ Дополнительных: {extra_count}')
    if EXTRA_MEAL_COST: lines.append(f'💰 К удержанию: {extra_count*EXTRA_MEAL_COST:,} сум')
    await update.message.reply_text('\n'.join(lines))


async def extra_ticket(update,ctx):
    if role(update.effective_user.id)!='owner': return
    ctx.user_data['extra_state']='surname'; await update.message.reply_text('🎫 Дополнительный талон\n\nВведите фамилию сотрудника:')


async def text_router(update,ctx):
    t=(update.message.text or '').strip(); r=role(update.effective_user.id)
    if r=='owner' and ctx.user_data.get('extra_state'):
        st=ctx.user_data.get('extra_state')
        if st=='surname': ctx.user_data['extra_surname']=t; ctx.user_data['extra_state']='name'; await update.message.reply_text('Введите имя сотрудника:'); return
        if st=='name': ctx.user_data['extra_name']=t; ctx.user_data['extra_state']='meal'; await update.message.reply_text('Введите питание: Обед или Ужин'); return
        if st=='meal' and t.lower() in ('обед','ужин'):
            surname=ctx.user_data.pop('extra_surname',''); name=ctx.user_data.pop('extra_name',''); ctx.user_data.pop('extra_state',None); kind='Обед' if t.lower()=='обед' else 'Ужин'; full=f'{surname} {name}'.strip(); date=now().date().isoformat(); mid=f'manual:{update.effective_user.id}:{now().timestamp()}'
            c=db(); c.execute('INSERT INTO meals(dahua_id,name,meal_type,meal_date,requested_at,served_at,status,extra) VALUES(?,?,?,?,?,?,?,1)',(mid,full,kind,date,now().isoformat(),now().isoformat(),'served')); c.commit(); c.close()
            await update.message.reply_text(f'✅ Дополнительный талон создан\n👤 {full}\n🍽 {kind}\n⚠️ К расчёту удержания'); return
        await update.message.reply_text('Введите «Обед» или «Ужин».'); return
    if t=='🔐 Запросить доступ': return await access_request(update,ctx)
    if t in ('📊 Контроль','👥 Сейчас на работе','🍲 Обед сейчас','🍽 Ужин сейчас'): return await control(update,ctx)
    if t=='🍽 Столовая': return await canteen(update,ctx)
    if t=='🍽 Питание': return await meal(update,ctx)
    if t in ('👤 Мои записи','📋 Мой отчёт','📊 Сегодня'): return await today(update,ctx)
    if t=='📊 Отчёты': return await reports(update,ctx)
    if t=='📱 QR столовой': return await qr_cmd(update,ctx)
    if t=='🎫 Доп. талон': return await extra_ticket(update,ctx)
    if t=='➕ Добавить сотрудника': await update.message.reply_text('Введите имя сотрудника, затем зарегистрируйте его лицо на терминале Dahua. После первого прохода привяжите ID командой /link ID.'); return
    await update.message.reply_text('Используйте кнопки меню.')


async def poller():
    last=int((now()-timedelta(hours=24)).timestamp())
    while True:
        try:
            records=get_records(datetime.fromtimestamp(last-3,timezone.utc).astimezone(TZ),now()+timedelta(seconds=5)); n=import_records(records)
            if records:
                mx=last
                for x in records:
                    try: mx=max(mx,int(x.get('CreateTime','0')))
                    except Exception: pass
                last=max(last,mx)
            if n: log.info('Dahua: %s new records',n)
        except Exception as e: log.warning('Dahua poll failed: %s',e)
        await asyncio.sleep(POLL)


def main():
    if not BOT_TOKEN: raise RuntimeError('BOT_TOKEN is required')
    init_db(); requests.packages.urllib3.disable_warnings()
    async def post_init(application): application.create_task(poller())
    app=Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler('start',start)); app.add_handler(CommandHandler('link',link)); app.add_handler(CommandHandler('today',today)); app.add_handler(CommandHandler('control',control)); app.add_handler(CommandHandler('meal',meal)); app.add_handler(CommandHandler('canteen',canteen)); app.add_handler(CommandHandler('qr',qr_cmd)); app.add_handler(CommandHandler('report',reports))
    app.add_handler(CallbackQueryHandler(meal_callback,pattern=r'^meal:')); app.add_handler(CallbackQueryHandler(serve,pattern=r'^serve:')); app.add_handler(CallbackQueryHandler(access_callback,pattern=r'^access:'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_router))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=='__main__': main()
