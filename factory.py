"""
🏭 المصنع — البوت الرئيسي (نسخة أزرار Inline + اشتراك إجباري + إذاعة)

الفلو الجديد:
- /start → رسالة ترحيب مع GIF + كل التعامل بأزرار inline
- اشتراك إجباري: لو فيه قنوات في force_sub.json، البوت يفحص العضوية قبل أي شيء
- المطور (ADMIN_USER_ID) عنده قائمة خاصة بأزرار: إذاعة + إدارة قنوات الاشتراك + إحصائيات
- الإذاعة: تتبعت لكل المستخدمين + كل القنوات اللي البوتات الفرعية فيها
"""
import asyncio
import logging
import sys
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    Message,
)

from config import FACTORY_TOKEN, ADMIN_USER_ID, START_GIF
from reactor_bot import ReactorBot
import storage
import keyboards as kbs


# ─── Logging ────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("factory")


# ─── المصنع ─────────────────────────────────────────

factory_bot = Bot(token=FACTORY_TOKEN)
factory_dp = Dispatcher(storage=MemoryStorage())

# قاموس البوتات الشغالة { bot_id: ReactorBot }
running_bots: dict[str, ReactorBot] = {}


# ─── FSM States ─────────────────────────────────────

class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_fsub_channel = State()


class UserStates(StatesGroup):
    waiting_token = State()
    # المستخدم بعت توكن صحيح وبيختار نوع الريأكشن
    choosing_reaction = State()


# tmp store: user_id -> {bot_id, token, info, owner_*}
# نخزن مؤقتاً بيانات التوكن أثناء اختيار النوع، عشان مانعملش رسائل جديدة
_pending_token_choice: dict[int, dict] = {}


# ─── Helpers لتعديل الرسائل بدل إرسال جديدة ────────

async def _safe_edit(message: Message, text: str, reply_markup=None) -> bool:
    """
    يحاول يعدّل الرسالة (caption لو فيها وسائط، أو text عادي).
    يرجّع True لو نجح. لو فشل (مثلاً الرسالة قديمة جداً) ما يبعتش رسالة جديدة.
    """
    try:
        if message.caption is not None or message.photo or message.animation or message.video:
            await message.edit_caption(
                caption=text, parse_mode="HTML", reply_markup=reply_markup,
            )
        else:
            await message.edit_text(
                text, parse_mode="HTML", reply_markup=reply_markup,
            )
        return True
    except TelegramAPIError:
        return False
    except Exception:
        return False


async def _edit_or_send(query: CallbackQuery, text: str, reply_markup=None) -> None:
    """
    يحاول يعدّل رسالة الكولباك. لو ما قدرش (لأنها وسائط بدون caption مثلاً
    أو تخطّت 48 ساعة)، يبعت رسالة جديدة كـ fallback أخير.
    """
    if await _safe_edit(query.message, text, reply_markup):
        return
    try:
        await query.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramAPIError:
        pass


# ─── أدوات ──────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_USER_ID


def is_valid_token_format(text: str) -> bool:
    if ":" not in text:
        return False
    left, right = text.split(":", 1)
    return left.isdigit() and len(right) >= 30 and len(left) >= 6


async def verify_token(token: str) -> Optional[dict]:
    tmp = Bot(token=token)
    try:
        me = await tmp.get_me()
        return {
            "id": me.id,
            "username": me.username or "",
            "first_name": me.first_name or "Bot",
        }
    except TelegramAPIError:
        return None
    finally:
        try:
            await tmp.session.close()
        except Exception:
            pass


async def start_reactor(bot_id: str, token: str, label: str) -> bool:
    if bot_id in running_bots:
        return True
    try:
        rb = ReactorBot(token=token, bot_id=bot_id, label=label)
        rb.start()
        running_bots[bot_id] = rb
        log.info("🚀 شغّلت البوت: %s", label)
        return True
    except Exception as e:
        log.exception("❌ فشل تشغيل البوت %s: %s", label, e)
        return False


async def stop_reactor(bot_id: str) -> None:
    rb = running_bots.pop(bot_id, None)
    if rb:
        await rb.stop()
        log.info("🛑 وقّفت البوت: %s", bot_id)


# ─── الاشتراك الإجباري ────────────────────────────

async def missing_subscriptions(user_id: int) -> list[dict]:
    """يرجّع قنوات الاشتراك الإجباري اللي المستخدم مش مشترك فيها."""
    channels = storage.load_force_sub()
    if not channels:
        return []
    missing: list[dict] = []
    for ch in channels:
        try:
            member = await factory_bot.get_chat_member(
                chat_id=int(ch["id"]), user_id=user_id
            )
            if member.status in ("left", "kicked"):
                missing.append(ch)
        except TelegramAPIError:
            # لو البوت مش موجود في القناة أو خطأ → نعتبرها مفقودة
            missing.append(ch)
    return missing


async def enforce_subscription(user_id: int, target_chat_id: int) -> bool:
    """
    يفحص الاشتراك. لو ناقص → يبعت رسالة بقنوات الاشتراك ويرجّع False.
    لو تمام → True.
    """
    if is_admin(user_id):
        return True
    missing = await missing_subscriptions(user_id)
    if not missing:
        return True
    text = (
        "🔒 <b>اشتراك إجباري</b>\n\n"
        "عشان تستخدم البوت، اشترك في القنوات دي الأول:\n\n"
        + "\n".join(f"• <b>{c.get('title','قناة')}</b>" for c in missing)
        + "\n\nبعدين اضغط <b>«✅ تحققت — اشتركت»</b>."
    )
    try:
        await factory_bot.send_message(
            target_chat_id, text,
            parse_mode="HTML", reply_markup=kbs.kb_force_sub(missing),
        )
    except TelegramAPIError:
        pass
    return False


# ─── شاشة /start ────────────────────────────────────

async def send_start_screen(chat_id: int, user_id: int, user_name: str = "") -> None:
    greeting = (        f"""
╭───⌁𝗧𝗹𝗔𝘀𝗛𝗮𝗡𝘆⌁───⟤
│╭───────────⟢
╞𝗧- <b>{user_name or ''}</b>
╞╡ 
╞𝗧-     ده مـصنع بـوتات تفاعلـية
╞╡
╞𝗧-     اعمـل بـوت خـاص بـيك
╞╡
╞𝗧-    @BotFather هـات تـوكن من
╞╡
╞𝗧-          ابـعت التـوكن هنا
│╰────────────╮
│╭────────────╯
╞𝗧- ضيـف الـبوت ادمـن في قناتك 
│╰───────────⟢
╰───⌁𝗧𝗹𝗔𝘀𝗛𝗮𝗡𝘆⌁───⟤"""
    )
    keyboard = kbs.kb_admin_main() if is_admin(user_id) else kbs.kb_user_main()
    try:
        await factory_bot.send_animation(
            chat_id=chat_id,
            animation=START_GIF,
            caption=greeting,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except TelegramAPIError:
        # fallback لو الجرافيك فشل
        await factory_bot.send_message(
            chat_id, greeting, parse_mode="HTML", reply_markup=keyboard,
        )


# ─── /start ────────────────────────────────────────

@factory_dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = message.from_user
    user_name = user.full_name
    storage.add_user(user.id, name=user_name, username=user.username or "")

    # فحص الاشتراك الإجباري
    if not await enforce_subscription(user.id, message.chat.id):
        return

    await send_start_screen(message.chat.id, user.id, user_name)


@factory_dp.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        " <b>قائمة المطور</b>\nاختار العملية:",
        parse_mode="HTML", reply_markup=kbs.kb_admin_main(),
    )


# ─── Callback: تحقق الاشتراك ───────────────────────

@factory_dp.callback_query(F.data == "fsub:check")
async def cb_fsub_check(query: CallbackQuery) -> None:
    missing = await missing_subscriptions(query.from_user.id)
    if missing:
        await query.answer("🟥 لسه فيه قنوات لازم تشترك فيها.", show_alert=True)
        return
    await query.answer("🟩 تمام! اتأكدت من اشتراكك.", show_alert=False)
    try:
        await query.message.delete()
    except Exception:
        pass
    await send_start_screen(
        query.message.chat.id, query.from_user.id, query.from_user.full_name,
    )


# ─── Callbacks: قائمة المستخدم ─────────────────────

@factory_dp.callback_query(F.data == "user:home")
async def cb_user_home(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not await enforce_subscription(query.from_user.id, query.message.chat.id):
        await query.answer()
        return
    text = f"""
╭───⌁𝗧𝗹𝗔𝘀𝗛𝗮𝗡𝘆⌁───⟤
│╭───────────⟢
╞𝗧- <b>{query.from_user.full_name}</b>
╞╡ 
╞𝗧-     ده مـصنع بـوتات تفاعلـية
╞╡
╞𝗧-     اعمـل بـوت خـاص بـيك
╞╡
╞𝗧-    @BotFather هـات تـوكن من
╞╡
╞𝗧-          ابـعت التـوكن هنا
│╰────────────╮
│╭────────────╯
╞𝗧- ضيـف الـبوت ادمـن في قناتك 
│╰───────────⟢
╰───⌁𝗧𝗹𝗔𝘀𝗛𝗮𝗡𝘆⌁───⟤"""
    await _edit_or_send(query, text, reply_markup=kbs.kb_user_main())
    await query.answer()


@factory_dp.callback_query(F.data == "user:add_bot")
async def cb_user_add_bot(query: CallbackQuery, state: FSMContext) -> None:
    if not await enforce_subscription(query.from_user.id, query.message.chat.id):
        await query.answer()
        return
    await state.set_state(UserStates.waiting_token)
    text = (
        "📨 <b>ابعتلي توكن البوت بتاعك</b>\n\n"
        "هتجيبه من @BotFather بأمر <code>/newbot</code> أو <code>/mybots</code>.\n\n"
        "<i>مثال:</i> <code>123456789:AAH...XYZ</code>"
    )
    await _edit_or_send(
        query, text,
        reply_markup=kbs.kb_cancel_action("user:cancel_token"),
    )
    await query.answer()


@factory_dp.callback_query(F.data == "user:cancel_token")
async def cb_user_cancel_token(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    _pending_token_choice.pop(query.from_user.id, None)
    text = f"👋 <b>أهلاً {query.from_user.full_name}!</b>\nاختار من القائمة 👇"
    await _edit_or_send(query, text, reply_markup=kbs.kb_user_main())
    await query.answer("اتلغى")


@factory_dp.callback_query(F.data == "user:my_bots")
async def cb_user_my_bots(query: CallbackQuery) -> None:
    if not await enforce_subscription(query.from_user.id, query.message.chat.id):
        await query.answer()
        return
    tokens = storage.load_tokens()
    mine = [(bid, t) for bid, t in tokens.items() if t.get("owner_id") == query.from_user.id]
    if not mine:
        await _edit_or_send(
            query,
            "🟦 لسه ماعندكش بوتات معتمدة.\nابعت توكن من «➕ إضافة بوت ريأكشن جديد».",
            reply_markup=kbs.kb_back("user:home"),
        )
        await query.answer()
        return

    bots_for_kb = [
        (bid, info.get("username", ""), bid in running_bots)
        for bid, info in mine
    ]
    text = (
        "<b>🤖 بوتاتك:</b>\n\n"
        "اضغط على أي بوت عشان تعدّل إعداداته (نوع الريأكشن، إلخ)."
    )
    await _edit_or_send(query, text, reply_markup=kbs.kb_my_bots(bots_for_kb))
    await query.answer()


@factory_dp.callback_query(F.data.startswith("bot:open:"))
async def cb_bot_open(query: CallbackQuery) -> None:
    bot_id = query.data.split(":", 2)[2]
    tokens = storage.load_tokens()
    info = tokens.get(bot_id)
    if not info or info.get("owner_id") != query.from_user.id:
        await query.answer("🟥 البوت ده مش بتاعك", show_alert=True)
        return
    rtype = info.get("reaction_type") or "mixed"
    from reactions import get_reaction_label
    running = "🟢 شغال" if bot_id in running_bots else "🔴 متوقف"
    text = (
        f"⚙️ <b>إعدادات البوت</b>\n\n"
        f"🤖 @{info.get('username','?')}\n"
        f"الحالة: {running}\n"
        f"🎭 نوع الريأكشن الحالي: <b>{get_reaction_label(rtype)}</b>"
    )
    await _edit_or_send(query, text, reply_markup=kbs.kb_bot_settings(bot_id))
    await query.answer()


@factory_dp.callback_query(F.data.startswith("bot:rtype:"))
async def cb_bot_rtype(query: CallbackQuery) -> None:
    bot_id = query.data.split(":", 2)[2]
    tokens = storage.load_tokens()
    info = tokens.get(bot_id)
    if not info or info.get("owner_id") != query.from_user.id:
        await query.answer("🟥 مش بتاعك", show_alert=True)
        return
    current = info.get("reaction_type") or "mixed"
    text = (
        "🎭 <b>اختار نوع الريأكشن</b>\n\n"
        "النوع ده هو اللي البوت هيستخدمه على المنشورات في كل قنواتك.\n"
        "تقدر تغيّره في أي وقت."
    )
    await _edit_or_send(
        query, text,
        reply_markup=kbs.kb_change_reaction_types(bot_id, current=current),
    )
    await query.answer()


@factory_dp.callback_query(F.data.startswith("rchg:"))
async def cb_bot_rtype_set(query: CallbackQuery) -> None:
    parts = query.data.split(":", 2)
    if len(parts) != 3:
        await query.answer()
        return
    _, bot_id, new_type = parts
    tokens = storage.load_tokens()
    info = tokens.get(bot_id)
    if not info or info.get("owner_id") != query.from_user.id:
        await query.answer("🟥 مش بتاعك", show_alert=True)
        return
    storage.set_reaction_type(bot_id, new_type)
    from reactions import get_reaction_label
    await query.answer(f"✅ اتغيّر إلى: {get_reaction_label(new_type)}")
    # حدّث نفس الرسالة بدل ما نبعت جديدة
    info = storage.load_tokens().get(bot_id, info)
    running = "🟢 شغال" if bot_id in running_bots else "🔴 متوقف"
    text = (
        f"⚙️ <b>إعدادات البوت</b>\n\n"
        f"🤖 @{info.get('username','?')}\n"
        f"الحالة: {running}\n"
        f"🎭 نوع الريأكشن الحالي: <b>{get_reaction_label(new_type)}</b>\n\n"
        f"🟩 تم الحفظ."
    )
    await _edit_or_send(query, text, reply_markup=kbs.kb_bot_settings(bot_id))

@factory_dp.callback_query(F.data == "user:help")
async def cb_user_help(query: CallbackQuery) -> None:
    text = (
        "ℹ️ <b>إزاي تستخدم المصنع؟</b>\n\n"
        "1. روح @BotFather واعمل بوت جديد.\n"
        "2. خد التوكن وابعتهولي.\n"
        "3. اختار نوع الريأكشن اللي عايز البوت يحطه.\n"
        "4. استنى المطور يوافق.\n"
        "5. ضيف البوت بتاعك <b>أدمن</b> في القناة.\n"
        "6. هيبدأ يحط ريأكشنز تلقائي على كل منشور 🎉\n"
    )
    await _edit_or_send(query, text, reply_markup=kbs.kb_back("user:home"))
    await query.answer()


# ─── استقبال التوكن (FSM) ──────────────────────────

@factory_dp.message(UserStates.waiting_token, F.text)
async def on_token_message(message: Message, state: FSMContext) -> None:
    if not await enforce_subscription(message.from_user.id, message.chat.id):
        return

    text = (message.text or "").strip()

    # رسالة الحالة الموحّدة — هنفضل نعدّلها بدل ما نبعت رسائل جديدة
    status_msg = await message.answer("🟦 بتأكد من التوكن...")

    if not is_valid_token_format(text):
        await status_msg.edit_text(
            "🟥 ده مش شكل توكن صحيح.\n"
            "التوكن لازم يبقى زي: <code>123456789:AAH...XYZ</code>\n\n"
            "ابعت توكن تاني أو ألغِ.",
            parse_mode="HTML",
            reply_markup=kbs.kb_cancel_action("user:cancel_token"),
        )
        return

    if storage.token_exists(text):
        await status_msg.edit_text(
            "🟥 التوكن ده متسجل قبل كده.",
            reply_markup=kbs.kb_back("user:home"),
        )
        await state.clear()
        return

    info = await verify_token(text)
    if not info:
        await status_msg.edit_text(
            "🟥 التوكن غلط أو البوت موقوف.",
            reply_markup=kbs.kb_back("user:home"),
        )
        await state.clear()
        return

    bot_id = str(info["id"])
    owner = message.from_user
    owner_name = owner.full_name + (f" (@{owner.username})" if owner.username else "")

    # نخزن البيانات مؤقتاً ونروح خطوة اختيار النوع — بدون رسالة جديدة
    _pending_token_choice[owner.id] = {
        "bot_id": bot_id,
        "token": text,
        "username": info["username"],
        "first_name": info["first_name"],
        "owner_id": owner.id,
        "owner_name": owner_name,
        "status_chat_id": status_msg.chat.id,
        "status_message_id": status_msg.message_id,
    }
    await state.set_state(UserStates.choosing_reaction)

    await status_msg.edit_text(
        f"🟩 التوكن صحيح!\n"
        f"🤖 <b>{info['first_name']}</b> (@{info['username']})\n\n"
        f"🎭 <b>اختار نوع الريأكشن</b> اللي عايز البوت يحطه على المنشورات:",
        parse_mode="HTML",
        reply_markup=kbs.kb_reaction_types(),
    )


@factory_dp.callback_query(UserStates.choosing_reaction, F.data.startswith("rtype:"))
async def cb_choose_reaction(query: CallbackQuery, state: FSMContext) -> None:
    rtype = query.data.split(":", 1)[1]
    pending = _pending_token_choice.get(query.from_user.id)
    if not pending:
        await query.answer("🟥 الجلسة انتهت، ابدأ من جديد", show_alert=True)
        await state.clear()
        return

    from reactions import REACTION_TYPES, get_reaction_label
    if rtype not in REACTION_TYPES:
        await query.answer("🟥 نوع غير معروف", show_alert=True)
        return

    # سجّل الطلب في pending مع نوع الريأكشن
    storage.add_pending(pending["bot_id"], {
        "token": pending["token"],
        "username": pending["username"],
        "first_name": pending["first_name"],
        "owner_id": pending["owner_id"],
        "owner_name": pending["owner_name"],
        "reaction_type": rtype,
    })

    _pending_token_choice.pop(query.from_user.id, None)
    await state.clear()

    # عدّل نفس الرسالة → تأكيد الإرسال
    confirm_text = (
        f"🟩 تم إرسال طلبك للمطور.\n\n"
        f"🤖 <b>{pending['first_name']}</b> (@{pending['username']})\n"
        f"🎭 نوع الريأكشن: <b>{get_reaction_label(rtype)}</b>\n\n"
        f"⏳ في انتظار الموافقة..."
    )
    await _edit_or_send(query, confirm_text, reply_markup=kbs.kb_back("user:home"))
    await query.answer("✅ تم الإرسال")

    admin_text = (
        "🆕 <b>طلب بوت جديد</b>\n\n"
        f"🤖 البوت: <b>{pending['first_name']}</b>\n"
        f"   @{pending['username']}\n"
        f"   ID: <code>{pending['bot_id']}</code>\n\n"
        f"🎭 نوع الريأكشن: <b>{get_reaction_label(rtype)}</b>\n\n"
        f"👤 صاحب الطلب: {pending['owner_name']}\n"
        f"   ID: <code>{pending['owner_id']}</code>"
    )
    try:
        await factory_bot.send_message(
            ADMIN_USER_ID, admin_text, parse_mode="HTML",
            reply_markup=kbs.kb_approve(pending["bot_id"]),
        )
    except TelegramAPIError as e:
        log.error("فشل إرسال إشعار للأدمن: %s", e)



# ─── موافقة / رفض ──────────────────────────────────

@factory_dp.callback_query(F.data.startswith("approve:"))
async def cb_approve(query: CallbackQuery) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("🟥 مش مسموح", show_alert=True)
        return

    bot_id = query.data.split(":", 1)[1]
    pending = storage.pop_pending(bot_id)
    if not pending:
        await query.answer("🟥 الطلب مش موجود", show_alert=True)
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    storage.add_token(
        bot_id=bot_id, token=pending["token"],
        username=pending["username"], first_name=pending["first_name"],
        owner_id=pending["owner_id"], owner_name=pending["owner_name"],
        reaction_type=pending.get("reaction_type", "mixed"),
    )

    label = f"@{pending['username']}" if pending["username"] else bot_id
    started = await start_reactor(bot_id, pending["token"], label)

    new_text = (query.message.html_text or "") + (
        "\n\n🟩 <b>اتقبل وبدأ يشتغل!</b>" if started
        else "\n\n🟥 <b>اتقبل بس فشل في التشغيل</b>"
    )
    try:
        await query.message.edit_text(new_text, parse_mode="HTML", reply_markup=None)
    except Exception:
        pass

    from reactions import get_reaction_label
    rtype_label = get_reaction_label(pending.get("reaction_type", "mixed"))
    try:
        await factory_bot.send_message(
            pending["owner_id"],
            f"🟩 <b>اتقبل بوتك!</b>\n\n"
            f"🤖 @{pending['username']} شغال دلوقتي\n"
            f"🎭 نوع الريأكشن: <b>{rtype_label}</b>\n"
            f"📌 ضيفه أدمن في أي قناة وهيبدأ يحط ريأكشنز تلقائياً.\n\n"
            f"💡 تقدر تغيّر نوع الريأكشن في أي وقت من «🤖 بوتاتي».",
            parse_mode="HTML",
        )
    except TelegramAPIError:
        pass

    await query.answer("🟩 تم القبول")


@factory_dp.callback_query(F.data.startswith("reject:"))
async def cb_reject(query: CallbackQuery) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("🟥 مش مسموح", show_alert=True)
        return

    bot_id = query.data.split(":", 1)[1]
    pending = storage.pop_pending(bot_id)
    if not pending:
        await query.answer("🟥 الطلب مش موجود", show_alert=True)
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    new_text = (query.message.html_text or "") + "\n\n🟥 <b>اترفض</b>"
    try:
        await query.message.edit_text(new_text, parse_mode="HTML", reply_markup=None)
    except Exception:
        pass

    try:
        await factory_bot.send_message(
            pending["owner_id"],
            "🟥 المطور رفض طلبك.\nممكن تحاول تكلمه مباشرة لو حابب.",
        )
    except TelegramAPIError:
        pass

    await query.answer("🟥 تم الرفض")


# ─── قائمة المطور ──────────────────────────────────

@factory_dp.callback_query(F.data == "adm:home")
async def cb_adm_home(query: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("🟥 مش مسموح", show_alert=True)
        return
    await state.clear()
    try:
        await query.message.edit_text(
            "👑 <b>قائمة المطور</b>\nاختار العملية:",
            parse_mode="HTML", reply_markup=kbs.kb_admin_main(),
        )
    except Exception:
        await query.message.answer(
            "👑 <b>قائمة المطور</b>\nاختار العملية:",
            parse_mode="HTML", reply_markup=kbs.kb_admin_main(),
        )
    await query.answer()


@factory_dp.callback_query(F.data == "adm:stats")
async def cb_adm_stats(query: CallbackQuery) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("🟥 مش مسموح", show_alert=True)
        return
    tokens = storage.load_tokens()
    pending = storage.load_pending()
    users = storage.load_users()
    fsub = storage.load_force_sub()

    # احسب إجمالي القنوات عبر كل البوتات
    total_channels = 0
    for bid in tokens.keys():
        total_channels += len(storage.load_channels(bid))

    text = (
        "📊 <b>إحصائيات المصنع</b>\n\n"
        f"🟦 البوتات الشغالة: <b>{len(running_bots)}</b>\n"
        f"🟦 البوتات المعتمدة: <b>{len(tokens)}</b>\n"
        f"🟦 طلبات معلقة: <b>{len(pending)}</b>\n"
        f"🟦 المستخدمين: <b>{len(users)}</b>\n"
        f"🟦 إجمالي القنوات: <b>{total_channels}</b>\n"
        f"🟦 قنوات اشتراك إجباري: <b>{len(fsub)}</b>"
    )
    try:
        await query.message.edit_text(
            text, parse_mode="HTML", reply_markup=kbs.kb_admin_back(),
        )
    except Exception:
        await query.message.answer(
            text, parse_mode="HTML", reply_markup=kbs.kb_admin_back(),
        )
    await query.answer()


@factory_dp.callback_query(F.data == "adm:bots")
async def cb_adm_bots(query: CallbackQuery) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("🟥 مش مسموح", show_alert=True)
        return
    tokens = storage.load_tokens()
    if not tokens:
        text = "🟦 مفيش بوتات معتمدة لحد دلوقتي."
    else:
        lines = ["<b>🤖 البوتات المعتمدة:</b>\n"]
        for bid, info in tokens.items():
            running = "🟢" if bid in running_bots else "🔴"
            lines.append(
                f"{running} @{info.get('username','?')}\n"
                f"   ID: <code>{bid}</code>\n"
                f"   👤 {info.get('owner_name','?')}"
            )
        text = "\n".join(lines)
    try:
        await query.message.edit_text(
            text, parse_mode="HTML", reply_markup=kbs.kb_admin_back(),
        )
    except Exception:
        await query.message.answer(
            text, parse_mode="HTML", reply_markup=kbs.kb_admin_back(),
        )
    await query.answer()


@factory_dp.callback_query(F.data == "adm:pending")
async def cb_adm_pending(query: CallbackQuery) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("🟥 مش مسموح", show_alert=True)
        return
    pending = storage.load_pending()
    if not pending:
        try:
            await query.message.edit_text(
                "🟦 مفيش طلبات معلقة.", reply_markup=kbs.kb_admin_back(),
            )
        except Exception:
            await query.message.answer(
                "🟦 مفيش طلبات معلقة.", reply_markup=kbs.kb_admin_back(),
            )
        await query.answer()
        return

    await query.answer()
    for bid, info in pending.items():
        text = (
            "⏳ <b>طلب معلق</b>\n\n"
            f"🤖 <b>{info.get('first_name','?')}</b> (@{info.get('username','?')})\n"
            f"   ID: <code>{bid}</code>\n"
            f"👤 {info.get('owner_name','?')}"
        )
        await query.message.answer(
            text, parse_mode="HTML", reply_markup=kbs.kb_approve(bid),
        )


@factory_dp.callback_query(F.data == "adm:users")
async def cb_adm_users(query: CallbackQuery) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("🟥 مش مسموح", show_alert=True)
        return
    users = storage.load_users()
    if not users:
        text = "🟦 مفيش مستخدمين متسجلين لسه."
    else:
        lines = [f"<b>👥 المستخدمين ({len(users)}):</b>\n"]
        # نعرض أول 30 بس عشان ما نتجاوزش حد الرسالة
        items = list(users.items())[:30]
        for uid, u in items:
            name = u.get("name", "?")
            uname = u.get("username", "")
            tag = f" @{uname}" if uname else ""
            lines.append(f"• {name}{tag} — <code>{uid}</code>")
        if len(users) > 30:
            lines.append(f"\n... و{len(users) - 30} مستخدم تاني")
        text = "\n".join(lines)
    try:
        await query.message.edit_text(
            text, parse_mode="HTML", reply_markup=kbs.kb_admin_back(),
        )
    except Exception:
        await query.message.answer(
            text, parse_mode="HTML", reply_markup=kbs.kb_admin_back(),
        )
    await query.answer()


# ─── الإذاعة ───────────────────────────────────────

@factory_dp.callback_query(F.data == "adm:broadcast")
async def cb_adm_broadcast(query: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("🟥 مش مسموح", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_broadcast)
    text = (
        "📡 <b>إذاعة رسالة</b>\n\n"
        "ابعتلي دلوقتي الرسالة اللي عايز تذيعها.\n"
        "هتتبعت لـ:\n"
        "🟦 كل المستخدمين اللي ضغطوا /start على المصنع\n"
        "🟦 كل القنوات اللي البوتات الفرعية فيها\n\n"
        "<i>تقدر تبعت نص أو صورة أو فيديو أو أي حاجة.</i>"
    )
    try:
        await query.message.edit_text(
            text, parse_mode="HTML",
            reply_markup=kbs.kb_cancel_action("adm:home"),
        )
    except Exception:
        await query.message.answer(
            text, parse_mode="HTML",
            reply_markup=kbs.kb_cancel_action("adm:home"),
        )
    await query.answer()


@factory_dp.message(AdminStates.waiting_broadcast)
async def on_broadcast_message(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()

    user_ids = storage.all_user_ids()
    tokens = storage.load_tokens()

    # احسب القنوات
    channels_per_bot: dict[str, list[str]] = {}
    total_channels = 0
    for bid in tokens.keys():
        chs = list(storage.load_channels(bid).keys())
        channels_per_bot[bid] = chs
        total_channels += len(chs)

    status = await message.answer(
        f"📡 بدأت الإذاعة...\n"
        f"🟦 مستخدمين: {len(user_ids)}\n"
        f"🟦 قنوات: {total_channels}",
    )

    # 1) إذاعة لكل المستخدمين عبر البوت الرئيسي
    sent_users = 0
    failed_users = 0
    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            sent_users += 1
        except TelegramAPIError:
            failed_users += 1
        await asyncio.sleep(0.05)  # حماية من الحظر

    # 2) إذاعة لكل القنوات عبر كل بوت فرعي شغال
    sent_channels = 0
    failed_channels = 0
    for bid, chat_ids in channels_per_bot.items():
        rb = running_bots.get(bid)
        if not rb or not chat_ids:
            continue
        for cid in chat_ids:
            try:
                await message.copy_to(chat_id=int(cid))
                # نبعت من البوت الرئيسي للمستخدمين، لكن للقنوات لازم البوت الفرعي
                # نعيد ونرسل من البوت الفرعي:
            except TelegramAPIError:
                pass
            try:
                # استخدم البوت الفرعي للنشر في قناته
                await rb.bot.copy_message(
                    chat_id=int(cid),
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
                sent_channels += 1
            except TelegramAPIError:
                failed_channels += 1
            await asyncio.sleep(0.05)

    summary = (
        "🟩 <b>الإذاعة خلصت</b>\n\n"
        f"👥 مستخدمين: ✅ {sent_users} | ❌ {failed_users}\n"
        f"📢 قنوات: ✅ {sent_channels} | ❌ {failed_channels}"
    )
    try:
        await status.edit_text(
            summary, parse_mode="HTML", reply_markup=kbs.kb_admin_back(),
        )
    except Exception:
        await message.answer(
            summary, parse_mode="HTML", reply_markup=kbs.kb_admin_back(),
        )


# ─── إدارة قنوات الاشتراك الإجباري ────────────────

@factory_dp.callback_query(F.data == "adm:fsub")
async def cb_adm_fsub(query: CallbackQuery) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("🟥 مش مسموح", show_alert=True)
        return
    channels = storage.load_force_sub()
    if not channels:
        text = (
            "🔒 <b>قنوات الاشتراك الإجباري</b>\n\n"
            "🟦 مفيش قنوات لسه. اضغط «➕ إضافة قناة»."
        )
    else:
        lines = ["🔒 <b>قنوات الاشتراك الإجباري</b>\n"]
        for c in channels:
            uname = c.get("username", "")
            tag = f" — @{uname}" if uname else ""
            lines.append(f"• <b>{c.get('title','قناة')}</b>{tag}\n  <code>{c['id']}</code>")
        text = "\n".join(lines)
    try:
        await query.message.edit_text(
            text, parse_mode="HTML", reply_markup=kbs.kb_fsub_admin(channels),
        )
    except Exception:
        await query.message.answer(
            text, parse_mode="HTML", reply_markup=kbs.kb_fsub_admin(channels),
        )
    await query.answer()


@factory_dp.callback_query(F.data == "fsub_adm:add")
async def cb_fsub_add(query: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("🟥 مش مسموح", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_fsub_channel)
    text = (
        "➕ <b>إضافة قناة اشتراك إجباري</b>\n\n"
        "ابعتلي يوزر القناة (مثلاً <code>@mychannel</code>) أو الـ ID العددي.\n\n"
        "<b>مهم:</b> لازم البوت الرئيسي يكون <b>أدمن</b> في القناة دي عشان يقدر يفحص اشتراك المستخدمين."
    )
    try:
        await query.message.edit_text(
            text, parse_mode="HTML",
            reply_markup=kbs.kb_cancel_action("adm:fsub"),
        )
    except Exception:
        await query.message.answer(
            text, parse_mode="HTML",
            reply_markup=kbs.kb_cancel_action("adm:fsub"),
        )
    await query.answer()


@factory_dp.message(AdminStates.waiting_fsub_channel, F.text)
async def on_fsub_channel_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").strip()
    target: str | int = raw
    if raw.startswith("@"):
        target = raw
    elif raw.lstrip("-").isdigit():
        target = int(raw)
    else:
        target = "@" + raw

    try:
        chat = await factory_bot.get_chat(target)
    except TelegramAPIError as e:
        await message.answer(
            f"🟥 ماقدرتش أوصل للقناة: <code>{e}</code>\n"
            f"تأكد إن البوت أدمن فيها.",
            parse_mode="HTML",
            reply_markup=kbs.kb_cancel_action("adm:fsub"),
        )
        return

    invite_url = ""
    try:
        # حاول نجيب invite link لو القناة خاصة
        if not chat.username:
            link = await factory_bot.create_chat_invite_link(chat.id)
            invite_url = link.invite_link or ""
    except TelegramAPIError:
        invite_url = ""

    added = storage.add_force_sub({
        "id": chat.id,
        "title": chat.title or str(chat.id),
        "username": chat.username or "",
        "invite": invite_url,
    })
    await state.clear()

    if added:
        await message.answer(
            f"🟩 اتضافت: <b>{chat.title}</b>",
            parse_mode="HTML", reply_markup=kbs.kb_admin_back(),
        )
    else:
        await message.answer(
            "🟦 القناة دي متضافة قبل كده.",
            reply_markup=kbs.kb_admin_back(),
        )


@factory_dp.callback_query(F.data.startswith("fsub_adm:del:"))
async def cb_fsub_del(query: CallbackQuery) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("🟥 مش مسموح", show_alert=True)
        return
    cid = query.data.split(":", 2)[2]
    removed = storage.remove_force_sub(cid)
    if removed:
        await query.answer(f"🟩 اتشالت: {removed.get('title','')}")
    else:
        await query.answer("🟥 مش موجودة")
    # حدّث القائمة
    await cb_adm_fsub(query)


# ─── Bootstrap ──────────────────────────────────────

async def restore_saved_bots() -> None:
    tokens = storage.load_tokens()
    if not tokens:
        log.info("📭 مفيش بوتات محفوظة.")
        return
    log.info("♻️ بأعيد تشغيل %d بوت محفوظ...", len(tokens))
    for bot_id, info in tokens.items():
        if not info.get("active", True):
            continue
        label = f"@{info.get('username', bot_id)}"
        await start_reactor(bot_id, info["token"], label)


async def main() -> None:
    print("\n╔═══════════════════════════════════════╗")
    print("║   🏭  Reactor Bot Factory — Python   ║")
    print("╚═══════════════════════════════════════╝\n")

    try:
        me = await factory_bot.get_me()
        print(f"✅ المصنع: {me.first_name} (@{me.username})")
        print(f"👑 الأدمن: {ADMIN_USER_ID}\n")
    except TelegramAPIError as e:
        print(f"❌ توكن المصنع غلط! {e}")
        sys.exit(1)

    await factory_bot.delete_webhook(drop_pending_updates=False)
    await restore_saved_bots()

    log.info("🔄 المصنع شغال... (Ctrl+C للإيقاف)\n")

    try:
        await factory_dp.start_polling(
            factory_bot,
            allowed_updates=["message", "callback_query"],
        )
    finally:
        log.info("🛑 بأوقف كل البوتات...")
        for bid in list(running_bots.keys()):
            await stop_reactor(bid)
        try:
            await factory_bot.session.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 المصنع اتقفل.")
