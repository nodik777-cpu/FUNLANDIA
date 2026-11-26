import postgres from "postgres";
import { createHmac, timingSafeEqual, randomBytes } from "node:crypto";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";

const PORT = Number(process.env.PORT || 8080);
const DATABASE_URL = process.env.DATABASE_URL;
const BOT_TOKEN = process.env.BOT_TOKEN;
const ADMIN_CHAT_ID = String(process.env.ADMIN_CHAT_ID || "");
if (!DATABASE_URL || !BOT_TOKEN || !ADMIN_CHAT_ID) {
  console.error("ADMIN_CONFIG_ERROR: DATABASE_URL, BOT_TOKEN and ADMIN_CHAT_ID are required");
  process.exit(1);
}
const sql = postgres(DATABASE_URL, { max: 5, connect_timeout: 10, idle_timeout: 20 });
const encoder = new TextEncoder();

function telegramUserFromInitData(initData) {
  if (!initData || initData.length > 8192) return null;
  const p = new URLSearchParams(initData);
  const hash = p.get("hash");
  const authDate = Number(p.get("auth_date"));
  const userRaw = p.get("user");
  if (!hash || !userRaw || !Number.isFinite(authDate)) return null;
  if (Math.abs(Date.now()/1000 - authDate) > 86400) return null;
  p.delete("hash");
  const dataCheck = [...p.entries()].sort(([a],[b]) => a.localeCompare(b)).map(([k,v]) => k+"="+v).join("\n");
  const secret = createHmac("sha256", "WebAppData").update(BOT_TOKEN).digest();
  const calculated = createHmac("sha256", secret).update(dataCheck).digest("hex");
  const a = Buffer.from(calculated, "hex"), b = Buffer.from(hash, "hex");
  if (a.length !== b.length || !timingSafeEqual(a,b)) return null;
  try { return JSON.parse(userRaw); } catch { return null; }
}
function validTelegramInitData(initData) {
  const user = telegramUserFromInitData(initData);
  return user && String(user.id) === ADMIN_CHAT_ID ? user : null;
}
function tashkentToday() {
  return new Intl.DateTimeFormat("en-CA", {timeZone:"Asia/Tashkent"}).format(new Date());
}
function validDate(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    !Number.isNaN(Date.parse(value + "T12:00:00+05:00")) &&
    new Date(value + "T12:00:00+05:00").toISOString().slice(0,10) === value;
}
function slotsForDate(date) {
  const weekday = new Date(date + "T12:00:00+05:00").getUTCDay();
  const firstHour = weekday === 1 ? 14 : 10;
  const slots = [];
  for (let minutes = firstHour * 60; minutes <= 18 * 60; minutes += 30) {
    slots.push(String(Math.floor(minutes / 60)).padStart(2,"0") + ":" +
      String(minutes % 60).padStart(2,"0"));
  }
  return slots;
}
async function telegramSend(chatId, text) {
  if (!chatId || !BOT_TOKEN) return;
  try {
    await fetch("https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage", {
      method:"POST", headers:{"content-type":"application/json"},
      body:JSON.stringify({chat_id:chatId,text})
    });
  } catch (e) {
    console.error("TELEGRAM_NOTIFY_ERROR", e?.message || e);
  }
}
async function publicBookingApi(req, url) {
  const tgUser = telegramUserFromInitData(req.headers.get("x-telegram-init-data") || "");
  if (!tgUser?.id) return json({error:"Откройте бронирование через Telegram-бот FUNLANDIA."},401);
  if (url.pathname === "/api/public/calendar" && req.method === "GET") {
    const month = url.searchParams.get("month") || "";
    const zone = Number(url.searchParams.get("zone") || 1);
    if (!/^\d{4}-\d{2}$/.test(month) || !Number.isInteger(zone) || zone < 1 || zone > 3)
      return json({error:"Некорректная дата или зона."},400);
    const [year, mon] = month.split("-").map(Number);
    const monthStart = new Date(month + "-01T00:00:00+05:00");
    const nextMonth = mon === 12 ? (year + 1) + "-01" : year + "-" + String(mon + 1).padStart(2,"0");
    const monthEnd = new Date(nextMonth + "-01T00:00:00+05:00");
    await sql`UPDATE birthday_bookings SET status='expired',updated_at=now()
      WHERE status='held' AND hold_expires_at IS NOT NULL AND hold_expires_at <= now()`;
    const rows = await sql`SELECT starts_at, ends_at FROM birthday_bookings
      WHERE zone_no=${zone}
        AND status IN ('held','awaiting_payment','awaiting_admin','confirmed')
        AND starts_at < ${monthEnd} AND ends_at > ${monthStart}`;
    const daysInMonth = new Date(Date.UTC(year, mon, 0)).getUTCDate();
    const today = tashkentToday();
    const days = [];
    for (let d=1; d<=daysInMonth; d++) {
      const date = month + "-" + String(d).padStart(2,"0");
      const slots = slotsForDate(date).map(time => {
        const start = new Date(date + "T" + time + ":00+05:00");
        const end = new Date(start.getTime() + 4*60*60*1000);
        const busy = rows.some(row => new Date(row.starts_at) < end && new Date(row.ends_at) > start);
        return {time, available: date >= today && start > new Date() && !busy, endsAt:end.toISOString()};
      });
      days.push({date, available:date >= today && slots.some(x=>x.available), slots});
    }
    return json({month,zone,days});
  }
  if (url.pathname === "/api/public/bookings" && req.method === "POST") {
    let body;
    try { body = await req.json(); } catch { return json({error:"Некорректные данные."},400); }
    const zone = Number(body.zone_no);
    const date = String(body.date || "");
    const time = String(body.time || "");
    const paymentMethod = String(body.payment_method || "");
    const allowed = validDate(date) && slotsForDate(date).includes(time) &&
      (paymentMethod === "payme" || paymentMethod === "click");
    const customer = String(body.customer_name || "").trim().slice(0,120);
    const child = String(body.child_name || "").trim().slice(0,120);
    const phone = String(body.phone || "").trim().slice(0,40);
    const age = body.child_age === "" || body.child_age == null ? null : Number(body.child_age);
    const children = Number(body.children_count);
    const adults = Number(body.adults_count || 0);
    const lang = ["ru","uz","en"].includes(body.language) ? body.language : "ru";
    if (!allowed || !Number.isInteger(zone) || zone < 1 || zone > 3 ||
        date < tashkentToday() || !customer || !child || !phone ||
        !Number.isInteger(children) || children < 1 || children > 60 ||
        !Number.isInteger(adults) || adults < 0 || adults > 60 ||
        (age !== null && (!Number.isInteger(age) || age < 0 || age > 18)))
      return json({error:"Проверьте дату, зону и заполнение обязательных полей."},400);
    const start = new Date(date + "T" + time + ":00+05:00");
    const end = new Date(start.getTime() + 4*60*60*1000);
    const code = "FL-" + date.replaceAll("-","").slice(2) + "-" + randomBytes(3).toString("hex").toUpperCase();
    try {
      await sql`UPDATE birthday_bookings SET status='expired',updated_at=now()
        WHERE status='held' AND hold_expires_at IS NOT NULL AND hold_expires_at <= now()`;
      const rows = await sql`INSERT INTO birthday_bookings
        (public_code, telegram_user_id, telegram_username, customer_name, child_name,
         child_age, phone, children_count, zone_no, starts_at, ends_at,
         party_minutes, cleanup_minutes, deposit_amount, status, extras, language,
         planned_ends_at, payment_method)
        VALUES (${code},${tgUser.id},${tgUser.username || null},${customer},${child},
         ${age},${phone},${children},${zone},${start},${end},
         180,60,100000,'held',${String(body.extras || "").slice(0,1000)},${lang},${end},${paymentMethod})
        RETURNING id,public_code,starts_at,ends_at,zone_no`;
      const b = rows[0];
      await sql`UPDATE birthday_bookings SET hold_expires_at=now()+interval '30 minutes',updated_at=now() WHERE id=${b.id}`;
      const message = "🎂 НОВАЯ ЗАЯВКА FUNLANDIA\n\nКод: " + b.public_code +
        "\nКлиент: " + customer + "\nИменинник: " + child + ", " + (age ?? "возраст не указан") +
        "\nТелефон: " + phone + "\nДата и время: " + date + " " + time +
        "\nЗона: №" + zone + "\nДетей: " + children + "\nВзрослых: " + adults +
        "\nАванс: 100 000 сум\nСпособ оплаты: " + (paymentMethod === "payme" ? "Payme" : "Click") +
        "\n\nСтатус: временная бронь на 30 минут, ожидает подтверждения администратора.";
      await telegramSend(ADMIN_CHAT_ID,message);
      return json({ok:true,booking:b,message:"Заявка отправлена администратору. Время удерживается 30 минут и будет подтверждено после проверки."},201);
    } catch (e) {
      if (e?.code === "23P01" || e?.code === "23505")
        return json({error:"Это время только что заняли. Выберите другой свободный слот."},409);
      console.error("PUBLIC_BOOKING_ERROR",e?.message || e);
      return json({error:"Не удалось создать заявку. Попробуйте ещё раз."},500);
    }
  }
  return json({error:"Not found"},404);
}
function json(data, status=200) {
  return new Response(JSON.stringify(data), {status, headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store","access-control-allow-origin":"*"}});
}
function html(file="index.html") {
  return new Response(readFileSync(new URL("./" + file, import.meta.url)), {headers:{"content-type":"text/html; charset=utf-8","cache-control":"no-store"}});
}
async function handler(req) {
  const url = new URL(req.url);
  if (url.pathname === "/health") return new Response("ok");
  if (url.pathname === "/ready") {
    try {
      const rows = await sql`SELECT to_regclass('public.birthday_requests') AS requests_table, to_regclass('public.birthday_bookings') AS bookings_table`;
      return rows[0]?.requests_table && rows[0]?.bookings_table ? new Response("ready") : new Response("schema missing", {status:503});
    } catch {
      return new Response("database unavailable", {status:503});
    }
  }
  if (url.pathname === "/" && req.method === "GET") return html("public.html");
  if (url.pathname === "/booking" && req.method === "GET") return html("booking.html");
  if (url.pathname === "/admin" && req.method === "GET") return html("index.html");
  if (url.pathname === "/api/health" && req.method === "GET") return json({ok:true});
  if (url.pathname.startsWith("/api/public/")) return publicBookingApi(req,url);
  if (!url.pathname.startsWith("/api/")) return new Response("Not found",{status:404});
  const user = validTelegramInitData(req.headers.get("x-telegram-init-data") || "");
  if (!user) return json({error:"Нет доступа. Откройте панель из Telegram под аккаунтом администратора."},401);
  try {
    if (url.pathname === "/api/bookings" && req.method === "GET") {
      const month = url.searchParams.get("month") || "";
      if (!/^\d{4}-\d{2}$/.test(month)) return json({error:"Укажите месяц в формате YYYY-MM."},400);
      const [year,mon] = month.split("-").map(Number);
      const nextMonth = mon === 12 ? (year+1)+"-01" : year+"-"+String(mon+1).padStart(2,"0");
      const from = new Date(month+"-01T00:00:00+05:00");
      const to = new Date(nextMonth+"-01T00:00:00+05:00");
      await sql`UPDATE birthday_bookings SET status='expired',updated_at=now()
        WHERE status='held' AND hold_expires_at IS NOT NULL AND hold_expires_at <= now()`;
      const rows = await sql`SELECT id,public_code,customer_name,child_name,child_age,phone,
        children_count,zone_no,starts_at,ends_at,planned_ends_at,released_at,status,deposit_amount,payment_method,created_at
        FROM birthday_bookings WHERE starts_at >= ${from} AND starts_at < ${to}
        ORDER BY starts_at,zone_no LIMIT 500`;
      return json(rows);
    }
    const bookingMatch = url.pathname.match(/^\/api\/bookings\/(\d+)$/);
    if (bookingMatch && req.method === "PATCH") {
      const body = await req.json();
      if (body.action === "extend") {
        const extraMinutes = Number(body.extra_minutes);
        if (!Number.isInteger(extraMinutes) || extraMinutes < 30 || extraMinutes > 240 || extraMinutes % 30 !== 0)
          return json({error:"Дополнительное время можно добавить от 30 до 240 минут с шагом 30 минут."},400);
        const current = await sql`SELECT id,zone_no,starts_at,ends_at,planned_ends_at,status
          FROM birthday_bookings WHERE id=${Number(bookingMatch[1])} FOR UPDATE`;
        if (!current.length || current[0].status !== "confirmed")
          return json({error:"Продлить можно только подтверждённую бронь."},409);
        const booking = current[0];
        const oldEnd = new Date(booking.ends_at);
        const newEnd = new Date(oldEnd.getTime() + extraMinutes*60*1000);
        const localEnd = new Date(newEnd.toLocaleString("en-US",{timeZone:"Asia/Tashkent"}));
        if (localEnd.getHours() > 22 || (localEnd.getHours() === 22 && (localEnd.getMinutes() > 0 || localEnd.getSeconds() > 0)))
          return json({error:"Продление выходит за время работы FUNLANDIA до 22:00."},409);
        const overlap = await sql`SELECT id FROM birthday_bookings
          WHERE zone_no=${booking.zone_no} AND id<>${booking.id}
            AND status IN ('held','awaiting_payment','awaiting_admin','confirmed')
            AND starts_at < ${newEnd} AND ends_at > ${oldEnd}
          LIMIT 1`;
        if (overlap.length) return json({error:"Нельзя продлить: после этого времени уже есть другая бронь."},409);
        const updated = await sql`UPDATE birthday_bookings
          SET ends_at=${newEnd},planned_ends_at=${newEnd},updated_at=now()
          WHERE id=${booking.id} AND status='confirmed'
          RETURNING id,public_code,zone_no,ends_at`;
        await sql`INSERT INTO birthday_admin_actions (booking_id,admin_telegram_id,action,note)
          VALUES (${booking.id},${user.id},'extend',${"Добавлено "+extraMinutes+" минут"})`;
        return json({ok:true,id:booking.id,status:"confirmed",ends_at:updated[0].ends_at});
      }
      if (body.status === "released") {
        const released = await sql`UPDATE birthday_bookings
          SET status='released',
              ends_at=LEAST(now(),COALESCE(planned_ends_at,ends_at)),
              released_at=now(),released_by=${user.id},updated_at=now()
          WHERE id=${Number(bookingMatch[1])} AND status='confirmed'
            AND starts_at < now() AND ends_at > now()
          RETURNING id,public_code,zone_no,starts_at,ends_at`;
        if (!released.length) return json({error:"Освободить можно только начавшуюся подтверждённую бронь, которая ещё занимает зону."},409);
        const b=released[0];
        await sql`INSERT INTO birthday_admin_actions (booking_id,admin_telegram_id,action,note)
          VALUES (${b.id},${user.id},'release',${String(body.note || "Зона освобождена администратором досрочно").slice(0,500)})`;
        return json({ok:true,id:b.id,status:"released",released_at:b.ends_at});
      }
      if (!["confirmed","rejected","cancelled"].includes(body.status))
        return json({error:"Недопустимый статус бронирования."},400);
      const bookingId = Number(bookingMatch[1]);
      await sql`UPDATE birthday_bookings SET status='expired',updated_at=now()
        WHERE id=${bookingId} AND status='held' AND hold_expires_at IS NOT NULL AND hold_expires_at <= now()`;
      const rows = await sql`UPDATE birthday_bookings SET status=${body.status},updated_at=now()
        WHERE id=${bookingId} AND status IN ('held','awaiting_admin','confirmed')
        RETURNING id,public_code,telegram_user_id,language,child_name,starts_at,zone_no,status`;
      if (!rows.length) return json({error:"Заявка не найдена или уже обрабатывается."},404);
      const booking = rows[0];
      await sql`INSERT INTO birthday_admin_actions (booking_id,admin_telegram_id,action,note)
        VALUES (${booking.id},${user.id},${body.status === "confirmed" ? "confirm" : body.status === "rejected" ? "reject" : "note"},${String(body.note || "").slice(0,500)})`;
      const dateText = new Date(booking.starts_at).toLocaleString("ru-RU",{timeZone:"Asia/Tashkent",dateStyle:"long",timeStyle:"short"});
      const messages = {
        ru: body.status === "confirmed"
          ? "✅ Ваша бронь FUNLANDIA "+booking.public_code+" подтверждена. "+dateText+", зона №"+booking.zone_no+". Администратор свяжется с вами по авансу 100 000 сум."
          : body.status === "rejected"
          ? "К сожалению, заявка FUNLANDIA "+booking.public_code+" отклонена. Пожалуйста, выберите другое время или свяжитесь с нами."
          : "Бронь FUNLANDIA "+booking.public_code+" отменена.",
        uz: body.status === "confirmed"
          ? "✅ FUNLANDIA "+booking.public_code+" broningiz tasdiqlandi. "+dateText+", "+booking.zone_no+"-zona. Administrator 100 000 so'm avans bo'yicha siz bilan bog'lanadi."
          : body.status === "rejected"
          ? "Afsuski, FUNLANDIA "+booking.public_code+" arizasi rad etildi. Iltimos, boshqa vaqtni tanlang yoki biz bilan bog'laning."
          : "FUNLANDIA "+booking.public_code+" broningiz bekor qilindi.",
        en: body.status === "confirmed"
          ? "✅ Your FUNLANDIA booking "+booking.public_code+" is confirmed. "+dateText+", Zone "+booking.zone_no+". The administrator will contact you about the 100,000 UZS deposit."
          : body.status === "rejected"
          ? "Unfortunately, your FUNLANDIA request "+booking.public_code+" was declined. Please choose another time or contact us."
          : "Your FUNLANDIA booking "+booking.public_code+" was cancelled."
      };
      await telegramSend(booking.telegram_user_id,messages[booking.language] || messages.ru);
      return json({ok:true,id:booking.id,status:booking.status});
    }
    if (url.pathname === "/api/summary" && req.method === "GET") {
      const [today] = await sql`SELECT count(*)::int AS count FROM birthday_requests WHERE created_at >= (date_trunc('day', now() AT TIME ZONE 'Asia/Tashkent') AT TIME ZONE 'Asia/Tashkent') AND created_at < ((date_trunc('day', now() AT TIME ZONE 'Asia/Tashkent') + interval '1 day') AT TIME ZONE 'Asia/Tashkent')`;
      const [all] = await sql`SELECT count(*)::int AS count FROM birthday_requests`;
      const [fresh] = await sql`SELECT count(*)::int AS count FROM birthday_requests WHERE status='new'`;
      const [confirmed] = await sql`SELECT count(*)::int AS count FROM birthday_requests WHERE status='confirmed'`;
      return json({today:today.count,total:all.count,new:fresh.count,confirmed:confirmed.count});
    }
    if (url.pathname === "/api/requests" && req.method === "GET") {
      const filter = url.searchParams.get("filter") || "all";
      const rows = filter === "today"
        ? await sql`SELECT id, customer_name, child_name, requested_date, phone, status, created_at FROM birthday_requests WHERE created_at >= (date_trunc('day', now() AT TIME ZONE 'Asia/Tashkent') AT TIME ZONE 'Asia/Tashkent') AND created_at < ((date_trunc('day', now() AT TIME ZONE 'Asia/Tashkent') + interval '1 day') AT TIME ZONE 'Asia/Tashkent') ORDER BY created_at DESC LIMIT 100`
        : filter === "new"
        ? await sql`SELECT id, customer_name, child_name, requested_date, phone, status, created_at FROM birthday_requests WHERE status='new' ORDER BY created_at DESC LIMIT 100`
        : await sql`SELECT id, customer_name, child_name, requested_date, phone, status, created_at FROM birthday_requests ORDER BY created_at DESC LIMIT 100`;
      return json(rows);
    }
    const match = url.pathname.match(/^\/api\/requests\/(\d+)$/);
    if (match && req.method === "GET") {
      const rows = await sql`SELECT * FROM birthday_requests WHERE id=${Number(match[1])} LIMIT 1`;
      return rows.length ? json(rows[0]) : json({error:"Заявка не найдена"},404);
    }
    if (match && req.method === "PATCH") {
      const body = await req.json();
      if (!["confirmed","rejected","new"].includes(body.status)) return json({error:"Недопустимый статус"},400);
      const rows = await sql`UPDATE birthday_requests SET status=${body.status} WHERE id=${Number(match[1])} RETURNING id,status,child_name`;
      return rows.length ? json(rows[0]) : json({error:"Заявка не найдена"},404);
    }
    return json({error:"Not found"},404);
  } catch (e) {
    console.error("ADMIN_API_ERROR", e?.message || e);
    return json({error:"Ошибка базы данных"},500);
  }
}
const server = createServer(async (req, res) => {
  try {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks);
    const request = new Request("http://127.0.0.1" + (req.url || "/"), {
      method: req.method,
      headers: req.headers,
      body: ["GET","HEAD"].includes(req.method || "GET") ? undefined : body
    });
    const response = await handler(request);
    res.writeHead(response.status, Object.fromEntries(response.headers.entries()));
    res.end(Buffer.from(await response.arrayBuffer()));
  } catch (e) {
    console.error("HTTP_SERVER_ERROR", e?.message || e);
    res.writeHead(500); res.end("Internal Server Error");
  }
});
server.listen(PORT, "0.0.0.0", async () => {
  try {
    await sql`SELECT 1`;
    const schema = readFileSync(new URL("./booking_schema.sql", import.meta.url), "utf8");
    await sql.unsafe(schema);
    const rows = await sql`SELECT to_regclass('public.birthday_requests') AS requests_table, to_regclass('public.birthday_bookings') AS bookings_table`;
    console.log("FUNLANDIA_ADMIN_READY port=" + PORT + " database=" +
      (rows[0]?.requests_table && rows[0]?.bookings_table ? "connected" : "schema_missing"));
  } catch (e) {
    console.error("FUNLANDIA_ADMIN_DATABASE_STARTUP_ERROR", e?.message || e);
  }
});
