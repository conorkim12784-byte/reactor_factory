"""
إدارة ملفات JSON: التوكنز + القنوات لكل بوت + طلبات الموافقة المعلقة
+ المستخدمين (للإذاعة) + قنوات الاشتراك الإجباري
"""
import json
import os
from datetime import datetime
from typing import Any
from config import (
    TOKENS_FILE, PENDING_FILE, USERS_FILE, FORCE_SUB_FILE, CHANNELS_DIR,
)


# ─── أدوات مساعدة ──────────────────────────────────

def _ensure_dir() -> None:
    os.makedirs(CHANNELS_DIR, exist_ok=True)


def _load_json(path: str, default=None):
    if not os.path.exists(path):
        return {} if default is None else default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, OSError):
        return {} if default is None else default


def _save_json(path: str, data) -> None:
    _ensure_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── توكنز البوتات المعتمدة ─────────────────────────

def load_tokens() -> dict:
    return _load_json(TOKENS_FILE, {})


def save_tokens(tokens: dict) -> None:
    _save_json(TOKENS_FILE, tokens)


def add_token(bot_id: str, token: str, username: str, first_name: str,
              owner_id: int, owner_name: str) -> None:
    tokens = load_tokens()
    tokens[bot_id] = {
        "token": token,
        "username": username,
        "first_name": first_name,
        "owner_id": owner_id,
        "owner_name": owner_name,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "active": True,
    }
    save_tokens(tokens)


def remove_token(bot_id: str) -> None:
    tokens = load_tokens()
    if bot_id in tokens:
        del tokens[bot_id]
        save_tokens(tokens)


def token_exists(token: str) -> bool:
    tokens = load_tokens()
    return any(t.get("token") == token for t in tokens.values())


# ─── طلبات الموافقة المعلقة ────────────────────────

def load_pending() -> dict:
    return _load_json(PENDING_FILE, {})


def save_pending(pending: dict) -> None:
    _save_json(PENDING_FILE, pending)


def add_pending(bot_id: str, data: dict) -> None:
    pending = load_pending()
    pending[bot_id] = data
    save_pending(pending)


def pop_pending(bot_id: str) -> dict | None:
    pending = load_pending()
    item = pending.pop(bot_id, None)
    save_pending(pending)
    return item


# ─── المستخدمين (للإذاعة) ──────────────────────────

def load_users() -> dict:
    """{ "<user_id>": {"name": "...", "username": "...", "joined_at": "..."} }"""
    return _load_json(USERS_FILE, {})


def add_user(user_id: int, name: str = "", username: str = "") -> bool:
    """يرجّع True لو المستخدم جديد."""
    users = load_users()
    uid = str(user_id)
    if uid in users:
        return False
    users[uid] = {
        "name": name,
        "username": username,
        "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_json(USERS_FILE, users)
    return True


def all_user_ids() -> list[int]:
    return [int(uid) for uid in load_users().keys()]


# ─── الاشتراك الإجباري (قنوات المطور) ──────────────

def load_force_sub() -> list[dict]:
    """[{"id": -1001..., "title": "...", "username": "...", "invite": "https://..."}]"""
    data = _load_json(FORCE_SUB_FILE, [])
    return data if isinstance(data, list) else []


def save_force_sub(channels: list[dict]) -> None:
    _save_json(FORCE_SUB_FILE, channels)


def add_force_sub(channel: dict) -> bool:
    channels = load_force_sub()
    cid = str(channel["id"])
    if any(str(c["id"]) == cid for c in channels):
        return False
    channels.append(channel)
    save_force_sub(channels)
    return True


def remove_force_sub(channel_id: str) -> dict | None:
    channels = load_force_sub()
    cid = str(channel_id)
    for i, c in enumerate(channels):
        if str(c["id"]) == cid:
            removed = channels.pop(i)
            save_force_sub(channels)
            return removed
    return None


# ─── قنوات كل بوت لوحده ─────────────────────────────

def _channels_path(bot_id: str) -> str:
    _ensure_dir()
    return os.path.join(CHANNELS_DIR, f"channels_{bot_id}.json")


def load_channels(bot_id: str) -> dict:
    return _load_json(_channels_path(bot_id), {})


def save_channels(bot_id: str, channels: dict) -> None:
    _save_json(_channels_path(bot_id), channels)


def add_channel(bot_id: str, chat: dict) -> bool:
    channels = load_channels(bot_id)
    chat_id = str(chat["id"])
    if chat_id in channels:
        return False
    channels[chat_id] = {
        "id": chat_id,
        "title": chat.get("title", chat_id),
        "username": chat.get("username", ""),
        "verified": bool(chat.get("is_verified", False)),
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_channels(bot_id, channels)
    return True


def remove_channel(bot_id: str, chat_id: str) -> dict | None:
    channels = load_channels(bot_id)
    item = channels.pop(chat_id, None)
    if item is not None:
        save_channels(bot_id, channels)
    return item


def channel_exists(bot_id: str, chat_id: str) -> bool:
    return chat_id in load_channels(bot_id)


def get_channel(bot_id: str, chat_id: str) -> dict | None:
    return load_channels(bot_id).get(chat_id)
