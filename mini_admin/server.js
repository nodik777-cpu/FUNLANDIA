import postgres from "postgres";
import { createHmac, timingSafeEqual } from "node:crypto";

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

function validTelegramInitData(initData) {
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
  try {
    const user = JSON.parse(userRaw);
    if (String(user.id) !== ADMIN_CHAT_ID) return null;
    return user;
  } catch { return null; }
}
function json(data, status=200) {
  return new Response(JSON.stringify(data), {status, headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store","access-control-allow-origin":"*"}});
}
function html() {
  return new Response(Bun.file(new URL("./index.html", import.meta.url)), {headers:{"content-type":"text/html; charset=utf-8","cache-control":"no-store"}});
}
async function handler(req) {
  const url = new URL(req.url);
  if (url.pathname === "/health") return new Response("ok");
  if (url.pathname === "/" && req.method === "GET") return html();
  if (url.pathname === "/api/health" && req.method === "GET") return json({ok:true});
  if (!url.pathname.startsWith("/api/")) return new Response("Not found",{status:404});
  const user = validTelegramInitData(req.headers.get("x-telegram-init-data") || "");
  if (!user) return json({error:"Нет доступа. Откройте панель из Telegram под аккаунтом администратора."},401);
  try {
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
Bun.serve({port:PORT,fetch:handler});
console.log("FUNLANDIA_ADMIN_READY port="+PORT);
