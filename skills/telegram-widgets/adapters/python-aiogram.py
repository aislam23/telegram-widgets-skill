"""
Adapter: Python + aiogram 3.x (which predates Bot API 10.4 widgets).

Drop this module into your bot and:
  1. dp.update.outer_middleware(WidgetQueryMiddleware(handle_widget_query))
  2. await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types() + WIDGET_UPDATES)
  3. send with `await send_widget(...)`, update with WidgetMessage.push()/stage()/done()/fail(),
     answer every query with `await answer(bot, query_id, "ok")` within 15 seconds.

Verified live on aiogram 3.20: sendWidget, editMessageWidgetData, editMessageCaption on a widget,
deleteMessage, widget_query delivery through the outer middleware.
"""
import asyncio
import json
import re
import time
import zlib
from typing import Any, Awaitable, Callable, Dict, Optional, Union

from aiogram import BaseMiddleware, Bot
from aiogram.client.default import Default
from aiogram.methods.base import TelegramMethod
from aiogram.types import InlineKeyboardMarkup, Message, ReplyParameters, TelegramObject

WIDGET_UPDATES = ["widget_query", "shared_widget_query"]
ZLIB_BUDGET = 4000          # hard limit 4096 after zlib level 9; keep headroom
DATA_LIMIT = 1024           # chat_data / public_data / answer, bytes of UTF-8
EDIT_INTERVAL = 2.0         # seconds between throttled progress edits


# ---------- Bot API methods aiogram does not know yet ----------

class SendWidget(TelegramMethod[Message]):
    __returning__ = Message
    __api_method__ = "sendWidget"

    chat_id: Union[int, str]
    html: str
    width: Optional[int] = None
    height: Optional[int] = None
    public_data: Optional[str] = None
    chat_data: Optional[str] = None
    caption: Optional[str] = None
    parse_mode: Optional[Union[str, Default]] = Default("parse_mode")
    show_caption_above_media: Optional[bool] = None
    allow_queries: Optional[bool] = None
    is_shared: Optional[bool] = None
    disable_notification: Optional[bool] = None
    protect_content: Optional[bool] = None
    reply_parameters: Optional[ReplyParameters] = None
    reply_markup: Optional[InlineKeyboardMarkup] = None


class SendSharedWidget(TelegramMethod[Message]):
    __returning__ = Message
    __api_method__ = "sendSharedWidget"

    chat_id: Union[int, str]
    widget_id: str
    chat_data: Optional[str] = None
    caption: Optional[str] = None
    parse_mode: Optional[Union[str, Default]] = Default("parse_mode")
    reply_parameters: Optional[ReplyParameters] = None
    reply_markup: Optional[InlineKeyboardMarkup] = None


class EditMessageWidgetData(TelegramMethod[bool]):
    __returning__ = bool
    __api_method__ = "editMessageWidgetData"

    chat_id: Optional[Union[int, str]] = None
    message_id: Optional[int] = None
    inline_message_id: Optional[str] = None
    public_data: Optional[str] = None
    chat_data: Optional[str] = None


class EditSharedWidgetData(TelegramMethod[bool]):
    __returning__ = bool
    __api_method__ = "editSharedWidgetData"

    widget_id: str
    public_data: str
    cache_time: Optional[int] = None


class AnswerWidgetQuery(TelegramMethod[bool]):
    __returning__ = bool
    __api_method__ = "answerWidgetQuery"

    widget_query_id: str
    data: Optional[str] = None


# ---------- receiving queries ----------

class WidgetQueryMiddleware(BaseMiddleware):
    """aiogram keeps unknown update fields in Update.model_extra and would drop the update as an
    unknown type. This outer middleware runs first and hands the raw dict to your handler."""

    def __init__(self, handler: Callable[[Bot, dict, bool], Awaitable[None]]):
        self.handler = handler

    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: Dict[str, Any]) -> Any:
        extra = getattr(event, "model_extra", None) or {}
        if "widget_query" in extra:
            return await self.handler(data["bot"], extra["widget_query"], False)
        if "shared_widget_query" in extra:
            return await self.handler(data["bot"], extra["shared_widget_query"], True)
        return await handler(event, data)


async def answer(bot: Bot, query_id: str, text: Optional[str] = None) -> None:
    """Answer every query, also on errors. Never raises: a failed answer must not break the job."""
    try:
        await bot(AnswerWidgetQuery(widget_query_id=query_id, data=text[:DATA_LIMIT] if text else None))
    except Exception:
        pass


def parse_request(pattern: re.Pattern, data: str) -> Optional[re.Match]:
    """Request data is untrusted: anchored pattern, explicit length cap. Clamp numbers after this."""
    if not data or len(data.encode()) > 64:
        return None
    return pattern.fullmatch(data)


# ---------- sending and updating ----------

def compressed_size(html: str) -> int:
    return len(zlib.compress(html.encode("utf-8"), 9))


def state_json(state: dict) -> str:
    data = json.dumps({k: v for k, v in state.items() if v is not None},
                      ensure_ascii=False, separators=(",", ":"))
    if len(data.encode("utf-8")) > DATA_LIMIT:
        raise ValueError(f"widget state is {len(data.encode())} bytes, limit {DATA_LIMIT}")
    return data


class WidgetMessage:
    """Authoritative state of one widget message. Edits are serialized, errors are terminal."""

    def __init__(self, bot: Bot, chat_id: int, message_id: int, state: dict, caption: str = ""):
        self.bot, self.chat_id, self.message_id = bot, chat_id, message_id
        self.state, self.caption = dict(state), caption
        self.failed = False
        self._lock = asyncio.Lock()
        self._last = 0.0

    @property
    def key(self) -> tuple[int, int]:
        return self.chat_id, self.message_id

    async def push(self, force: bool = True, terminal: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last < EDIT_INTERVAL:
            return                       # every edit counts against the bot's message limits
        self._last = now
        data = state_json(self.state)
        async with self._lock:
            if self.failed and not terminal:
                return                   # a late progress edit must not overwrite the error
            try:
                await self.bot(EditMessageWidgetData(
                    chat_id=self.chat_id, message_id=self.message_id, chat_data=data))
            except Exception as e:
                if "not modified" not in str(e).lower():
                    raise

    async def set_caption(self, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None,
                          terminal: bool = False) -> None:
        if text == self.caption and reply_markup is None:
            return
        async with self._lock:
            if self.failed and not terminal:
                return
            await self.bot.edit_message_caption(chat_id=self.chat_id, message_id=self.message_id,
                                                caption=text[:1024], reply_markup=reply_markup)
            self.caption = text

    async def progress(self, percent: Optional[float]) -> None:
        stage_changed = self.state.get("m") != "p"
        self.state.update(m="p", p=None if percent is None else round(percent))
        await self.push(force=stage_changed)

    async def done(self, **fields: Any) -> None:
        self.state.update(m="d", p=None, **fields)
        await self.push()

    async def fail(self, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None,
                   title: Optional[str] = None) -> None:
        """Short title in the widget, full text and buttons in the caption. Pass only safe text:
        see public_reason()."""
        self.failed = True
        self.state.update(m="x", p=None, t=title)
        await self.push(terminal=True)
        await self.set_caption(text, reply_markup, terminal=True)


async def send_widget(bot: Bot, chat_id: int, html: str, state: dict, caption: str, *,
                      public_data: Optional[str] = None, reply_to: Optional[int] = None,
                      allow_queries: bool = True) -> Optional[WidgetMessage]:
    """None when the widget could not be sent: fall back to your old text UI."""
    if compressed_size(html) > ZLIB_BUDGET:
        return None
    try:
        msg = await bot(SendWidget(
            chat_id=chat_id, html=html, chat_data=state_json(state), public_data=public_data,
            caption=caption, allow_queries=allow_queries,
            reply_parameters=ReplyParameters(message_id=reply_to, allow_sending_without_reply=True)
            if reply_to else None))
    except Exception:
        return None
    return WidgetMessage(bot, chat_id, msg.message_id, state, caption)


# ---------- never leak the token ----------

_URL = re.compile(r"https?://\S+")


def public_reason(e: BaseException, token: str) -> str:
    """HTTP client errors include the request URL, and Bot API file URLs contain the bot token.
    Use this for anything shown to users; TimeoutError has an empty str()."""
    text = _URL.sub("<link hidden>", str(e) or type(e).__name__)
    if token and len(token) > 20:              # real tokens are ~46 chars
        text = text.replace(token, "<token hidden>")
    return text[:200]


# ---------- example handler ----------
#
# GO = re.compile(r"go:(\d)")
# busy: set[tuple[int, int]] = set()
# owners: dict[tuple[int, int], int] = {}        # persist in Redis/DB in production
#
# async def handle_widget_query(bot: Bot, q: dict, shared: bool) -> None:
#     chat_id = (q.get("chat") or {}).get("id"); message_id = q.get("message_id")
#     user_id = (q.get("from") or {}).get("id")
#     key = (chat_id, message_id)
#     if shared or owners.get(key) != user_id:
#         return await answer(bot, q["id"], "Not available")
#     m = parse_request(GO, q.get("data", ""))
#     if m is None:
#         return await answer(bot, q["id"], "Unknown action")
#     option = min(int(m.group(1)), 2)
#     if key in busy:
#         return await answer(bot, q["id"], "Already working")
#     busy.add(key)
#     await answer(bot, q["id"], "ok")              # answer first, work after
#     asyncio.create_task(run_job(bot, key, option)) # keep a reference; discard key in finally
