#!/usr/bin/env python3
"""
Local browser preview of a Telegram widget: wraps it with theme variables and a TelegramWidget stub
(the approach recommended in the official guide). Layout and logic only: a browser draws features
Telegram removes and renders canvas differently, so always verify in real Telegram afterwards.

    python3 preview_widget.py widget.html --chat-data '{"m":"e"}' --public-data texts.json \
        --out preview.html [--dark] [--answer ok] [--width 360]

--public-data / --chat-data accept a JSON string or a path to a file with it.
Requests are logged to the console and to window.__requests, and resolve with {result: --answer}.
"""
from __future__ import annotations

import argparse
import json
import os

LIGHT = {"bg-color": "#ffffff", "text-color": "#000000", "hint-color": "#707579", "link-color": "#3390ec",
         "button-color": "#3390ec", "button-text-color": "#ffffff", "secondary-bg-color": "#f1f1f4",
         "accent-text-color": "#3390ec", "subtitle-text-color": "#707579", "destructive-text-color": "#e53935",
         "section-separator-color": "#e7e7e7"}
DARK = {"bg-color": "#212d3b", "text-color": "#ffffff", "hint-color": "#7d8b99", "link-color": "#62bcf9",
        "button-color": "#50a8eb", "button-text-color": "#ffffff", "secondary-bg-color": "#2b3a4a",
        "accent-text-color": "#62bcf9", "subtitle-text-color": "#7d8b99", "destructive-text-color": "#ee686f",
        "section-separator-color": "#33414f"}


def load(value: str | None) -> str | None:
    if value is None:
        return None
    if os.path.exists(value):
        return open(value, encoding="utf-8").read().strip()
    return value


def build(widget_html: str, chat_data: str | None, public_data: str | None, dark: bool,
          answer: str, width: int) -> str:
    theme = DARK if dark else LIGHT
    css_vars = ";".join(f"--tg-theme-{k}:{v}" for k, v in theme.items())
    params = {k.replace("-", "_"): v for k, v in theme.items()}
    stub = f"""
window.__requests = [];
window.TelegramWidget = {{
  profile: 1, isProfileAtLeast: n => n <= 1, colorScheme: {json.dumps('dark' if dark else 'light')},
  themeParams: Object.freeze({json.dumps(params)}), isActive: true, isPreview: false, isForward: false,
  chatType: 'private', viewer: {{ id: 1, first_name: 'Preview' }},
  chatData: {json.dumps(chat_data)}, publicData: {json.dumps(public_data)}, wallet: null,
  contentSafeAreaInset: {{ top: 0, right: 0, bottom: 0, left: 0, cornerLeft: 0, cornerRight: 0 }},
  HapticFeedback: {{ impactOccurred() {{ return this; }}, notificationOccurred() {{ return this; }}, selectionChanged() {{ return this; }} }},
  _h: {{}},
  onEvent(t, f) {{ (this._h[t] = this._h[t] || []).push(f); }}, offEvent() {{}},
  ready() {{}}, setResizeAnchor() {{}}, watchPublicData() {{}}, unwatchPublicData() {{}},
  openLink: u => console.log('openLink', u), openTelegramLink: u => console.log('openTelegramLink', u),
  copyText: t => console.log('copyText', t),
  request(d) {{ console.log('request', d); window.__requests.push(d);
    return new Promise(r => setTimeout(() => r({{ result: {json.dumps(answer)} }}), 150)); }},
}};
// Simulate a bot edit from the console: __setChatData('{{"m":"p","p":40}}')
window.__setChatData = s => {{ TelegramWidget.chatData = s; (TelegramWidget._h.chatDataChanged || []).forEach(f => f.call(TelegramWidget)); }};
"""
    return f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Widget preview</title>
<style>
html{{background:#8fa98c}}
.bubble{{width:{width}px;max-width:calc(100vw - 32px);margin:24px auto;border-radius:16px;overflow:hidden;
  background:var(--tg-theme-bg-color);color:var(--tg-theme-text-color);font:15px/1.35 system-ui,sans-serif;{css_vars}}}
.bubble button{{font:inherit;border:0;border-radius:8px;padding:9px;background:var(--tg-theme-button-color);color:var(--tg-theme-button-text-color)}}
</style>
<div class="bubble" style="{css_vars}"><div style="margin:8px 12px">
<script>{stub}</script>
{widget_html}
</div></div>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--chat-data")
    ap.add_argument("--public-data")
    ap.add_argument("--out", default="preview.html")
    ap.add_argument("--dark", action="store_true")
    ap.add_argument("--answer", default="ok")
    ap.add_argument("--width", type=int, default=360)
    a = ap.parse_args()
    html = open(a.file, encoding="utf-8").read()
    page = build(html, load(a.chat_data), load(a.public_data), a.dark, a.answer, a.width)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"wrote {a.out}; open it in a browser at 320-430 px width")


if __name__ == "__main__":
    main()
