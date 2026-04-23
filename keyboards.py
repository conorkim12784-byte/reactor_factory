"""
🎨 مكتبة الأزرار الـ Inline — تستخدم حقل `style` الجديد في Bot API 9.x

   primary  → 🔵 أزرق  (القوايم / التنقل / المعلومات)
   success  → 🟢 أخضر (التأكيد / الموافقة / النجاح)
   danger   → 🔴 أحمر (الإلغاء / الرفض / الحذف / الخطأ)
   (بدون)   → ⚪ شفاف افتراضي

ملاحظة فنية:
aiogram لسه ما ضافش `style` كحقل رسمي في `InlineKeyboardButton`،
لكن Pydantic عنده `model_config.extra = "allow"` في aiogram، فبنبني الزر
بـ `model_construct` ونحقن `style` كحقل extra يتسرّل ويتبعت للـ Bot API
كما هو. لو سيرفر تليجرام ما دعمش الحقل (نسخة قديمة)، هيتجاهله ببساطة.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from reactions import REACTION_TYPES


# ─── بنّاء داخلي مع style ─────────────────────────

def _styled_button(
    text: str,
    *,
    style: str | None = None,
    callback_data: str | None = None,
    url: str | None = None,
) -> InlineKeyboardButton:
    """
    يبني InlineKeyboardButton ويضيف حقل `style` كـ extra field.
    نستخدم model_construct علشان نتخطى الـ validation الصارم
    ونسمح بحقول جديدة من Bot API لسه ما اتعملهاش mapping في aiogram.
    """
    fields: dict = {"text": text}
    if callback_data is not None:
        fields["callback_data"] = callback_data
    if url is not None:
        fields["url"] = url
    if style is not None:
        fields["style"] = style

    # Pydantic v2: model_construct يبني الـ instance من غير validation
    # وبيحتفظ بكل الحقول الـ extra لما الموديل عنده extra='allow'.
    try:
        btn = InlineKeyboardButton.model_construct(**fields)
    except Exception:
        # fallback آمن لو حصل أي مشكلة
        kwargs = {k: v for k, v in fields.items() if k != "style"}
        btn = InlineKeyboardButton(**kwargs)
        if style is not None:
            object.__setattr__(btn, "style", style)
    return btn


# ─── أنماط الأزرار ────────────────────────────────

def btn_primary(text: str, callback_data: str) -> InlineKeyboardButton:
    """🔵 زر معلومات / قائمة / تنقل."""
    return _styled_button(text, style="primary", callback_data=callback_data)


def btn_success(text: str, callback_data: str) -> InlineKeyboardButton:
    """🟢 زر تأكيد / موافقة / إضافة / نجاح."""
    return _styled_button(text, style="success", callback_data=callback_data)


def btn_danger(text: str, callback_data: str) -> InlineKeyboardButton:
    """🔴 زر إلغاء / رفض / حذف / خطأ."""
    return _styled_button(text, style="danger", callback_data=callback_data)


def btn_plain(text: str, callback_data: str) -> InlineKeyboardButton:
    """⚪ زر شفاف بدون لون."""
    return _styled_button(text, callback_data=callback_data)


def btn_url(text: str, url: str, style: str | None = "primary") -> InlineKeyboardButton:
    """🔵 رابط خارجي (افتراضياً أزرق)."""
    return _styled_button(text, style=style, url=url)


def kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


# ─── كيبوردات جاهزة ───────────────────────────────

def kb_user_main() -> InlineKeyboardMarkup:
    """القائمة الرئيسية للمستخدم العادي."""
    return kb(
        [btn_primary("➕ إضافة بوت ريأكشن جديد", "user:add_bot")],
        [btn_primary("🤖 بوتاتي", "user:my_bots")],
        [btn_primary("ℹ️ مساعدة", "user:help")],
    )


def kb_admin_main() -> InlineKeyboardMarkup:
    """قائمة المطور (تظهر للأدمن فقط)."""
    return kb(
        [btn_primary("📊 إحصائيات المصنع", "adm:stats")],
        [btn_primary("🤖 البوتات المعتمدة", "adm:bots")],
        [btn_primary("⏳ طلبات الموافقة", "adm:pending")],
        [btn_primary("📡 إذاعة رسالة", "adm:broadcast")],
        [btn_primary("🔒 قنوات الاشتراك الإجباري", "adm:fsub")],
        [btn_primary("👥 المستخدمين", "adm:users")],
    )


def kb_back(target: str = "user:home") -> InlineKeyboardMarkup:
    return kb([btn_primary("🔙 رجوع", target)])


def kb_admin_back() -> InlineKeyboardMarkup:
    return kb([btn_primary("🔙 رجوع لقائمة المطور", "adm:home")])


def kb_force_sub(channels: list[dict]) -> InlineKeyboardMarkup:
    """كيبورد قنوات الاشتراك الإجباري + زر تحقق."""
    rows: list[list[InlineKeyboardButton]] = []
    for c in channels:
        title = c.get("title") or "قناة"
        username = c.get("username", "")
        invite = c.get("invite", "")
        url = f"https://t.me/{username}" if username else invite
        if url:
            rows.append([btn_url(f"📢 {title}", url)])
    rows.append([btn_success("تحققت — اشتركت", "fsub:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_confirm(yes_cb: str, no_cb: str,
               yes_text: str = "تأكيد", no_text: str = "إلغاء") -> InlineKeyboardMarkup:
    return kb([
        btn_success(yes_text, yes_cb),
        btn_danger(no_text, no_cb),
    ])


def kb_approve(bot_id: str) -> InlineKeyboardMarkup:
    return kb([
        btn_success("موافقة", f"approve:{bot_id}"),
        btn_danger("رفض", f"reject:{bot_id}"),
    ])


def kb_fsub_admin(channels: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [btn_success("➕ إضافة قناة", "fsub_adm:add")],
    ]
    for c in channels:
        title = c.get("title") or "قناة"
        cid = str(c["id"])
        rows.append([btn_danger(f"حذف: {title}", f"fsub_adm:del:{cid}")])
    rows.append([btn_primary("🔙 رجوع لقائمة المطور", "adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_cancel_action(target: str = "adm:home") -> InlineKeyboardMarkup:
    return kb([btn_danger("إلغاء", target)])


def kb_reaction_types(current: str | None = None) -> InlineKeyboardMarkup:
    """
    كيبورد اختيار نوع الريأكشن.
    callback_data بصيغة: rtype:<key>
    لو current = key لنوع، نحط علامة ✓ جنبه.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for key, info in REACTION_TYPES.items():
        label = info["label"]
        if current and current == key:
            label = f"✅ {label}"
        rows.append([btn_primary(label, f"rtype:{key}")])
    rows.append([btn_danger("إلغاء", "user:cancel_token")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_change_reaction_types(bot_id: str, current: str | None = None) -> InlineKeyboardMarkup:
    """
    لما المستخدم يغيّر نوع الريأكشن لبوت موجود.
    callback_data بصيغة: rchg:<bot_id>:<key>
    """
    rows: list[list[InlineKeyboardButton]] = []
    for key, info in REACTION_TYPES.items():
        label = info["label"]
        if current and current == key:
            label = f"✅ {label}"
        rows.append([btn_primary(label, f"rchg:{bot_id}:{key}")])
    rows.append([btn_primary("🔙 رجوع لبوتاتي", "user:my_bots")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_my_bots(bots: list[tuple[str, str, bool]]) -> InlineKeyboardMarkup:
    """
    bots: list of (bot_id, username, is_running)
    كل بوت بيبقى زر يوديك على صفحة إعداداته.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for bid, uname, running in bots:
        dot = "🟢" if running else "🔴"
        rows.append([btn_primary(f"{dot} @{uname or bid}", f"bot:open:{bid}")])
    rows.append([btn_primary("🔙 رجوع", "user:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_bot_settings(bot_id: str) -> InlineKeyboardMarkup:
    return kb(
        [btn_primary("🎭 تغيير نوع الريأكشن", f"bot:rtype:{bot_id}")],
        [btn_primary("🔙 رجوع لبوتاتي", "user:my_bots")],
    )

