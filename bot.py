import os
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
BOT_TOKEN=os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID=os.environ.get("ADMIN_CHAT_ID","")
ADMIN_PHONE="+998 93 381 00 55"
CALL_CENTER="555 127 337"
ADDRESS="Ташкент, ул. Тимур Малика, 3"
INSTAGRAM="https://www.instagram.com/funlandiauz/"
def menu(): return ReplyKeyboardMarkup([["🎟️ Цены","🎂 День рождения"],["🎠 Развлечения","📍 Адрес"],["🕐 Время работы","📞 Контакты"],["📸 Instagram","🇺🇿 O‘zbekcha"]],resize_keyboard=True)
async def start(update,context): await update.message.reply_text("🎉 ДОБРО ПОЖАЛОВАТЬ В FUNLANDIA! 🎉\n\nМесто, где дети играют, веселятся и получают яркие эмоции, а родители отдыхают! ❤️\n\n🛝 Лабиринты • 🤸 Батуты • 🎢 Горки • 🎯 Пневмопушки • 🧗 Тарзанка\n\nВыберите интересующий раздел ниже 👇",reply_markup=menu())
async def prices(update): await update.message.reply_text("🎟️ ЦЕНЫ FUNLANDIA\n\n🛝 ДЕТСКАЯ ЗОНА\n🏰 Лабиринты\n🎪 Надувные батуты\n🎢 Горки\n🎯 Пневмопушки\n\n💰 1 час — 80 000 сум\n💰 2 часа — 90 000 сум\n♾️ Безлимит — 100 000 сум\n\n👧👦 Детям от 1 года до 16 лет — вход платный.\n\n━━━━━━━━━━━━━━\n\n🤸 БАТУТНАЯ ЗОНА\n🤸 Профессиональные батуты\n🧗 Тарзанка\n🛝 17-метровая горка\n\n💰 1 час — 80 000 сум\n💰 2 часа — 90 000 сум\n♾️ Безлимит — 100 000 сум\n\n⚠️ На батутную зону допускаются дети от 7 лет и только под присмотром родителей или сопровождающего взрослого.\n\n━━━━━━━━━━━━━━\n\n🎉 ДВЕ ЗОНЫ — БОЛЬШЕ ВЕСЕЛЬЯ!\n🔥 Две зоны — 120 000 сум\n♾️ Безлимитное посещение обеих зон!\n\n🎊 ИГРАЙ • ВЕСЕЛИСЬ • ПОЛУЧАЙ ЭМОЦИИ В FUNLANDIA!",reply_markup=menu())
async def hours(update): await update.message.reply_text("🕐 ВРЕМЯ РАБОТЫ FUNLANDIA\n\n🎡 Работаем без выходных!\n\nВторник–воскресенье:\n🕙 10:00–22:00\n\nКаждый понедельник:\n🧹 Санитарный день — с 10:00 до 14:00\n🟢 Открытие для посетителей — с 14:00 до 22:00\n\n🧹 Каждый понедельник до 14:00 — санитарный день.\n🎉 Ждём вас с 14:00 до 22:00!",reply_markup=menu())
async def contacts(update):
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("👨‍💼 Позвонить администратору",url="tel:+998933810055")],[InlineKeyboardButton("☎️ Позвонить в колл-центр",url="tel:+998555127337")]])
    await update.message.reply_text(f"📞 КОНТАКТЫ FUNLANDIA\n\n👨‍💼 Администратор: {ADMIN_PHONE}\n☎️ Колл-центр: {CALL_CENTER}",reply_markup=kb)
async def address(update): await update.message.reply_text(f"📍 FUNLANDIA\n\n{ADDRESS}\n\nБудем рады видеть вас! 🎉",reply_markup=menu())
async def instagram(update): await update.message.reply_text(f"📸 Instagram FUNLANDIA\n\n{INSTAGRAM}",reply_markup=menu())
async def attractions(update): await update.message.reply_text("🎠 НАШИ РАЗВЛЕЧЕНИЯ\n\n🛝 4-этажные лабиринты\n🎪 Надувные батуты\n🤸 Профессиональные батуты\n🎢 Горки\n🛝 17-метровая горка\n🧗 Тарзанка\n🎯 Пневмопушки\n🧸 Зона для малышей\n🏖️ Кинетический песок\n🎠 Карусели",reply_markup=menu())
async def birthday(update,context):
    context.user_data["step"]=1; context.user_data["birthday"]={}
    await update.message.reply_text("🎂 ДЕНЬ РОЖДЕНИЯ В FUNLANDIA!\n\n🎁 АКЦИЯ ДЛЯ ИМЕНИННИКА\n\nПразднование проходит в одной выбранной зоне:\n🛝 Детская площадка\nили\n🤸 Батутная зона\n\n👧 5 детей — 450 000 сум\n👦 10 детей — 900 000 сум\n\n🍽️ ЗАКАЗ СТОЛА\n🪑 Стол на 3 часа — 200 000 сум\n➕ Дополнительное время — 50 000 сум за каждый час\n\n🪑 ВЫБОР ЗОНЫ ПОСАДКИ\n1️⃣ Зона 1\n2️⃣ Зона 2\n3️⃣ Зона 3\n\nНапишите имя именинника:")
async def birthday_form(update,context):
    s=context.user_data["step"]; v=update.message.text.strip(); d=context.user_data["birthday"]
    if s==1: d["name"]=v; context.user_data["step"]=2; await update.message.reply_text("📅 На какую дату планируете праздник?")
    elif s==2: d["date"]=v; context.user_data["step"]=3; await update.message.reply_text("👧👦 Сколько будет детей?")
    elif s==3: d["children"]=v; context.user_data["step"]=4; await update.message.reply_text("🕐 Какое время вас интересует?")
    elif s==4: d["time"]=v; context.user_data["step"]=5; await update.message.reply_text("📞 Оставьте номер телефона для связи.")
    elif s==5: d["phone"]=v; context.user_data["step"]=6; await update.message.reply_text("🪑 Выберите зону посадки: Зона 1, Зона 2 или Зона 3.")
    else:
        d["zone"]=v; u=update.effective_user.username or "нет username"; msg=f"🎂 НОВАЯ ЗАЯВКА FUNLANDIA\n\nИменинник: {d['name']}\nДата: {d['date']}\nДетей: {d['children']}\nВремя: {d['time']}\nТелефон: {d['phone']}\nЗона посадки: {d['zone']}\nTelegram: @{u}"
        if ADMIN_CHAT_ID:
            try: await context.bot.send_message(chat_id=ADMIN_CHAT_ID,text=msg)
            except Exception: pass
        context.user_data.clear(); await update.message.reply_text("✅ Заявка принята!\n\nАдминистратор FUNLANDIA свяжется с вами для подтверждения.",reply_markup=menu())
async def handler(update,context):
    if context.user_data.get("step"): return await birthday_form(update,context)
    t=update.message.text
    if t=="🎟️ Цены": return await prices(update)
    if t=="🎂 День рождения": return await birthday(update,context)
    if t=="🎠 Развлечения": return await attractions(update)
    if t=="📍 Адрес": return await address(update)
    if t=="🕐 Время работы": return await hours(update)
    if t=="📞 Контакты": return await contacts(update)
    if t=="📸 Instagram": return await instagram(update)
    if t=="🇺🇿 O‘zbekcha": return await update.message.reply_text("🇺🇿 O‘zbekcha menyu tez orada to‘liq qo‘shiladi.",reply_markup=menu())
    await update.message.reply_text("😊 Пожалуйста, выберите нужный раздел в меню.",reply_markup=menu())
def main():
    if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN is not set")
    app=Application.builder().token(BOT_TOKEN).build(); app.add_handler(CommandHandler("start",start)); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handler)); app.run_polling()
if __name__=="__main__": main()
