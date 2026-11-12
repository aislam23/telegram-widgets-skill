---
name: telegram-widgets
description: Build, ship and secure Telegram Bot API 10.4+ HTML widgets, the interactive mini-UIs a bot sends inside a chat message (sendWidget, sendSharedWidget, answerWidgetQuery, editMessageWidgetData, editSharedWidgetData, widget_query and shared_widget_query updates, the TelegramWidget JavaScript object). Language- and framework-agnostic; works for bots in Python, Node.js, Go, PHP or anything that speaks HTTP. Use this skill whenever a user wants to add an interactive message, live progress bar, poll, picker, editor, mini-game, ticker, counter or quiz to a Telegram bot, migrate callback-button flows to widgets, debug a widget that looks different in Telegram than in a browser, or hits INPUT_MEDIA_WIDGET_TOO_LARGE, BUSY, NOT_ALLOWED or TIMEOUT, even if they only say "make the bot message interactive" and never say "widget".
---

# Telegram widgets

A widget is one self-contained HTML document that a bot sends as a message. Telegram apps run it on the
user's device in a QuickJS sandbox with no network, draw it in the chat's colors and keep it alive while
it is on screen. The widget **cannot change its own state**: only the bot writes state, and the widget
can only *ask* the bot with tiny requests. Everything in this skill follows from that split.

```
 bot ──sendWidget(html, chat_data, public_data)──▶ message ──▶ widget runs on the device
 bot ◀──────────── widget_query (≤64 bytes, on a tap) ─────── widget
 bot ──answerWidgetQuery (≤1024 bytes, to the asker only)──▶ widget (its promise resolves)
 bot ──editMessageWidgetData (new state)────────────────────▶ widget gets chatDataChanged
```

The bot side is plain HTTPS calls to the Bot API, so this works in any language. Official docs:
https://core.telegram.org/bots/widgets and https://core.telegram.org/bots/api. Re-read them if they are
newer than this skill: the feature is rolling out in steps and limits may change.

## What to read

| You need | Read |
|---|---|
| Methods, fields, limits, allowed HTML/CSS/JS, the `TelegramWidget` API | `references/platform.md` |
| Security checklist (for every widget) | `references/security.md` |
| Bugs that only appear in real Telegram, and their fixes | `references/pitfalls.md` |
| Bot-side architecture in pseudocode (any language) | `references/server-side.md` |
| Reaching widget calls from a framework that predates 10.4 | `references/frameworks.md` |
| Proven designs: live progress, editor with autostart, poll, ticker | `references/patterns.md` |
| Size checks, local preview, live test plan | `references/testing.md` |

Files to start from:
- `templates/widget-skeleton.html`: the widget side, safe defaults built in.
- `adapters/`: working bot-side code for Python + aiogram, Python stdlib, Node.js (fetch) and curl.
  Use the one matching the user's stack, or port it: the logic is the same everywhere.
- `scripts/check_widget.py`: compressed size and forbidden-feature lint (needs Python 3 to run, checks
  widgets for bots in any language). `scripts/preview_widget.py`: local browser preview with a stub.

## Workflow

Follow the steps in order. Most real failures came from skipping step 1 or step 6.

### 1. Check where the widget will live

As of Bot API 10.4 **production supports widgets only in the private chat with the bot**. Groups, inline
mode and forwarding work only on the test server, and production widgets are automatically
`protect_content` (cannot be forwarded). Channels never accept widgets. If the plan depends on groups,
inline results or viral forwarding, say so up front and design a private-chat version or an explicit
test-server path.

Check the user's bot library. Most libraries released before 10.4 do not know the new methods or the
`widget_query` update; `references/frameworks.md` shows the escape hatches.

### 2. Design the protocol before writing HTML

Write it down as a comment in the bot code:

- **chat_data** (per message, ≤1024 bytes UTF-8): what the widget renders. Compact JSON with short keys
  and a mode field, e.g. `{"m":"p","st":1,"p":64}`. The bot holds the authoritative copy and always
  sends the whole object.
- **public_data** (≤1024 bytes): shared state, or, for a static widget, a free slot for constant data
  such as UI strings (see the size budget).
- **requests** (1–64 bytes): a tiny grammar such as `h`, `g:x,y,z,s`, `f`. Each must be answerable in
  well under 15 seconds; slow work happens after answering.
- **answers** (≤1024 bytes): what the widget shows immediately (`ok` or a short error sentence).
- **modes**: which state the bot pushes when, and what the widget shows in each, including errors and
  waiting states.

Non-Latin text costs 2–3 bytes per character in every budget.

### 3. Plan the 4 KB budget

The HTML may be 32 KB raw but must be **≤4096 bytes after zlib level 9**, counted by the server. Aim for
≤4000. A typical spend: CSS ~450 B, logic 1.5–2.5 KB, ~400 B for twenty Russian UI strings, the rest for
images. Tactics in order of payoff:

1. Move constant UI strings into `public_data` (static widgets) and index them (`T[3]`).
2. Prefer SVG and CSS to images; `data:` images barely compress.
3. If an image is essential, make it server-side and shrink it in a loop until the compressed HTML fits
   (WebP first, JPEG fallback). See `references/patterns.md` §7.
4. Hand-minify: short identifiers, no comments, shared helpers. Minifiers save only 5–10%.

Run `python3 scripts/check_widget.py widget.html` after every change.

### 4. Build the widget from the skeleton

Start from `templates/widget-skeleton.html`. It already handles what broke in practice: it renders
synchronously from `TelegramWidget.chatData` and on `chatDataChanged`; it keeps one request in flight,
queues a primary action pressed meanwhile, catches synchronous throws and resets flags on rejection; it
writes non-constant text with `textContent`; it uses theme variables; it runs outside Telegram for
previews.

Rules that are easy to forget (details in `references/platform.md`):

- `request()`, `openLink()`, `copyText()` only inside a **click or pointerup** handler, synchronously.
  One tap unlocks one call. In the private chat a few background requests are allowed without a tap.
- Vertical drags always scroll the chat. The widget gets taps, and horizontal drags only on elements
  with `touch-action: pan-y`. On `pointercancel`, undo whatever `pointerdown` started.
- The leading 20 px never claim gestures (system back swipe).
- No `<input>`, `<select>`, `<video>`, `<audio>`, `<iframe>`, no `fetch`, no `vh`, no `color-mix()`,
  no `oklch()`, no `overflow: auto`, no web fonts. `<button>` is the only form control.
- At most 16 elements with `opacity < 1`, filters or blurred shadows at once: mute with colors.
- Height 50–600 px and nothing scrolls inside; stay under ~560 px at 320 px width.
- Canvas: no hole-punching paths; dim everything, then clip and redraw (pitfall 1).
- Send a caption. Apps without widget support show only the caption, and with a caption below the
  widget the message time does not cover its corner.

### 5. Build the bot side

Follow `references/server-side.md` and start from the matching file in `adapters/`. Non-negotiables,
explained in `references/security.md`:

1. **Subscribe to the updates**: list `widget_query` (and `shared_widget_query` if used) in
   `allowed_updates`, or requests time out silently.
2. **Answer every query** with `answerWidgetQuery` within 15 s, also on errors, before slow work.
3. **Authorize**: match `from.id` with the owner stored for `(chat_id, message_id)`, or key by
   `(widget_id, from.id)` for shared widgets. `from` and `widget_id` cannot be forged; `data` can.
4. **Parse `data` strictly** with an anchored pattern and a length cap; clamp every number.
5. **Keep authoritative state on the server**, keyed by the message, persisted with a TTL when buttons
   must work after a restart. Commit a user's move only after the edit succeeded.
6. **Guard concurrency**: register busy and waiting records immediately after `sendWidget` returns,
   before any other await; serialize edits per message; make error states terminal; never hold a shared
   lock while waiting for a human.
7. **Respect rate limits**: each `editMessageWidgetData` counts as a sent message; push mode changes at
   once and percentages at most every 1–2 s. Shared widgets: one edit per second.
8. **Never leak secrets** in HTML, state, answers, captions, user-facing errors or logs. Raw exception
   text from HTTP clients can contain `https://api.telegram.org/file/bot<TOKEN>/…`.
9. **Fallback and kill switch**: if `sendWidget` fails, use the previous text/keyboard flow; keep a
   `WIDGETS_ENABLED` flag.

### 6. Verify in real Telegram, not only in a browser

A browser renders more than Telegram and hides renderer differences. Always:

1. `scripts/check_widget.py`: size and forbidden features pass.
2. `scripts/preview_widget.py`: every mode renders at 320–430 px, light and dark.
3. Send it from a test bot to a real account and walk through every mode, errors, a slow network, two
   quick taps, and scrolling the widget away and back (`references/testing.md`).
4. Tell the user exactly what was verified live and what was only previewed.

## Defaults when the user did not specify

- A static widget (`sendWidget` without `is_shared`) in the private chat; `allow_queries` only when the
  widget must talk to the bot.
- Always a caption that makes sense on its own.
- Long jobs: one widget per job, state pushed by the bot, percentages throttled.
- Choices with a sensible default: an editor that auto-continues with the default after a short
  countdown unless the user touches it (`references/patterns.md` §3).
- The old non-widget flow stays available behind a feature flag.
