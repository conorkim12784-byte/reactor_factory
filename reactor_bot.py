"""
كلاس البوت الفرعي (Reactor Bot) — نفس منطق الكود الـ PHP الأصلي:
- يتسجل في القنوات اللي يضاف فيها أدمن (my_chat_member)
- يحط ريأكشن عشوائي على كل منشور جديد (channel_post)
- يستخدم الريأكشنز المتاحة في القناة من getChat
- لو فشل → fallback ❤️
"""
import asyncio
import logging
import random
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    ChatMemberUpdated,
    Message,
    ReactionTypeCustomEmoji,
    ReactionTypeEmoji,
)

from config import REACTION_DELAY_MIN, REACTION_DELAY_MAX, MANUAL_PREMIUM
from reactions import NORMAL_REACTIONS, FALLBACK_EMOJI
import storage


log = logging.getLogger("reactor")


class ReactorBot:
    """بوت ريأكشن واحد — كل instance بيشتغل لوحده على توكن منفصل."""

    def __init__(self, token: str, bot_id: str, label: str = ""):
        self.token = token
        self.bot_id = bot_id
        self.label = label or bot_id
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self._task: asyncio.Task | None = None
        self._register_handlers()

    # ─── Handlers ──────────────────────────────────

    def _register_handlers(self) -> None:
        self.dp.my_chat_member.register(self._on_my_chat_member)
        self.dp.channel_post.register(self._on_channel_post)

    async def _on_my_chat_member(self, event: ChatMemberUpdated) -> None:
        """يتسجل/يشيل القناة لما البوت يبقى أدمن أو يتشال."""
        chat = event.chat
        if chat.type != "channel":
            return

        new_status = event.new_chat_member.status
        old_status = event.old_chat_member.status

        is_now_admin = new_status == "administrator"
        was_admin = old_status == "administrator"
        is_removed = new_status in ("left", "kicked", "member", "restricted")

        if is_now_admin and not was_admin:
            chat_dict = {
                "id": chat.id,
                "title": chat.title or str(chat.id),
                "username": chat.username or "",
                "is_verified": getattr(chat, "is_verified", False),
            }
            added = storage.add_channel(self.bot_id, chat_dict)
            if added:
                verified = chat_dict["is_verified"]
                tag = "💎 موثقة" if verified else "📢 عادية"
                log.info("[%s] ➕ قناة جديدة: %s (%s)", self.label, chat.title, tag)

        elif was_admin and (is_removed or not is_now_admin):
            removed = storage.remove_channel(self.bot_id, str(chat.id))
            if removed:
                log.info("[%s] ➖ قناة اتشالت: %s", self.label, removed.get("title"))

    async def _on_channel_post(self, message: Message) -> None:
        """يحط ريأكشن عشوائي على كل منشور."""
        # تجاهل المنشورات المعاد توجيهها
        if message.forward_origin or message.forward_from_chat:
            return

        chat = message.chat
        chat_id = str(chat.id)

        if not storage.channel_exists(self.bot_id, chat_id):
            return

        title = chat.title or chat_id
        is_premium = self._is_premium(chat)
        label = "💎 موثقة" if is_premium else "📢 عادية"

        # جيب الريأكشنز المتاحة من القناة مباشرة
        reaction, display = await self._pick_reaction(chat_id)

        log.info(
            "[%s] 📨 %s | %s | #%d | %s",
            self.label, label, title, message.message_id, display,
        )

        # تأخير عشوائي عشان يبان طبيعي
        await asyncio.sleep(random.randint(REACTION_DELAY_MIN, REACTION_DELAY_MAX))

        ok = await self._set_reaction(chat_id, message.message_id, reaction)
        if ok:
            log.info("[%s] ✅ تم ✓", self.label)
            return

        # fallback ❤️
        log.warning("[%s] ⚠️ فشل الريأكشن، بحط ❤️...", self.label)
        ok2 = await self._set_reaction(
            chat_id, message.message_id, ReactionTypeEmoji(emoji=FALLBACK_EMOJI)
        )
        log.info("[%s] %s", self.label, "✅ بديل [❤️] ✓" if ok2 else "❌ فشل نهائياً")

    # ─── Helpers ───────────────────────────────────

    def _is_premium(self, chat: Any) -> bool:
        chat_id = str(chat.id)
        username = chat.username or ""

        if chat_id in MANUAL_PREMIUM or (username and username in MANUAL_PREMIUM):
            return True

        saved = storage.get_channel(self.bot_id, chat_id)
        if saved and saved.get("verified"):
            return True

        if getattr(chat, "is_verified", False):
            return True

        return False

    async def _pick_reaction(self, chat_id: str) -> tuple:
        """
        يجيب الريأكشنز المتاحة من القناة ويختار واحد منها.
        يرجّع (reaction_object, display_string).
        """
        try:
            chat_full = await self.bot.get_chat(chat_id)
            available = chat_full.available_reactions
        except TelegramAPIError:
            available = None

        # القناة بتسمح بـ "all" أو مفيش بيانات → استخدم العادية
        if not available or (
            isinstance(available, list) and len(available) == 0
        ):
            emoji = random.choice(NORMAL_REACTIONS)
            return ReactionTypeEmoji(emoji=emoji), emoji

        # available list of ReactionType objects (Emoji or CustomEmoji)
        try:
            pick = random.choice(available)
        except Exception:
            emoji = random.choice(NORMAL_REACTIONS)
            return ReactionTypeEmoji(emoji=emoji), emoji

        # نوع custom_emoji
        if hasattr(pick, "custom_emoji_id") and pick.custom_emoji_id:
            return (
                ReactionTypeCustomEmoji(custom_emoji_id=pick.custom_emoji_id),
                f"custom:{pick.custom_emoji_id}",
            )

        # نوع emoji عادي
        if hasattr(pick, "emoji") and pick.emoji:
            return ReactionTypeEmoji(emoji=pick.emoji), pick.emoji

        # fallback
        emoji = random.choice(NORMAL_REACTIONS)
        return ReactionTypeEmoji(emoji=emoji), emoji

    async def _set_reaction(self, chat_id: str, msg_id: int, reaction) -> bool:
        try:
            await self.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=msg_id,
                reaction=[reaction],
                is_big=False,
            )
            return True
        except TelegramAPIError as e:
            log.debug("[%s] set_reaction failed: %s", self.label, e)
            return False

    # ─── حلقة التشغيل ──────────────────────────────

    async def _run(self) -> None:
        try:
            await self.bot.delete_webhook(drop_pending_updates=False)
            log.info("[%s] 🟢 البوت بدأ يستقبل المنشورات...", self.label)
            await self.dp.start_polling(
                self.bot,
                allowed_updates=["channel_post", "my_chat_member"],
                handle_signals=False,
            )
        except asyncio.CancelledError:
            log.info("[%s] 🛑 اتوقف.", self.label)
            raise
        except Exception as e:
            log.exception("[%s] ❌ خطأ: %s", self.label, e)
        finally:
            try:
                await self.bot.session.close()
            except Exception:
                pass

    def start(self) -> asyncio.Task:
        """يبدأ البوت كـ background task."""
        if self._task and not self._task.done():
            return self._task
        self._task = asyncio.create_task(self._run(), name=f"reactor-{self.bot_id}")
        return self._task

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            await self.dp.stop_polling()
        except Exception:
            pass
        try:
            await self.bot.session.close()
        except Exception:
            pass
