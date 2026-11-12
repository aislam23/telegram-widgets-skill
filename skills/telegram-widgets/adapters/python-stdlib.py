"""
Adapter: Python 3.9+, standard library only (no bot framework).

    BOT_TOKEN=123:abc python3 python-stdlib.py <chat_id> widget.html

sends the widget, then long-polls for widget_query updates and answers them with "ok".
Use it to try a widget before wiring it into your framework. Never print API URLs: they contain
the token.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import zlib

API = "https://api.telegram.org/bot{token}/{method}"   # test server: .../bot{token}/test/{method}


class TelegramError(Exception):
    pass


def call(token: str, method: str, http_timeout: float = 60, **params) -> object:
    body = json.dumps({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(API.format(token=token, method=method), data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=http_timeout) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:            # do not re-raise e: its text holds the URL
        payload = json.load(e)
    except urllib.error.URLError as e:
        raise TelegramError(f"{method}: network error {type(e.reason).__name__}") from None
    if not payload.get("ok"):
        raise TelegramError(f"{method}: {payload.get('description')}")
    return payload["result"]


def send_widget(token: str, chat_id: int, html: str, chat_data: str = "", caption: str = "",
                public_data: str | None = None, allow_queries: bool = True) -> dict:
    size = len(zlib.compress(html.encode(), 9))
    if size > 4096:
        raise ValueError(f"widget is {size} bytes compressed, limit 4096")
    return call(token, "sendWidget", chat_id=chat_id, html=html, chat_data=chat_data or None,
                public_data=public_data, caption=caption or None, allow_queries=allow_queries)


def edit_widget_data(token: str, chat_id: int, message_id: int, chat_data: str) -> None:
    call(token, "editMessageWidgetData", chat_id=chat_id, message_id=message_id, chat_data=chat_data)


def answer_widget_query(token: str, query_id: str, data: str | None = None) -> None:
    call(token, "answerWidgetQuery", widget_query_id=query_id, data=data)


def poll(token: str):
    offset = None
    while True:
        # allowed_updates must list the widget updates explicitly
        updates = call(token, "getUpdates", http_timeout=70, offset=offset, timeout=50,
                       allowed_updates=["message", "widget_query", "shared_widget_query"])
        for u in updates:
            offset = u["update_id"] + 1
            yield u


if __name__ == "__main__":
    token = os.environ["BOT_TOKEN"]
    chat_id, path = int(sys.argv[1]), sys.argv[2]
    msg = send_widget(token, chat_id, open(path, encoding="utf-8").read(),
                      chat_data='{"m":"e"}', caption="Widget test")
    print("sent message", msg["message_id"])
    for update in poll(token):
        q = update.get("widget_query") or update.get("shared_widget_query")
        if q:
            print("query from", q["from"]["id"], "data", repr(q.get("data")))
            answer_widget_query(token, q["id"], "ok")
