import os, json, time
from pathlib import Path
from datetime import datetime
import requests
from dotenv import load_dotenv
import qrcode

load_dotenv()
BASE=Path(__file__).resolve().parent
DB=BASE/"staff_data.json"
QR=BASE/"FUNLANDIA_MEAL_QR.png"
TOKEN=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
HOST=os.getenv("DAHUA_HOST","192.168.1.202").strip()
USER=os.getenv("DAHUA_USER","admin").strip()
PASS=os.getenv("DAHUA_PASSWORD","").strip()
VERIFY=os.getenv("DAHUA_VERIFY_SSL","false").lower()=="true"
ADMINS={int(x) for x in os.getenv("ADMIN_CHAT_IDS","").split(",") if x.strip().isdigit()}
CAFETERIA={int(x) for x in os.getenv("CAFETERIA_CHAT_IDS","").split(",") if x.strip().isdigit()}
EXTRA_LUNCH=int(os.getenv("EXTRA_LUNCH_PRICE","0") or 0)
if not TOKEN: raise SystemExit("TELEGRAM_BOT_TOKEN не задан")
if not PASS: raise SystemExit("DAHUA_PASSWORD не задан")
TG=f"https://api.telegram.org/bot{TOKEN}"; DAHUA=f"https://{HOST}"
AUTH=requests.auth.HTTPDigestAuth(USER,PASS)
VERIFY_SSL=VERIFY
PENDING={}

def load():
    if DB.exists():
        try: return json.loads(DB.read_text(encoding="utf-8"))
        except: pass
    return {"bindings":{},"meals":[],"fired":{}}
D=load()
def save(): DB.write_text(json.dumps(D,ensure_ascii=False,indent=2),encoding="utf-8")
def tg(method,data=None):
    r=requests.post(f"{TG}/{method}",json=data or {},timeout=30); r.raise_for_status()
    j=r.json()
    if not j.get("ok"): raise RuntimeError(j)
    return j["result"]
def send(cid,text,kb=None):
    d={"chat_id":cid,"text":text}
    if kb: d["reply_markup"]={"keyboard":kb,"resize_keyboard":True}
    return tg("sendMessage",d)
def photo(cid,path,caption=""):
    with open(path,"rb") as f: return requests.post(f"{TG}/sendPhoto",data={"chat_id":cid,"caption":caption},files={"photo":f},timeout=30)
def menu():
    return [["📋 Проходы","⏰ Кто опоздал"],["👥 Сотрудники","📊 Отчёты"],["🍽 Питание","📷 QR столовой"],["🔄 Обновить","⚙️ Настройки"]]
def admin_menu():
    return menu()+[["❌ Уволить","🔗 Привязать Telegram"]]
def admin(cid): return cid in ADMINS
def parse(s):
    d={}
    for line in s.splitlines():
        if not line.startswith("records[") or "=" not in line: continue
        try:
            a,v=line.split("=",1); i=a.split("].",1)[0].split("[")[1]; f=a.split("].",1)[1]
            d.setdefault(i,{})[f]=v
        except: pass
    return [d[k] for k in sorted(d,key=lambda x:int(x))]
def records():
    st=int(datetime.now().replace(hour=0,minute=0,second=0,microsecond=0).timestamp()); en=int(time.time())
    out=[]; off=0
    while True:
        r=requests.get(f"{DAHUA}/cgi-bin/recordFinder.cgi",params={"action":"find","name":"AccessControlCardRec","StartTime":st,"EndTime":en,"offset":off,"count":500},auth=AUTH,verify=VERIFY_SSL,timeout=30)
        r.raise_for_status(); b=parse(r.text); out+=b
        found=0
        for x in r.text.splitlines():
            if x.startswith("found="):
                try: found=int(x.split("=",1)[1])
                except: pass
        if len(b)<500 or found<500: break
        off+=500
        if off>10000: break
    return out
def users():
    r=requests.get(f"{DAHUA}/cgi-bin/recordFinder.cgi",params={"action":"find","name":"AccessControlCard","offset":0,"count":500},auth=AUTH,verify=VERIFY_SSL,timeout=30)
    r.raise_for_status(); return parse(r.text)
def name_of(uid,us=None):
    for u in (us if us is not None else users()):
        if str(u.get("UserID",""))==str(uid): return u.get("CardName") or str(uid)
def events(rs):
    out=[]
    for r in rs:
        try: dt=datetime.fromtimestamp(int(r["CreateTime"]))
        except: continue
        typ=(r.get("Type") or "").lower()
        if typ not in ("entry","exit"): continue
        out.append((dt,typ,r))
    return sorted(out)
def summary(rs):
    ev=events(rs); first=next((x[0] for x in ev if x[1]=="entry"),None); ex=[x[0] for x in ev if x[1]=="exit"]
    last=ex[-1] if ex else None
    if not first: return None
    hm=first.strftime("%H:%M")
    if "09:55"<=hm<="10:15" and last and last.strftime("%H:%M")>="21:30": shift="Полная смена"; nin="10:00"; nout="22:00"
    elif "08:00"<=hm<="10:00": shift="1-я смена"; nin="10:00"; nout="20:00"
    else: shift="2-я смена"; nin="13:00"; nout="22:00"
    base=first.replace(hour=int(nin[:2]),minute=int(nin[3:]),second=0,microsecond=0)
    end=first.replace(hour=int(nout[:2]),minute=int(nout[3:]),second=0,microsecond=0)
    late=max(0,int((first-base).total_seconds()//60))
    early=max(0,int((end-last).total_seconds()//60)) if last and last<end else 0
    return {"shift":shift,"first":first,"last":last,"late":late,"early":early,"events":ev}
def bound(cid): return D["bindings"].get(str(cid))
def today(uid): return [r for r in records() if str(r.get("UserID",""))==str(uid)]
def meal_status(cid):
    b=bound(cid)
    if not b: return None,"Telegram не привязан к сотруднику Face ID."
    uid=str(b["user_id"])
    if uid in D["fired"]: return None,"Доступ закрыт: сотрудник уволен."
    rs=today(uid); s=summary(rs)
    if not s: return None,"Сегодня проход сотрудника не найден."
    if not s["events"] or s["events"][-1][1]!="entry": return None,"По журналу Dahua сотрудник сейчас не находится на объекте."
    date=datetime.now().strftime("%Y-%m-%d")
    used=[x for x in D["meals"] if x["chat_id"]==cid and x["date"]==date]
    return (b,s,used),None
def meal_kb(s,used):
    u={x["meal"] for x in used}; rows=[]
    if s["shift"] in ("1-я смена","Полная смена") and "Обед" not in u: rows.append(["🍲 Обед"])
    if "Ужин" not in u: rows.append(["🍽 Ужин"])
    if s["shift"]=="2-я смена" and "Обед за свой счёт" not in u: rows.append(["🍲 Обед за свой счёт"])
    rows.append(["⬅️ Главное меню"]); return rows
def issue(cid,meal):
    st,err=meal_status(cid)
    if err: send(cid,"❌ "+err,menu()); return
    b,s,used=st; date=datetime.now().strftime("%Y-%m-%d")
    if any(x["date"]==date and x["chat_id"]==cid and x["meal"]==meal for x in used):
        send(cid,"⚠️ Это питание уже подтверждено сегодня.",meal_kb(s,used)); return
    if meal=="Обед" and s["shift"]=="2-я смена":
        send(cid,"Для 2-й смены обед оформляется как «Обед за свой счёт».",meal_kb(s,used)); return
    rec={"date":date,"time":datetime.now().strftime("%H:%M:%S"),"chat_id":cid,"user_id":b["user_id"],"name":b["name"],"shift":s["shift"],"meal":meal,"self_paid":meal=="Обед за свой счёт","price":EXTRA_LUNCH if meal=="Обед за свой счёт" else 0}
    D["meals"].append(rec); save()
    send(cid,f"✅ Питание подтверждено\n\n{b['name']}\nСмена: {s['shift']}\n{meal}\nВремя: {rec['time']}",menu())
    note=f"🍽 ПИТАНИЕ ВЫДАНО\n\n{b['name']}\nUserID: {b['user_id']}\nСмена: {s['shift']}\n{meal}\nВремя: {rec['time']}"
    for target in ADMINS|CAFETERIA:
        try: send(target,note,admin_menu() if target in ADMINS else None)
        except Exception as e: print("notify:",e)
def make_qr():
    u=tg("getMe").get("username")
    if not u: raise RuntimeError("У бота нет username")
    link=f"https://t.me/{u}?start=meal"; qrcode.make(link).save(QR); return link
def fire(uid,cid):
    us=users(); name=name_of(uid,us)
    if not name: send(cid,f"❌ UserID {uid} не найден в Dahua.",admin_menu()); return
    r=requests.get(f"{DAHUA}/cgi-bin/Attendance.cgi",params={"action":"deleteUser","UserID":uid},auth=AUTH,verify=VERIFY_SSL,timeout=30)
    ok=r.status_code==200 and r.text.strip().upper()=="OK"
    if not ok: send(cid,f"❌ Dahua не подтвердил удаление UserID {uid}.",admin_menu()); return
    check=requests.get(f"{DAHUA}/cgi-bin/Attendance.cgi",params={"action":"getUser","UserID":uid},auth=AUTH,verify=VERIFY_SSL,timeout=20)
    D["fired"][uid]={"name":name,"fired_at":datetime.now().isoformat(timespec="seconds")}
    for k,v in list(D["bindings"].items()):
        if str(v.get("user_id"))==uid: D["bindings"].pop(k)
    save()
    send(cid,f"✅ Сотрудник уволен\n\n{name}\nUserID: {uid}\n\nДоступ удалён из Dahua. История проходов и питания сохранена.\nПроверка удаления: HTTP {check.status_code}",admin_menu())
def handle(cid,text):
    print(f"Telegram message: chat={cid} text={text}")
    if text.startswith("/id"): send(cid,f"Ваш Telegram chat ID: {cid}",menu()); return
    if text.startswith("/start"):
        if "meal" in text.lower():
            st,err=meal_status(cid)
            if err: send(cid,"🍽 ПИТАНИЕ\n\n❌ "+err,menu())
            else:
                b,s,used=st; send(cid,f"🍽 ПИТАНИЕ\n\n{b['name']}\nСмена: {s['shift']}\nПервый вход: {s['first'].strftime('%H:%M')}\n\nВыберите питание:",meal_kb(s,used))
            return
        send(cid,"👋 FUNLANDIA — система сотрудников\n\nВыберите раздел:",admin_menu() if admin(cid) else menu()); return
    if cid in PENDING:
        action=PENDING.pop(cid)
        if not admin(cid): send(cid,"Нет прав.",menu()); return
        if action=="fire": fire(text.strip(),cid); return
        if action=="bind":
            uid=text.strip(); n=name_of(uid)
            if not n: send(cid,f"❌ UserID {uid} не найден в Dahua.",admin_menu()); return
            D["bindings"][str(cid)]={"user_id":uid,"name":n}; D["fired"].pop(uid,None); save()
            send(cid,f"✅ Telegram привязан к\n{n}\nUserID: {uid}",admin_menu()); return
    if text=="❌ Уволить":
        if not admin(cid): send(cid,"Нет прав.",menu()); return
        PENDING[cid]="fire"; send(cid,"❌ УВОЛИТЬ\n\nВведите UserID сотрудника из Dahua:",admin_menu()); return
    if text=="🔗 Привязать Telegram":
        if not admin(cid): send(cid,"Нет прав.",menu()); return
        PENDING[cid]="bind"; send(cid,"🔗 ПРИВЯЗАТЬ TELEGRAM\n\nВведите UserID сотрудника из Dahua:",admin_menu()); return
    if text=="🍽 Питание":
        st,err=meal_status(cid)
        if err: send(cid,"🍽 ПИТАНИЕ\n\n❌ "+err,menu()); return
        b,s,used=st; send(cid,f"🍽 ПИТАНИЕ\n\n{b['name']}\nСмена: {s['shift']}\nПервый вход: {s['first'].strftime('%H:%M')}\n\nВыберите питание:",meal_kb(s,used)); return
    if text in ("🍲 Обед","🍽 Ужин","🍲 Обед за свой счёт"): issue(cid,text); return
    if text=="⬅️ Главное меню": send(cid,"Главное меню:",admin_menu() if admin(cid) else menu()); return
    if text=="📷 QR столовой":
        if not admin(cid): send(cid,"Раздел доступен администратратору.",menu()); return
        try:
            link=make_qr(); photo(cid,QR,"FUNLANDIA — QR столовой\nРаспечатайте и разместите возле столовой."); send(cid,f"📷 QR готов.\n{link}\nФайл: {QR}",admin_menu())
        except Exception as e: send(cid,f"❌ QR: {e}",admin_menu())
        return
    if text=="📋 Проходы":
        rs=records(); rs.sort(key=lambda x:int(x.get("CreateTime","0"))); lines=["📋 ПРОХОДЫ СЕГОДНЯ",""]
        for r in rs[-40:]:
            try: tm=datetime.fromtimestamp(int(r["CreateTime"])).strftime("%H:%M:%S")
            except: tm="--:--:--"
            lines.append(f"{tm} — {r.get('CardName') or r.get('UserID','?')} — {r.get('Type','')}")
        send(cid,"\n".join(lines),menu()); return
    if text=="⏰ Кто опоздал":
        rs=records(); by={}
        for r in rs: by.setdefault(str(r.get("UserID","")),[]).append(r)
        lines=["⏰ ОПОЗДАНИЯ И РАННИЙ УХОД",""]; n=0
        for uid,rr in by.items():
            s=summary(rr)
            if not s: continue
            if s["late"] or s["early"]:
                n+=1; nm=name_of(uid)
                lines.append(f"{nm} — {s['shift']}\nВход: {s['first'].strftime('%H:%M')} — опоздание {s['late']} мин.\nВыход: {s['last'].strftime('%H:%M') if s['last'] else 'на работе'} — ранний уход {s['early']} мин.\n")
        if not n: lines.append("Сегодня нарушений по имеющимся данным нет.")
        send(cid,"\n".join(lines),menu()); return
    if text=="👥 Сотрудники":
        us=users(); lines=["👥 СОТРУДНИКИ",""]
        for u in sorted(us,key=lambda x:(x.get("CardName") or "").lower()):
            uid=u.get("UserID",""); lines.append(f"{u.get('CardName') or uid} | ID {uid} | {'УВОЛЕН' if uid in D['fired'] else 'активен'}")
        if admin(cid): lines+=["","❌ Уволить — кнопка ниже","🔗 Привязать Telegram — кнопка ниже"]
        send(cid,"\n".join(lines),admin_menu() if admin(cid) else menu()); return
    if text=="📊 Отчёты":
        day=datetime.now().strftime("%Y-%m-%d"); m=[x for x in D["meals"] if x["date"]==day]; extra=sum(x["price"] for x in m if x["self_paid"])
        send(cid,f"📊 ОТЧЁТЫ\n\nПитание сегодня: {len(m)}\nДоп. обеды: {sum(1 for x in m if x['self_paid'])}\nК удержанию: {extra:,} сум",admin_menu() if admin(cid) else menu()); return
    if text=="🔄 Обновить": send(cid,"🔄 Данные обновляются напрямую из Dahua.",admin_menu() if admin(cid) else menu()); return
    if text=="⚙️ Настройки":
        send(cid,f"⚙️ НАСТРОЙКИ\n\nDahua: {HOST}\nРабочий день: 10:00–22:00\n1-я смена: 10:00–20:00\n2-я смена: 13:00–22:00\nПолная смена: 10:00–22:00",admin_menu() if admin(cid) else menu()); return
    send(cid,"Используйте кнопки меню.",admin_menu() if admin(cid) else menu())
def main():
    print("================================"); print("FUNLANDIA STAFF BOT"); print("Telegram + Dahua CGI"); print("================================")
    off=0
    while True:
        try:
            for u in tg("getUpdates",{"timeout":30,"offset":off}):
                off=u["update_id"]+1; m=u.get("message")
                if m: handle(m["chat"]["id"],(m.get("text") or "").strip())
        except KeyboardInterrupt: print("\nSTOP"); break
        except Exception as e: print("ERROR:",e); time.sleep(5)
if __name__=="__main__": main()
