
import json, asyncio, logging, base64, io
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from PIL import Image, ImageDraw, ImageFont
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler,
    filters, ContextTypes
)
import os

from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
HF_TOKEN  = os.getenv('HF_TOKEN')  

USERS_FILE = "users.json"
TZ = ZoneInfo("Asia/Tashkent")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
log = logging.getLogger("planner")

# ─── ONBOARDING STATES ─────────────────────────
(
    S_STATUS, S_WORK, S_CLASS,
    S_HEIGHT, S_AGE, S_WEIGHT,
    S_GOAL, S_BUDGET,
    S_ALLERGY_Q, S_ALLERGY_TXT,
) = range(10)


# ═══════════════════════════════════════════════
#  USER DATABASE (JSON fayl)
#  Har bir user chat_id bo'yicha saqlanadi.
#  CHAT_ID hardcode emas — har kim o'z datasi.
# ═══════════════════════════════════════════════
def _load() -> dict:
    if Path(USERS_FILE).exists():
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save(data: dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(chat_id) -> dict:
    return _load().get(str(chat_id), {})

def patch_user(chat_id, fields: dict):
    db = _load()
    db.setdefault(str(chat_id), {}).update(fields)
    _save(db)

def clear_user(chat_id):
    db = _load()
    uid = str(chat_id)
    # faqat ismni saqla, qolganini o'chir
    kept = {k: v for k, v in db.get(uid, {}).items()
            if k in ("first_name", "username", "chat_id")}
    db[uid] = kept
    _save(db)


# ═══════════════════════════════════════════════
#  HUGGINGFACE ROUTER API  (bepul, ishlaydi)
#  Model: DeepSeek-V3.2 via Novita
# ═══════════════════════════════════════════════
HF_URL   = "https://router.huggingface.co/v1/chat/completions"
HF_MODEL = "deepseek-ai/DeepSeek-V3-0324:novita"

def _hf_headers():
    return {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
    }

async def groq_text(messages: list, model=None, max_tokens=4000) -> str:
    """HuggingFace Router orqali matn generatsiya."""
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            HF_URL,
            headers=_hf_headers(),
            json={
                "model": HF_MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.7,
            }
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

async def groq_vision(img_bytes: bytes, prompt: str) -> str:
    """Rasm + matn → HuggingFace Router (DeepSeek vision)."""
    b64 = base64.b64encode(img_bytes).decode()
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            HF_URL,
            headers=_hf_headers(),
            json={
                "model": HF_MODEL,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": prompt}
                    ]
                }],
                "max_tokens": 1000,
            }
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════
#  AI HAFTALIK TARTIB GENERATORI
# ═══════════════════════════════════════════════
async def make_plan(user: dict) -> dict:
    status = user.get("status", "studying")
    if status == "working":
        sched_line = f"Ish vaqti: {user.get('work_schedule', '?')}"
    elif status == "studying":
        sched_line = f"Dars jadvali: {user.get('class_schedule', '?')}"
    else:
        sched_line = (f"Dars jadvali: {user.get('class_schedule', '?')}, "
                      f"Ish vaqti: {user.get('work_schedule', '?')}")

    prompt = f"""Sen o'zbek tilida ishlaydi student hayot rejalashtiruvchi AI assistantsan.
Quyidagi foydalanuvchi ma'lumotlariga asosida 1 haftalik mukammal kunlik tartib tuz.

FOYDALANUVCHI MA'LUMOTLARI:
- Holat: {status}
- {sched_line}
- Bo'yi: {user.get('height', '?')} sm
- Yoshi: {user.get('age', '?')} yosh
- Vazni: {user.get('weight', '?')} kg
- Maqsad: {user.get('goal', '?')}
- Haftalik byudjet: {user.get('budget', '?')}
- Allergiya / yeya olmaydigan: {user.get('allergies', "yo'q")}

FAQAT quyidagi JSON formatida qaytar. Markdown, izoh, boshqa hech narsa yozma:

{{
  "reminder_times": {{
    "wake_up": "07:00",
    "sleep": "23:00"
  }},
  "days": {{
    "Dushanba": {{
      "schedule": [
        {{"time":"07:00","emoji":"⏰","activity":"Uyg'onish","duration_min":15}},
        {{"time":"07:15","emoji":"🏃","activity":"Ertalabki mashq","duration_min":20}},
        {{"time":"07:35","emoji":"🍳","activity":"Nonushta tayyorlash","duration_min":20}},
        {{"time":"07:55","emoji":"🍽️","activity":"Nonushta","duration_min":15}},
        {{"time":"08:10","emoji":"📚","activity":"O'qish bloki","duration_min":90}},
        {{"time":"12:00","emoji":"💼","activity":"Dars/Ish","duration_min":240}},
        {{"time":"16:00","emoji":"🍜","activity":"Tushlik","duration_min":40}},
        {{"time":"17:00","emoji":"📖","activity":"Mustaqil o'qish","duration_min":90}},
        {{"time":"19:30","emoji":"🍽️","activity":"Kechki ovqat","duration_min":30}},
        {{"time":"20:00","emoji":"😎","activity":"Dam olish","duration_min":90}},
        {{"time":"22:00","emoji":"🌙","activity":"Uxlashga tayyorlik","duration_min":30}},
        {{"time":"22:30","emoji":"💤","activity":"Uyqu","duration_min":480}}
      ],
      "meals": {{
        "breakfast": {{"name":"Tuxum qovurma","time":"07:55","kcal":320,"ingredients":["2 tuxum","yog'","tuz"]}},
        "lunch":     {{"name":"Guruch oshi","time":"16:00","kcal":550,"ingredients":["guruch","sabzi","piyoz"]}},
        "dinner":    {{"name":"Makaron","time":"19:30","kcal":480,"ingredients":["makaron","sariyog'"]}}
      }},
      "motivation": "Haftaning boshi — kuchli boshlang!",
      "tip": "Eng muhim vazifani tongda bajaring."
    }},
    "Seshanba": {{ /* xuddi shunday to'liq to'ldir */ }},
    "Chorshanba": {{ /* ... */ }},
    "Payshanba": {{ /* ... */ }},
    "Juma":      {{ /* ... */ }},
    "Shanba":    {{ /* ... */ }},
    "Yakshanba": {{ /* ... */ }}
  }},
  "weekly_shopping": {{
    "items": [
      {{"name":"Tuxum","amount":"30 dona","price_sum":25000}},
      {{"name":"Guruch","amount":"2 kg","price_sum":14000}}
    ],
    "total_sum": 107000
  }}
}}

Barcha 7 kunni to'liq to'ldir. Allergiyasiz mahsulotlar ishlat. Byudjetga mos ovqatlar tuz."""

    raw = (await groq_text([{"role": "user", "content": prompt}])).strip()
    # markdown fence ni tozala
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip()
    return json.loads(raw)


# ═══════════════════════════════════════════════
#  RASM GENERATORI (Pillow)
# ═══════════════════════════════════════════════
def _font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def build_image(day_name: str, day_data: dict, first_name: str) -> io.BytesIO:
    W, H = 800, 1080
    BG   = "#0d0d1a"; CARD = "#16162a"
    PUR  = "#8b5cf6"; GOLD = "#f59e0b"
    GRN  = "#10b981"; WHT  = "#f1f5f9"; GRY = "#64748b"

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Header gradient
    for i in range(90):
        v = int(40 + 160 * (1 - i / 90))
        draw.rectangle([0, i, W, i + 1], fill=(v // 3, 0, v))

    f_xl = _font(BOLD, 30);  f_lg = _font(BOLD, 22)
    f_md = _font(BOLD, 18);  f_sm = _font(REG,  16)
    f_xs = _font(REG,  13)

    draw.text((W // 2, 28), f"📅  {day_name}",          font=f_xl, fill=WHT,  anchor="mm")
    draw.text((W // 2, 65), f"Salom, {first_name}! Bugungi tartibingiz", font=f_sm, fill=GOLD, anchor="mm")

    y = 98

    # ── JADVAL ───────────────────────────────
    draw.text((24, y), "⏱  KUNLIK JADVAL", font=f_lg, fill=GOLD)
    y += 32
    for item in day_data.get("schedule", [])[:10]:
        draw.rounded_rectangle([14, y, W - 14, y + 34], radius=6, fill=CARD, outline=PUR, width=1)
        draw.text((26, y + 9), item.get("emoji", "•"),           font=f_sm, fill=GOLD)
        draw.text((52, y + 9), item.get("time", ""),             font=f_sm, fill=GRN)
        draw.text((108, y + 9), item.get("activity", ""),        font=f_sm, fill=WHT)
        dur = item.get("duration_min")
        if dur:
            draw.text((W - 75, y + 9), f"{dur} min",             font=f_xs, fill=GRY)
        y += 40
    y += 8

    # ── OVQATLAR ─────────────────────────────
    draw.text((24, y), "🍽  OVQATLAR", font=f_lg, fill=GRN)
    y += 32
    for key, label, icon in [
        ("breakfast", "Nonushta", "🌅"),
        ("lunch",     "Tushlik",  "☀️"),
        ("dinner",    "Kechki",   "🌙"),
    ]:
        m = day_data.get("meals", {}).get(key)
        if not m:
            continue
        draw.rounded_rectangle([14, y, W - 14, y + 56], radius=6, fill="#0e2a1a", outline=GRN, width=1)
        draw.text((26, y + 8),  f"{icon} {label} ({m.get('time', '?')})", font=f_sm, fill=GRN)
        draw.text((26, y + 30), f"   {m.get('name', '')}",                 font=f_md, fill=WHT)
        kcal = m.get("kcal")
        if kcal:
            draw.text((W - 90, y + 30), f"{kcal} kkal",                    font=f_xs, fill=GRY)
        y += 62
    y += 8

    # ── MOTIVATSIYA ───────────────────────────
    mot = day_data.get("motivation", "")
    tip = day_data.get("tip", "")
    if mot:
        draw.rounded_rectangle([14, y, W - 14, y + 42], radius=6, fill="#1a0d30", outline=PUR, width=1)
        draw.text((26, y + 13), f"💪  {mot}", font=f_sm, fill=WHT)
        y += 48
    if tip:
        draw.rounded_rectangle([14, y, W - 14, y + 42], radius=6, fill="#1a1500", outline=GOLD, width=1)
        draw.text((26, y + 13), f"💡  {tip}", font=f_sm, fill=GOLD)

    draw.text((W // 2, H - 18), "🤖 By Shakhzod, font=f_xs, fill=GRY, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


# ═══════════════════════════════════════════════
#  SCHEDULER — har user uchun alohida
# ═══════════════════════════════════════════════
UZ_DAYS = ["Dushanba","Seshanba","Chorshanba","Payshanba","Juma","Shanba","Yakshanba"]

def today_uz() -> str:
    return UZ_DAYS[datetime.now(TZ).weekday()]

async def send_reminder(app: Application, chat_id: int):
    try:
        user = get_user(chat_id)
        plan = user.get("weekly_plan")
        if not plan:
            return
        day   = today_uz()
        ddata = plan["days"].get(day)
        if not ddata:
            return
        name  = user.get("first_name", "Do'stim")
        buf   = build_image(day, ddata, name)
        meals = ddata.get("meals", {})
        cap   = f"☀️ *Xayrli tong, {name}!*\n\n📅 Bugun: *{day}*\n\n🍽 *Bugungi ovqatlar:*\n"
        for k, lbl in [("breakfast","Nonushta"),("lunch","Tushlik"),("dinner","Kechki")]:
            if k in meals:
                cap += f"• {lbl} ({meals[k].get('time','?')}): {meals[k].get('name','')}\n"
        cap += f"\n💪 _{ddata.get('motivation', '')}_"
        await app.bot.send_photo(chat_id=chat_id, photo=buf, caption=cap, parse_mode="Markdown")
    except Exception as e:
        log.error(f"Reminder error {chat_id}: {e}")

def register_reminder(scheduler: AsyncIOScheduler, app: Application,
                      chat_id: int, wake_up: str = "07:30"):
    job_id = f"rem_{chat_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    h, m = map(int, wake_up.split(":"))
    m -= 5
    if m < 0:
        m += 60; h = (h - 1) % 24
    scheduler.add_job(
        send_reminder, "cron",
        hour=h, minute=m, timezone=TZ,
        args=[app, chat_id],
        id=job_id, replace_existing=True
    )
    log.info(f"Reminder set for chat_id={chat_id} at {h:02d}:{m:02d}")


# ═══════════════════════════════════════════════
#  KEYBOARD HELPERS
# ═══════════════════════════════════════════════
def kb(*rows):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows]
    )

MAIN_MENU = kb(
    [("📅 Bugungi tartib",    "today"),  ("🗓 Haftalik tartib",  "week")],
    [("🛒 Xarid ro'yxati",   "shopping"),("ℹ️ Mening ma'lumotim","myinfo")],
    [("🔄 Qayta sozlash",     "restart")],
)


# ═══════════════════════════════════════════════
#  /start HANDLER
# ═══════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    cid = update.effective_chat.id
    patch_user(cid, {"first_name": u.first_name, "username": u.username, "chat_id": cid})

    if get_user(cid).get("weekly_plan"):
        await update.message.reply_text(
            f"👋 Xush kelibsiz, *{u.first_name}*!\n\nNima qilishni xohlaysiz?",
            reply_markup=MAIN_MENU, parse_mode="Markdown"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"👋 Salom, *{u.first_name}*!\n\n"
        "🤖 Men *Student Life Planner Bot*man!\n\n"
        "📋 *Nima qila olaman:*\n"
        "• Sizga mos 1 haftalik tartib tuzaman 🗓\n"
        "• Har kuni ertalab tartibni rasmda yuboran 🖼\n"
        "• Dars jadvalingizni rasm sifatida qabul qilaman 📸\n"
        "• Byudjet, allergiya, maqsadni hisobga olaman ✅\n"
        "• Ko'p foydalanuvchili — har kim o'z tartibini oladi 👥\n\n"
        "⏱ Sozlash ~3 daqiqa. Boshlaylikmi? 👇",
        reply_markup=kb([("🚀 Boshlash!", "begin")]),
        parse_mode="Markdown"
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════
#  ONBOARDING CONVERSATION
# ═══════════════════════════════════════════════

async def cb_begin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "1️⃣ *Siz hozir nima qilasiz?*",
        reply_markup=kb(
            [("💼 Ishlayman",          "st_work")],
            [("📚 O'qiyman (student)", "st_study")],
            [("💼📚 Ikkalasi ham",     "st_both")],
        ),
        parse_mode="Markdown"
    )
    return S_STATUS

async def cb_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    cid = q.message.chat_id
    status = {"st_work":"working","st_study":"studying","st_both":"both"}[q.data]
    patch_user(cid, {"status": status})

    if status in ("studying", "both"):
        await q.edit_message_text(
            "2️⃣ *Dars jadvalingizni yuboring*\n\n"
            "📷 Rasm — AI o'qib oladi(hozircha rasm bilan muammo bor, yozib yuboring)\n"
            "✏️ Yoki matn sifatida yozing(aynan quyidagi tartibda)\n\n"
            "_Masalan: Dush 8:00-10:00 Matematika, 10:00-12:00 Fizika_",
            parse_mode="Markdown"
        )
        return S_CLASS
    else:
        await q.edit_message_text(
            "2️⃣ *Ish vaqtingizni kiriting*\n\n"
            "Format: `09:00-18:00`\n"
            "_Yoki 'Erkin jadval' deb yozing_",
            parse_mode="Markdown"
        )
        return S_WORK

async def recv_work(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    patch_user(cid, {"work_schedule": update.message.text})
    await update.message.reply_text("3️⃣ *Bo'yingiz (sm)?*\n_Masalan: 175_", parse_mode="Markdown")
    return S_HEIGHT

async def recv_class_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    patch_user(cid, {"class_schedule": update.message.text})
    await update.message.reply_text("3️⃣ *Bo'yingiz (sm)?*\n_Masalan: 175_", parse_mode="Markdown")
    return S_HEIGHT

async def recv_class_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    msg = await update.message.reply_text("📸 Rasm qabul qilindi, o'qiyapman... ⏳")
    try:
        fobj  = await ctx.bot.get_file(update.message.photo[-1].file_id)
        raw   = await fobj.download_as_bytearray()
        result = await groq_vision(
            bytes(raw),
            "Bu rasmdagi dars jadvalini o'zbek tilida oddiy matn sifatida yoz. "
            "Format: KUN: VAQT - FAN. Faqat jadval matni — boshqa hech narsa yozma."
        )
        patch_user(cid, {"class_schedule": result})
        await msg.edit_text(f"✅ *Jadval o'qildi:*\n\n`{result}`", parse_mode="Markdown")
    except Exception as e:
        log.error(f"Vision error: {e}")
        patch_user(cid, {"class_schedule": "Noma'lum"})
        await msg.edit_text("⚠️ Rasm o'qishda xato. Davom etamiz...")
    await update.message.reply_text("3️⃣ *Bo'yingiz (sm)?*\n_Masalan: 175_", parse_mode="Markdown")
    return S_HEIGHT

async def recv_height(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        patch_user(update.effective_chat.id, {"height": int(update.message.text.strip())})
        await update.message.reply_text("4️⃣ *Yoshingiz?*\n_Masalan: 20_", parse_mode="Markdown")
        return S_AGE
    except Exception:
        await update.message.reply_text("❌ Faqat son. Masalan: `175`", parse_mode="Markdown")
        return S_HEIGHT

async def recv_age(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        patch_user(update.effective_chat.id, {"age": int(update.message.text.strip())})
        await update.message.reply_text("5️⃣ *Vazningiz (kg)?*\n_Masalan: 70_", parse_mode="Markdown")
        return S_WEIGHT
    except Exception:
        await update.message.reply_text("❌ Faqat son. Masalan: `20`", parse_mode="Markdown")
        return S_AGE

async def recv_weight(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        patch_user(update.effective_chat.id, {"weight": float(update.message.text.strip())})
        await update.message.reply_text(
            "6️⃣ *Asosiy maqsadingiz?*",
            reply_markup=kb(
                [("📚 Yaxshi o'qish / GPA",      "g_study")],
                [("💪 Sport / Jismoniy shakllanish","g_sport")],
                [("🥗 Sog'lom turmush tarzi",     "g_health")],
                [("⚡ Ish unumdorligi / Karyera",  "g_work")],
                [("⚖️ Vazn yo'qotish",             "g_loss")],
                [("🏋️ Mushak olish / Kuchlanish",  "g_muscle")],
            ),
            parse_mode="Markdown"
        )
        return S_GOAL
    except Exception:
        await update.message.reply_text("❌ Faqat son. Masalan: `70`", parse_mode="Markdown")
        return S_WEIGHT

GOALS = {
    "g_study":  "Yaxshi o'qish va yuqori GPA",
    "g_sport":  "Sport va jismoniy shakllanish",
    "g_health": "Sog'lom turmush tarzi",
    "g_work":   "Ish unumdorligi va karyera",
    "g_loss":   "Vazn yo'qotish",
    "g_muscle": "Mushak olish va kuchlanish",
}

async def cb_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    patch_user(q.message.chat_id, {"goal": GOALS[q.data]})
    await q.edit_message_text(
        "7️⃣ *Haftalik oziq-ovqat byudjelingiz?*",
        reply_markup=kb(
            [("💸 Juda kam  (<100k so'm)",   "b_low")],
            [("💰 Kam       (100–200k so'm)", "b_med")],
            [("💵 O'rta     (200–400k so'm)", "b_good")],
            [("💎 Yaxshi    (400k+ so'm)",    "b_high")],
        ),
        parse_mode="Markdown"
    )
    return S_BUDGET

BUDGETS = {
    "b_low":  "Juda kam (100k gacha)",
    "b_med":  "Kam (100–200k so'm)",
    "b_good": "O'rta (200–400k so'm)",
    "b_high": "Yaxshi (400k+ so'm)",
}

async def cb_budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    patch_user(q.message.chat_id, {"budget": BUDGETS[q.data]})
    await q.edit_message_text(
        "8️⃣ *Allergiya yoki yeya olmaydigan mahsulotlar?*",
        reply_markup=kb(
            [("✅ Yo'q, hammani yeyman", "al_no")],
            [("⚠️ Ha, kiritaman",       "al_yes")],
        ),
        parse_mode="Markdown"
    )
    return S_ALLERGY_Q

async def cb_allergy_q(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    cid = q.message.chat_id
    if q.data == "al_no":
        patch_user(cid, {"allergies": "yo'q"})
        await q.edit_message_text(
            "⏳ *AI tartibingizni tuzmoqda...*\n\n"
            "Bu ~20 soniya davom etadi. Kuting... 🧠",
            parse_mode="Markdown"
        )
        asyncio.create_task(_process(cid, ctx))
        return ConversationHandler.END
    await q.edit_message_text(
        "✏️ *Qaysi mahsulotlarga allergiyangiz?*\n\n"
        "Vergul bilan ajrating:\n"
        "_Masalan: sut, tuxum, yong'oq_",
        parse_mode="Markdown"
    )
    return S_ALLERGY_TXT

async def recv_allergy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    patch_user(cid, {"allergies": update.message.text})
    await update.message.reply_text(
        "⏳ *AI tartibingizni tuzmoqda...*\n\n"
        "Bu ~20 soniya davom etadi. Kuting... 🧠",
        parse_mode="Markdown"
    )
    asyncio.create_task(_process(cid, ctx))
    return ConversationHandler.END


# ═══════════════════════════════════════════════
#  PLAN GENERATION + SEND
# ═══════════════════════════════════════════════
async def _process(cid: int, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        user = get_user(cid)
        plan = await make_plan(user)
        patch_user(cid, {"weekly_plan": plan})

        wake_up = plan.get("reminder_times", {}).get("wake_up", "07:30")
        register_reminder(ctx.application.bot_data["scheduler"], ctx.application, cid, wake_up)

        today  = today_uz()
        ddata  = plan["days"].get(today, list(plan["days"].values())[0])
        name   = user.get("first_name", "Do'stim")
        buf    = build_image(today, ddata, name)

        # xarid ro'yxati
        sh = plan.get("weekly_shopping", {})
        shop_lines = "\n\n🛒 *Haftalik xarid ro'yxati:*\n"
        for item in sh.get("items", []):
            shop_lines += f"• {item['name']} — {item['amount']} (~{item.get('price_sum',0):,} so'm)\n"
        shop_lines += f"\n💰 *Jami:* ~{sh.get('total_sum',0):,} so'm"

        cap = (
            f"✅ *Tartibingiz tayyor, {name}!*\n\n"
            f"📅 Bugun: *{today}*\n"
            f"⏰ Uyg'onish: *{wake_up}*\n\n"
            f"Har kuni {wake_up} dan 5 daqiqa oldin eslatma keladi! 🎯"
            + shop_lines
        )
        await ctx.bot.send_photo(
            chat_id=cid, photo=buf,
            caption=cap, parse_mode="Markdown",
            reply_markup=MAIN_MENU
        )
    except Exception as e:
        log.error(f"Process error {cid}: {e}")
        await ctx.bot.send_message(
            chat_id=cid,
            text=f"❌ Xatolik yuz berdi: `{e}`\n\n/start bilan qayta boshlang.",
            parse_mode="Markdown"
        )


# ═══════════════════════════════════════════════
#  MENU CALLBACK HANDLERS
# ═══════════════════════════════════════════════
async def cb_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    cid  = q.message.chat_id
    user = get_user(cid)
    plan = user.get("weekly_plan")
    if not plan:
        await q.answer("❌ Avval /start bilan sozlang!", show_alert=True); return
    day   = today_uz()
    ddata = plan["days"].get(day, list(plan["days"].values())[0])
    buf   = build_image(day, ddata, user.get("first_name","Do'stim"))
    await ctx.bot.send_photo(chat_id=cid, photo=buf,
        caption=f"📅 *{day}* uchun tartib", parse_mode="Markdown",
        reply_markup=MAIN_MENU)

async def cb_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    cid  = q.message.chat_id
    plan = get_user(cid).get("weekly_plan")
    if not plan:
        await q.answer("❌ Avval /start bilan sozlang!", show_alert=True); return
    lines = ["📋 *Haftalik tartib qisqacha:*\n"]
    for day, dd in plan["days"].items():
        m  = dd.get("meals", {})
        bk = m.get("breakfast",{}).get("name","—")
        ln = m.get("lunch",    {}).get("name","—")
        dn = m.get("dinner",   {}).get("name","—")
        lines.append(f"*{day}*\n🌅 {bk}  |  ☀️ {ln}  |  🌙 {dn}\n_{dd.get('motivation','')}_\n")
    await q.edit_message_text(
        "\n".join(lines), parse_mode="Markdown",
        reply_markup=kb([("⬅️ Orqaga", "back_menu")])
    )

async def cb_shopping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    plan = get_user(q.message.chat_id).get("weekly_plan")
    if not plan:
        await q.answer("❌ Avval /start bilan sozlang!", show_alert=True); return
    sh = plan.get("weekly_shopping", {})
    lines = ["🛒 *Haftalik xarid ro'yxati:*\n"]
    for item in sh.get("items", []):
        lines.append(f"• {item['name']} — {item['amount']}  (~{item.get('price_sum',0):,} so'm)")
    lines.append(f"\n💰 *Jami:* ~{sh.get('total_sum',0):,} so'm")
    await q.edit_message_text("\n".join(lines), parse_mode="Markdown",
                              reply_markup=kb([("⬅️ Orqaga","back_menu")]))

async def cb_myinfo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    u = get_user(q.message.chat_id)
    if not u:
        await q.answer("❌ Ma'lumot topilmadi.", show_alert=True); return
    rt = u.get("weekly_plan", {}).get("reminder_times", {})
    await q.edit_message_text(
        f"ℹ️ *Sizning ma'lumotlaringiz:*\n\n"
        f"👤 Ism: {u.get('first_name','?')}\n"
        f"💼 Holat: {u.get('status','?')}\n"
        f"📏 Bo'yi: {u.get('height','?')} sm\n"
        f"🎂 Yoshi: {u.get('age','?')}\n"
        f"⚖️ Vazni: {u.get('weight','?')} kg\n"
        f"🎯 Maqsad: {u.get('goal','?')}\n"
        f"💰 Byudjet: {u.get('budget','?')}\n"
        f"⚠️ Allergiya: {u.get('allergies','?')}\n"
        f"⏰ Uyg'onish: {rt.get('wake_up','?')}\n"
        f"🌙 Uyqu: {rt.get('sleep','?')}",
        parse_mode="Markdown",
        reply_markup=kb([("⬅️ Orqaga","back_menu")])
    )

async def cb_restart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "⚠️ *Barcha ma'lumotlaringiz o'chib ketadi!*\nRostan qayta boshlaylikmi?",
        reply_markup=kb(
            [("🗑 Ha, o'chiraman","restart_yes")],
            [("❌ Yo'q, bekor",   "back_menu")],
        ),
        parse_mode="Markdown"
    )

async def cb_restart_yes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    cid = q.message.chat_id
    clear_user(cid)
    jid = f"rem_{cid}"
    if ctx.application.bot_data["scheduler"].get_job(jid):
        ctx.application.bot_data["scheduler"].remove_job(jid)
    await q.edit_message_text(
        "🔄 Ma'lumotlaringiz o'chirildi. Qaytadan boshlaylikmi?",
        reply_markup=kb([("🚀 Boshlash!", "begin")])
    )

async def cb_back_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("Nima qilishni xohlaysiz?", reply_markup=MAIN_MENU)


# ═══════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════
async def post_init(app: Application):
    """Bot ishga tushganda scheduler ni ham ishga tushir."""
    scheduler = AsyncIOScheduler(timezone=TZ)
    app.bot_data["scheduler"] = scheduler

    for uid, udata in _load().items():
        plan = udata.get("weekly_plan")
        if plan:
            wake = plan.get("reminder_times", {}).get("wake_up", "07:30")
            register_reminder(scheduler, app, int(uid), wake)

    scheduler.start()
    log.info("✅ Scheduler ishga tushdi.")


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_begin, pattern="^begin$")],
        states={
            S_STATUS:      [CallbackQueryHandler(cb_status, pattern="^st_")],
            S_WORK:        [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_work)],
            S_CLASS:       [
                MessageHandler(filters.PHOTO, recv_class_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_class_text),
            ],
            S_HEIGHT:      [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_height)],
            S_AGE:         [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_age)],
            S_WEIGHT:      [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_weight)],
            S_GOAL:        [CallbackQueryHandler(cb_goal,      pattern="^g_")],
            S_BUDGET:      [CallbackQueryHandler(cb_budget,    pattern="^b_")],
            S_ALLERGY_Q:   [CallbackQueryHandler(cb_allergy_q, pattern="^al_")],
            S_ALLERGY_TXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_allergy)],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        per_message=False,
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(cb_today,       pattern="^today$"))
    app.add_handler(CallbackQueryHandler(cb_week,        pattern="^week$"))
    app.add_handler(CallbackQueryHandler(cb_shopping,    pattern="^shopping$"))
    app.add_handler(CallbackQueryHandler(cb_myinfo,      pattern="^myinfo$"))
    app.add_handler(CallbackQueryHandler(cb_restart,     pattern="^restart$"))
    app.add_handler(CallbackQueryHandler(cb_restart_yes, pattern="^restart_yes$"))
    app.add_handler(CallbackQueryHandler(cb_back_menu,   pattern="^back_menu$"))

    log.info("✅ Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
