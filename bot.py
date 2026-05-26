"""
bot.py
YouTube Downloader Telegram Bot
aiogram 3.x | Inline Admin Panel | VIP Management
"""
import asyncio
import logging
import time
from typing import Optional

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton, BotCommand,
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.client.default import DefaultBotProperties

from config import (
    BOT_TOKEN, ADMIN_IDS, FREE_DAILY_LIMIT, FREE_MAX_HEIGHT,
    FREE_MAX_FILE_MB, VIP_MAX_FILE_MB, MESSAGES, VIP_CONTACT,
)
from database import Database
from downloader import Downloader, extract_url

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)
db = Database()
dl = Downloader()
_active = {}


# ===========================================================================
# FSM States
# ===========================================================================
class DlState(StatesGroup):
    waiting = State()

class AdminState(StatesGroup):
    add_vip    = State()
    remove_vip = State()
    ban        = State()
    unban      = State()
    lookup     = State()
    broadcast  = State()


# ===========================================================================
# Keyboards
# ===========================================================================
def kb_admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 آمار ربات", callback_data="ap:stats")],
        [
            InlineKeyboardButton(text="👑 افزودن VIP",  callback_data="ap:addvip"),
            InlineKeyboardButton(text="🗑 حذف VIP",    callback_data="ap:rmvip"),
        ],
        [InlineKeyboardButton(text="🔍 جستجوی کاربر", callback_data="ap:lookup")],
        [
            InlineKeyboardButton(text="🚫 بن کردن",    callback_data="ap:ban"),
            InlineKeyboardButton(text="✅ رفع بن",     callback_data="ap:unban"),
        ],
        [InlineKeyboardButton(text="📢 ارسال همگانی", callback_data="ap:broadcast")],
    ])

def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ انصراف", callback_data="ap:cancel")]
    ])

def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="ap:panel")]
    ])

def kb_quality(videos, audios, vid) -> InlineKeyboardMarkup:
    rows = []
    if videos:
        rows.append([InlineKeyboardButton(text="──── 🎬 ویدیو ────", callback_data="noop")])
        for f in videos:
            h   = f["height"]
            sz  = dl.fmt_size(f.get("filesize"), f.get("filesize_approx", False))
            fps = f" {int(f['fps'])}fps" if f.get("fps") and f["fps"] > 30 else ""
            ico = "🔒 " if f["vip_required"] else "✅ "
            lbl = f"{ico}{h}p{fps}   {sz}"
            cb  = f"vr:{h}" if f["vip_required"] else f"dv:{vid}:{h}"
            rows.append([InlineKeyboardButton(text=lbl, callback_data=cb)])
    if audios:
        rows.append([InlineKeyboardButton(text="──── 🎵 صدا ────", callback_data="noop")])
        row = []
        for f in audios:
            ico = "🔒 " if f["vip_required"] else "🎵 "
            lbl = f"{ico}{f['label']}"
            cb  = "vr:a" if f["vip_required"] else f"da:{vid}:{f['format']}:{f['quality']}"
            row.append(InlineKeyboardButton(text=lbl, callback_data=cb))
            if len(row) == 2:
                rows.append(row); row = []
        if row:
            rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ لغو", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ===========================================================================
# Video cache
# ===========================================================================
_cache = {}

def cc_set(url, info, fmts):
    vid = str(abs(hash(url + str(time.time()))))[:12]
    _cache[vid] = {"url": url, "info": info, "fmts": fmts, "exp": int(time.time()) + 3600}
    now = int(time.time())
    for k in [k for k, v in _cache.items() if v["exp"] < now]:
        del _cache[k]
    return vid

def cc_get(vid):
    d = _cache.get(vid)
    return d if d and d["exp"] > int(time.time()) else None


# ===========================================================================
# Admin panel text builder
# ===========================================================================
async def admin_panel_text():
    s = await db.get_stats()
    return (
        "┌──────────────────────────────┐\n"
        "│  🛠  پنل مدیریت ربات         │\n"
        "└──────────────────────────────┘\n\n"
        f"👥 کل کاربران: <b>{s['total_users']:,}</b>  (👑 {s['vip_users']:,} VIP)\n"
        f"📥 دانلود امروز: <b>{s['today_downloads']:,}</b>\n"
        f"🆕 عضو امروز: <b>{s['today_users']:,}</b>\n\n"
        "یک گزینه انتخاب کنید:"
    )


# ===========================================================================
# Helpers
# ===========================================================================
def is_admin(uid): return uid in ADMIN_IDS

async def safe_edit(msg, text, mk=None):
    try:
        return await msg.edit_text(text, reply_markup=mk)
    except TelegramBadRequest:
        return None


# ===========================================================================
# User commands
# ===========================================================================
@router.message(CommandStart())
async def cmd_start(m: Message):
    u = m.from_user
    await db.get_or_create_user(u.id, u.username, u.first_name)
    vip = await db.is_vip(u.id)
    badge = "👑 <b>VIP</b>" if vip else "🆓 رایگان"
    await m.answer(MESSAGES["welcome"].format(name=u.first_name or "دوست", status=badge))

@router.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer(MESSAGES["help"])

@router.message(Command("status"))
async def cmd_status(m: Message):
    uid = m.from_user.id
    await db.get_or_create_user(uid)
    vip = await db.is_vip(uid)
    cnt = await db.get_daily_count(uid)
    exp = await db.get_vip_expiry(uid)
    if vip:
        es = exp.strftime("%Y-%m-%d") if exp else "نامحدود"
        txt = (
            "┌──────────────────────────┐\n"
            "│  👑  حساب VIP Premium    │\n"
            "└──────────────────────────┘\n\n"
            f"✅ دانلود نامحدود\n✅ کیفیت تا 4K\n✅ فایل تا 2GB\n\n"
            f"📊 امروز: <b>{cnt}</b>\n📅 انقضا: <code>{es}</code>"
        )
    else:
        rem = max(0, FREE_DAILY_LIMIT - cnt)
        txt = (
            "┌──────────────────────────┐\n"
            "│  🆓  حساب رایگان         │\n"
            "└──────────────────────────┘\n\n"
            f"📊 امروز: <b>{cnt}/{FREE_DAILY_LIMIT}</b>\n"
            f"⏳ باقیمانده: <b>{rem}</b>\n"
            f"🔒 حداکثر کیفیت: <b>{FREE_MAX_HEIGHT}p</b>\n\n"
            f"👑 ارتقا: /vip"
        )
    await m.answer(txt)

@router.message(Command("vip"))
async def cmd_vip(m: Message):
    await m.answer(MESSAGES["vip_info"].format(contact=VIP_CONTACT))

@router.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    _active.pop(m.from_user.id, None)
    await m.answer("✅ لغو شد.")


# ===========================================================================
# /admin  —  Inline Panel
# ===========================================================================
@router.message(Command("admin"))
async def cmd_admin(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        await m.answer("🚫 دسترسی ندارید.")
        return
    await state.clear()
    await m.answer(await admin_panel_text(), reply_markup=kb_admin_panel())


# ── Panel refresh ─────────────────────────────────────────────────────────────
@router.callback_query(F.data == "ap:panel")
async def ap_panel(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer()
    await state.clear()
    await cb.message.edit_text(await admin_panel_text(), reply_markup=kb_admin_panel())
    await cb.answer()


# ── Stats ─────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "ap:stats")
async def ap_stats(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer()
    s = await db.get_stats()
    txt = (
        "📊 <b>آمار کامل</b>\n━━━━━━━━━━━━━━━━\n\n"
        f"👥 کل کاربران:     <b>{s['total_users']:,}</b>\n"
        f"👑 VIP:            <b>{s['vip_users']:,}</b>\n"
        f"🆓 رایگان:         <b>{s['free_users']:,}</b>\n\n"
        f"📥 کل دانلودها:    <b>{s['total_downloads']:,}</b>\n"
        f"📥 دانلود امروز:   <b>{s['today_downloads']:,}</b>\n"
        f"🆕 عضو امروز:      <b>{s['today_users']:,}</b>"
    )
    await cb.message.edit_text(txt, reply_markup=kb_back())
    await cb.answer()


# ── Add VIP ───────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "ap:addvip")
async def ap_addvip_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer()
    await cb.message.edit_text(
        "👑 <b>افزودن VIP</b>\n━━━━━━━━━━━━━━━━\n\n"
        "آیدی عددی کاربر و تعداد روز را بفرست:\n\n"
        "📌 فرمت: <code>[user_id] [روز]</code>\n"
        "مثال: <code>123456789 30</code>\n\n"
        "اگه روز ننویسی پیش‌فرض <b>30 روز</b> هست.",
        reply_markup=kb_cancel())
    await state.set_state(AdminState.add_vip)
    await cb.answer()

@router.message(AdminState.add_vip)
async def ap_addvip_do(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    parts = m.text.strip().split()
    try:
        uid  = int(parts[0])
        days = int(parts[1]) if len(parts) > 1 else 30
    except (ValueError, IndexError):
        await m.answer("❌ فرمت اشتباه!\nمثال: <code>123456789 30</code>", reply_markup=kb_cancel())
        return

    await db.get_or_create_user(uid)
    await db.set_vip(uid, days)
    exp = await db.get_vip_expiry(uid)
    es  = exp.strftime("%Y-%m-%d") if exp else "—"

    await m.answer(
        "┌──────────────────────────┐\n"
        "│  ✅  VIP فعال شد         │\n"
        "└──────────────────────────┘\n\n"
        f"👤 User ID:  <code>{uid}</code>\n"
        f"📅 مدت:      <b>{days} روز</b>\n"
        f"⏳ انقضا:    <code>{es}</code>",
        reply_markup=kb_back())
    try:
        await bot.send_message(uid,
            f"🎉 اشتراک <b>VIP</b> شما برای <b>{days} روز</b> فعال شد!\n"
            f"انقضا: <code>{es}</code>")
    except Exception:
        pass
    await state.clear()


# ── Remove VIP ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "ap:rmvip")
async def ap_rmvip_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer()
    await cb.message.edit_text(
        "🗑 <b>حذف VIP</b>\n━━━━━━━━━━━━━━━━\n\n"
        "آیدی عددی کاربر را بفرست:\n\n"
        "مثال: <code>123456789</code>",
        reply_markup=kb_cancel())
    await state.set_state(AdminState.remove_vip)
    await cb.answer()

@router.message(AdminState.remove_vip)
async def ap_rmvip_do(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    try:
        uid = int(m.text.strip())
    except ValueError:
        await m.answer("❌ آیدی باید عدد باشد.", reply_markup=kb_cancel())
        return

    u = await db.get_user(uid)
    if not u:
        await m.answer(f"⚠️ کاربر <code>{uid}</code> ثبت نشده.", reply_markup=kb_back())
        await state.clear(); return

    was = await db.is_vip(uid)
    await db.remove_vip(uid)
    await m.answer(
        "┌──────────────────────────┐\n"
        "│  🗑  VIP حذف شد          │\n"
        "└──────────────────────────┘\n\n"
        f"👤 User ID:  <code>{uid}</code>\n"
        f"🔖 نام:      {u.get('first_name') or '—'}\n"
        f"📌 قبلاً VIP: {'✅' if was else '❌'}",
        reply_markup=kb_back())
    try:
        await bot.send_message(uid, "⚠️ اشتراک VIP شما توسط ادمین حذف شد.")
    except Exception:
        pass
    await state.clear()


# ── Lookup ────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "ap:lookup")
async def ap_lookup_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer()
    await cb.message.edit_text(
        "🔍 <b>جستجوی کاربر</b>\n\nآیدی عددی کاربر را بفرست:",
        reply_markup=kb_cancel())
    await state.set_state(AdminState.lookup)
    await cb.answer()

@router.message(AdminState.lookup)
async def ap_lookup_do(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    try:
        uid = int(m.text.strip())
    except ValueError:
        await m.answer("❌ آیدی باید عدد باشد.", reply_markup=kb_cancel()); return

    u = await db.get_user(uid)
    if not u:
        await m.answer(f"⚠️ کاربر <code>{uid}</code> یافت نشد.", reply_markup=kb_back())
        await state.clear(); return

    vip = await db.is_vip(uid)
    exp = await db.get_vip_expiry(uid)
    cnt = await db.get_daily_count(uid)
    es  = exp.strftime("%Y-%m-%d") if exp else "—"
    await m.answer(
        "🔍 <b>اطلاعات کاربر</b>\n━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID:            <code>{uid}</code>\n"
        f"👤 نام:           {u.get('first_name') or '—'}\n"
        f"📛 یوزرنیم:      @{u.get('username') or '—'}\n"
        f"👑 VIP:           {'✅ بله' if vip else '❌ خیر'}\n"
        f"📅 انقضا VIP:    <code>{es}</code>\n"
        f"📥 امروز:         <b>{cnt}</b>\n"
        f"📥 کل دانلودها:   <b>{u.get('total_downloads', 0)}</b>\n"
        f"🚫 بن:            {'✅' if u.get('is_banned') else '❌'}\n"
        f"🗓 عضویت:         {str(u.get('join_date', ''))[:10]}",
        reply_markup=kb_back())
    await state.clear()


# ── Ban ───────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "ap:ban")
async def ap_ban_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer()
    await cb.message.edit_text(
        "🚫 <b>بن کردن کاربر</b>\n\nآیدی عددی کاربر را بفرست:",
        reply_markup=kb_cancel())
    await state.set_state(AdminState.ban)
    await cb.answer()

@router.message(AdminState.ban)
async def ap_ban_do(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    try:
        uid = int(m.text.strip())
    except ValueError:
        await m.answer("❌ آیدی باید عدد باشد.", reply_markup=kb_cancel()); return
    await db.get_or_create_user(uid)
    await db.ban_user(uid)
    await m.answer(f"🚫 کاربر <code>{uid}</code> بن شد.", reply_markup=kb_back())
    try:
        await bot.send_message(uid, "🚫 حساب شما توسط ادمین مسدود شد.")
    except Exception:
        pass
    await state.clear()


# ── Unban ─────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "ap:unban")
async def ap_unban_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer()
    await cb.message.edit_text(
        "✅ <b>رفع بن کاربر</b>\n\nآیدی عددی کاربر را بفرست:",
        reply_markup=kb_cancel())
    await state.set_state(AdminState.unban)
    await cb.answer()

@router.message(AdminState.unban)
async def ap_unban_do(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    try:
        uid = int(m.text.strip())
    except ValueError:
        await m.answer("❌ آیدی باید عدد باشد.", reply_markup=kb_cancel()); return
    await db.unban_user(uid)
    await m.answer(f"✅ بن کاربر <code>{uid}</code> برداشته شد.", reply_markup=kb_back())
    try:
        await bot.send_message(uid, "✅ مسدودیت حساب شما برداشته شد.")
    except Exception:
        pass
    await state.clear()


# ── Broadcast ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "ap:broadcast")
async def ap_bc_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer()
    await cb.message.edit_text(
        "📢 <b>ارسال همگانی</b>\n\nمتن پیام را بفرست:",
        reply_markup=kb_cancel())
    await state.set_state(AdminState.broadcast)
    await cb.answer()

@router.message(AdminState.broadcast)
async def ap_bc_do(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    txt = m.html_text or m.text or ""
    if not txt.strip():
        await m.answer("❌ متن نمی‌تواند خالی باشد.", reply_markup=kb_cancel()); return
    uids = await db.get_all_user_ids()
    sm = await m.answer(f"⏳ ارسال به <b>{len(uids):,}</b> کاربر...")
    ok = fail = 0
    for uid in uids:
        try:
            await bot.send_message(uid, txt)
            ok += 1; await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    await sm.edit_text(
        f"✅ <b>ارسال تموم شد!</b>\n\n✔ موفق: <b>{ok:,}</b>\n❌ ناموفق: <b>{fail:,}</b>",
        reply_markup=kb_back())
    await state.clear()


# ── Cancel FSM ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "ap:cancel")
async def ap_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(await admin_panel_text(), reply_markup=kb_admin_panel())
    await cb.answer()


# ===========================================================================
# URL handler
# ===========================================================================
@router.message(F.text)
async def handle_url(m: Message, state: FSMContext):
    u   = m.from_user
    txt = m.text.strip()
    url = extract_url(txt)
    if not url:
        if txt.startswith("/"):
            await m.answer("❓ دستور ناشناخته. /help بزن.")
        return

    if await db.is_banned(u.id):
        await m.answer("🚫 حساب شما مسدود شده."); return
    await db.get_or_create_user(u.id, u.username, u.first_name)
    if _active.get(u.id):
        await m.answer("⚠️ دانلود قبلی تموم نشده. /cancel"); return

    sm = await m.answer(MESSAGES["extracting"])
    try:
        info = await dl.get_video_info(url)
    except ValueError as e:
        await safe_edit(sm, f"❌ {e}"); return
    except Exception as e:
        logger.error(f"extract err: {e}", exc_info=True)
        await safe_edit(sm, "❌ خطای غیرمنتظره."); return

    if info.get("is_live"):
        await safe_edit(sm, MESSAGES["error_live"]); return

    vip  = await db.is_vip(u.id)
    fmts = dl.parse_formats(info, is_vip=vip)
    if not fmts["video"] and not fmts["audio"]:
        await safe_edit(sm, MESSAGES["no_formats"]); return

    vid      = cc_set(url, info, fmts)
    title    = info.get("title", "ویدیو")[:80]
    duration = dl.fmt_dur(info.get("duration"))
    views    = dl.fmt_views(info.get("view_count"))
    await safe_edit(sm,
        MESSAGES["select_quality"].format(title=title, duration=duration, views=views),
        mk=kb_quality(fmts["video"], fmts["audio"], vid))
    await state.set_state(DlState.waiting)


# ===========================================================================
# Download callbacks
# ===========================================================================
@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery): await cb.answer()

@router.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear(); _active.pop(cb.from_user.id, None)
    await cb.message.edit_text(MESSAGES["cancelled"]); await cb.answer()

@router.callback_query(F.data.startswith("vr:"))
async def cb_vip_req(cb: CallbackQuery):
    await cb.answer("🔒 VIP only!\n\n/vip", show_alert=True)

@router.callback_query(F.data.startswith("dv:"))
async def cb_dl_video(cb: CallbackQuery, state: FSMContext):
    _, vid, h = cb.data.split(":", 2)
    await cb.answer()
    await _run_dl(cb.message, state, cb.from_user.id, vid, height=int(h))

@router.callback_query(F.data.startswith("da:"))
async def cb_dl_audio(cb: CallbackQuery, state: FSMContext):
    _, vid, afmt, aqty = cb.data.split(":", 3)
    await cb.answer()
    await _run_dl(cb.message, state, cb.from_user.id, vid,
                  is_audio=True, audio_format=afmt, audio_quality=aqty)


# ===========================================================================
# Download core
# ===========================================================================
async def _run_dl(msg, state, uid, vid, is_audio=False,
                  height=None, audio_format="mp3", audio_quality="192"):
    if _active.get(uid):
        await msg.answer("⚠️ دانلود قبلی تموم نشده!"); return
    cached = cc_get(vid)
    if not cached:
        await msg.edit_text("❌ منقضی شد. لینک رو دوباره بفرست.")
        await state.clear(); return

    url  = cached["url"]
    info = cached["info"]
    vip  = await db.is_vip(uid)

    if not vip:
        if not is_audio and height and height > FREE_MAX_HEIGHT:
            await msg.answer(MESSAGES["not_vip"]); return
        if await db.get_daily_count(uid) >= FREE_DAILY_LIMIT:
            await msg.answer(MESSAGES["daily_limit"]); return

    _active[uid] = True
    await state.clear()
    ql = f"🎵 {audio_format.upper()} {audio_quality}kbps" if is_audio else f"🎬 {height}p"
    sm = await msg.edit_text(f"⬇️ <b>شروع دانلود...</b>\n📌 {ql}\n\n⏳ صبر کن...")
    last = [0.0]

    async def prog(status, percent=0, downloaded=0, total=0, speed=0, eta=0):
        now = time.time()
        if now - last[0] < 3: return
        last[0] = now
        bar = dl.pbar(percent)
        if status == "downloading":
            t = (f"⬇️ <b>در حال دانلود...</b>\n📌 {ql}\n\n"
                 f"<code>{bar}</code>\n"
                 f"💾 {dl.fmt_size(downloaded)} / {dl.fmt_size(total) if total else '?'}\n"
                 f"⚡ {dl.fmt_size(int(speed))}/s  ⏱ {dl.fmt_dur(eta)}")
        elif status == "merging":
            t = f"🔧 <b>ادغام ویدیو و صدا...</b>\n📌 {ql}"
        else:
            return
        try:
            await sm.edit_text(t)
        except TelegramBadRequest:
            pass

    fp = None
    try:
        fp, fi = await dl.download(url=url, height=height if not is_audio else None,
                                   is_audio=is_audio, audio_format=audio_format,
                                   audio_quality=audio_quality, user_id=uid,
                                   progress_callback=prog)
        fs  = fi["filesize"]
        mx  = (VIP_MAX_FILE_MB if vip else FREE_MAX_FILE_MB) * 1024 * 1024
        if fs > mx:
            await sm.edit_text(MESSAGES["error_size"].format(
                size=dl.fmt_size(fs), max_size=dl.fmt_size(mx)))
            dl.cleanup(fp); return

        await sm.edit_text("⬆️ <b>در حال آپلود به تلگرام...</b>")
        title   = info.get("title", "video")[:80]
        channel = info.get("uploader") or info.get("channel") or ""
        cap = (f"🎬 <b>{title}</b>\n📺 {channel}\n"
               f"━━━━━━━━━━━━━━━━\n📌 {ql}   💾 {dl.fmt_size(fs)}")
        with open(fp, "rb") as f:
            if is_audio:
                await bot.send_audio(msg.chat.id, f, title=title[:64],
                                     performer=channel[:64], caption=cap)
            else:
                await bot.send_video(msg.chat.id, f, caption=cap, supports_streaming=True)

        await db.increment_daily_count(uid)
        await db.log_download(uid, url, title, ql, fs, "success")
        await sm.edit_text("✅ <b>دانلود و ارسال با موفقیت انجام شد!</b>")

    except ValueError as e:
        await sm.edit_text(f"❌ <b>خطا:</b>\n<code>{str(e)[:300]}</code>")
        if fp: await db.log_download(uid, url, status="failed")
    except TelegramBadRequest as e:
        logger.error(f"TG err: {e}")
        await sm.edit_text("❌ خطا در ارسال. فایل خیلی بزرگه یا فرمت پشتیبانی نمیشه.")
    except Exception as e:
        logger.error(f"dl err uid={uid}: {e}", exc_info=True)
        await sm.edit_text("❌ خطای غیرمنتظره.")
    finally:
        if fp: dl.cleanup(fp)
        _active.pop(uid, None)


# ===========================================================================
# Startup / Shutdown / Main
# ===========================================================================
async def on_startup():
    await db.init()
    await bot.set_my_commands([
        BotCommand(command="start",  description="شروع ربات"),
        BotCommand(command="help",   description="راهنما"),
        BotCommand(command="status", description="وضعیت حساب"),
        BotCommand(command="vip",    description="اشتراک VIP"),
        BotCommand(command="cancel", description="لغو دانلود"),
        BotCommand(command="admin",  description="پنل ادمین"),
    ])
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, "✅ ربات راه‌اندازی شد!")
        except Exception:
            pass
    logger.info("Bot ready.")

async def on_shutdown():
    await bot.session.close()

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"],
                           drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
