# Platform reference (Bot API 10.4, widget profile 1)

Condensed from the official guide (https://core.telegram.org/bots/widgets) and API reference
(https://core.telegram.org/bots/api). Check the originals for anything newer.

## Contents
1. Availability
2. Bot API methods
3. Types and updates
4. Limits
5. The TelegramWidget object
6. What the sandbox supports (profile 1)
7. Layout, gestures, lifecycle

## 1. Availability

| Place | How | Requests | Chat state | Production |
|---|---|---|---|---|
| Private chat with the bot | `sendWidget` | on a tap and in the background | per user | yes |
| Group / supergroup (bot is a member) | `sendWidget` | on a tap only | one for all members | test server only |
| Any chat except channels, via the bot | inline mode | on a tap only | per sent message | test server only |
| A forward, any chat | forwarded by users | on a tap, shared widgets only | none | test server only |

- In production, sent widgets automatically have protected content and cannot be forwarded.
- Channels refuse widgets, directly and via the bot.
- Groups need the bot to have `can_send_other_messages`.
- Apps without widget support show the message as unsupported media with its caption.
- `copyMessage` / `copyMessages` refuse widget messages.

## 2. Bot API methods

### sendWidget → Message
| Parameter | Notes |
|---|---|
| `chat_id` | required |
| `html` | required, 1–32768 bytes UTF-8, ≤4096 bytes after zlib level 9, no NUL |
| `width`, `height` | optional size anchors in logical px; width clamped to 200..bubble max, height to 50..600; omit for automatic |
| `public_data`, `chat_data` | optional, 0–1024 bytes each |
| `caption`, `parse_mode`, `caption_entities`, `show_caption_above_media` | as for media |
| `allow_queries` | let the widget send requests; without it every request is refused everywhere |
| `is_shared` | create a shared widget; its id comes back as `message.widget.id` |
| `message_thread_id`, `disable_notification`, `protect_content`, `allow_paid_broadcast`, `message_effect_id`, `reply_parameters`, `reply_markup` | as usual |

Errors: `INPUT_MEDIA_WIDGET_TOO_LARGE` (raw or compressed size), `INPUT_MEDIA_WIDGET_HTML_INVALID`
(NUL / bad UTF-8), `INPUT_MEDIA_WIDGET_DATA_TOO_LARGE`, `INPUT_MEDIA_WIDGET_DATA_INVALID`.

### sendSharedWidget → Message
`chat_id`, `widget_id` (required); `chat_data`, caption fields, `message_thread_id`,
`disable_notification`, `protect_content`, `allow_paid_broadcast`, `message_effect_id`,
`reply_parameters`, `reply_markup`.

### answerWidgetQuery → True
`widget_query_id` (required), `data` (0–1024 bytes). Must be called within 15 s (also the query id
lifetime; a late answer fails with "query is too old"). The answer reaches only the widget that asked
and never changes state.

### editMessageWidgetData → True
`chat_id` + `message_id`, or `inline_message_id`; `public_data`, `chat_data` (0–1024 bytes; omitted =
unchanged, empty string = cleared). Counts as one sent message against the bot's limits. Editing to the
same value fails with "message is not modified": treat as success.

### editSharedWidgetData → True
`widget_id`, `public_data` (required), `cache_time` (5–3600 s, default 30, the client refresh period).
At most one edit per second per shared widget.

### Also works on widget messages
`editMessageCaption` (verified live), `editMessageReplyMarkup`, `deleteMessage`. The HTML itself can
never be replaced: for a new layout send a new widget.

## 3. Types and updates

- `Message.widget`: `Widget` with `html`, optional `id` (shared only), `width`, `height`,
  `public_data`, `chat_data`.
- `Update.widget_query`: `WidgetQuery` from an original message.
- `Update.shared_widget_query`: `SharedWidgetQuery` from a forwarded shared widget.
- `WidgetQuery`: `id`, `from`, `chat`?, `message_id`?, `inline_message_id`?, `chat_instance`,
  `chat_type`? (inline only), `type` (`WidgetQueryType`), `data` (1–64 bytes), `widget_id`? (shared).
- `SharedWidgetQuery`: `id`, `from`, `type`, `data`, `widget_id`. No chat, no message.
- `WidgetQueryType`: `{"type":"data", "wallet_card"?}`, `{"type":"sign_data","wallet",...}`,
  `{"type":"sent_transaction","wallet","msg_hash"}`.
- Inline results: `InputWidgetMessageContent` (sendWidget fields) and
  `InputSharedWidgetMessageContent` (`widget_id`, `chat_data`, caption fields). Test server only.
- If you pass `allowed_updates`, include `widget_query` and `shared_widget_query`.

## 4. Limits

| What | Limit | Beyond it |
|---|---|---|
| HTML | 32768 bytes UTF-8 | INPUT_MEDIA_WIDGET_TOO_LARGE |
| Compressed HTML | 4096 bytes, zlib level 9 (Python's zlib matches the server) | INPUT_MEDIA_WIDGET_TOO_LARGE |
| chat_data / public_data | 1024 bytes UTF-8 each | ..._DATA_TOO_LARGE |
| Request data | 1–64 bytes UTF-8 | TypeError in the widget |
| Answer data | 1024 bytes | WIDGET_RESULT_TOO_LARGE |
| Time to answer | 15 s | TIMEOUT in the widget |
| Requests per user and bot | 5 per 5 s, background included | RATE_LIMITED |
| Requests per widget | one in flight, one per tap | BUSY / NOT_ALLOWED |
| Background requests | private chat, while visible: one on appear, then one per 5 s | NOT_ALLOWED / RATE_LIMITED |
| Shared widget edits | 1 per second | flood wait |
| Bubble | width 200..max, height 50..600, clipped | clipped |
| localStorage / sessionStorage | 4 KB per area per message | QuotaExceededError |
| JS CPU | 300 ms per second; one task ≤500 ms | slowed / stopped |
| Memory | 8 MB | stopped ("Widget stopped") |
| DOM | 2000 nodes, 10000 changes per task | stopped |
| Timers | 64 live | RangeError |
| CSS | 400 rules, 32 @keyframes | stopped |
| Canvas | 4000 commands per canvas per task; 2048×2048 px total | RangeError / stopped |
| data: images | 1024×1024 px | placeholder |
| Heavy elements | 16 with opacity<1, filter, blurred shadow, backdrop-filter (max 2) | stopped |
| Script animations | 64 | not drawn |
| Crashes | 2 in a row | stays stopped until app restart |

## 5. The TelegramWidget object

Exists before the first script line inside Telegram; `undefined` in a plain browser.

Properties: `profile` (1), `colorScheme` (`light`/`dark`), `themeParams` (`bg_color`, `text_color`,
`hint_color`, `link_color`, `button_color`, `button_text_color`, `secondary_bg_color`,
`accent_text_color`, `subtitle_text_color`, `destructive_text_color`, …), `isActive`, `isPreview`,
`isForward`, `chatType` (null in forwards/previews), `viewer` (`id`, `first_name`, `last_name`,
`username`, `is_premium`; only where the widget may send requests), `publicData`, `chatData`
(strings or null), `contentSafeAreaInset`, `wallet`, `HapticFeedback`.

Methods: `isProfileAtLeast(n)`, `request(data[, {wallet:true}])` → Promise<{result}>,
`copyText(text)`, `openLink(url)`, `openTelegramLink(url)`, `watchPublicData()`,
`unwatchPublicData()`, `setResizeAnchor('top'|'bottom')` (check `typeof` first), `ready()`,
`onEvent(type, fn)`, `offEvent(type, fn)`. There is no `sendMessage`.

Events: `themeChanged`, `activated`, `deactivated`, `chatDataChanged`, `publicDataChanged`,
`contentSafeAreaChanged`.

Request errors (`error.name === 'WidgetRequestError'`, `error.code`): `NOT_ALLOWED`, `BUSY`,
`RATE_LIMITED`, `TIMEOUT`, `FAILED`, `INVALID_ANSWER`; wallet calls add `REJECTED`, `BAD_REQUEST`.

CSS variables on the root (inline, `!important`): `--tg-theme-<key>` for every themeParams key,
`--tg-color-scheme`, `--tg-text-font-size`, `--tg-text-line-height`, `--tg-text-padding`,
`--tg-button-*`, `--tg-content-safe-area-inset-*`, `--tg-content-safe-area-corner-left/right`.

## 6. What the sandbox supports (profile 1)

**HTML in**: div, span, p, br, hr, h1–h6, header, footer, main, nav, section, article, aside, pre,
blockquote, figure, figcaption, inline text tags, lists, tables, details/summary, `<img>` with a
`data:` PNG/JPEG/GIF/WebP, `<canvas>`, `<button>`, `<a href="#id">`, `<a href="https://…">`,
attributes class/id/style/title/hidden/lang/dir/data-*/aria-* and inline `on*` handlers.
**HTML out**: all form controls except button, progress, meter, dialog, popovers, audio, video,
iframe, object, embed, external `<script src>`, link, meta, template, `data:` SVG images.

**SVG in**: shapes, paths, g, defs, symbol, use, transforms, text/tspan, gradients, CSS on SVG.
**SVG out**: clipPath, mask, pattern, marker, filter primitives, SMIL, foreignObject, `<image>`.

**CSS in**: block/inline/flex/grid/tables, positioning (fixed = inside the bubble), z-index,
aspect-ratio, overflow hidden/clip, borders, radius, box-shadow, opacity, gradients, 2D transforms,
blur/brightness/drop-shadow filters, generic font families only, tabular-nums, transitions,
keyframes, px/em/rem/%/ch/vw/vmin/vmax, calc/min/max/clamp, custom properties,
`env(safe-area-inset-*)`, structural pseudo-classes, `:is/:where/:not`, `::before/::after`, `:active`,
`:hover` (mouse only), `@media` on width/orientation/prefers-color-scheme/prefers-reduced-motion,
`@supports`, `touch-action` auto/pan-y/none, `light-dark()`.
**CSS out**: vh and other height units, overflow auto/scroll (become hidden), sticky (becomes
relative), logical properties, multi-column, display contents/flow-root, 3D transforms, clip-path,
masks, blend modes, text-shadow, line-clamp, background-clip:text, `color-mix()`, `oklch()` and other
modern color functions, web fonts, `@import`, `@container`, `@layer`, nesting, `:has()`, `:focus*`,
`:checked`.

**JS in**: ES2023 (QuickJS, no JIT), Promises, timers, rAF, DOM (createElement, innerHTML,
classList, dataset, style, addEventListener, MutationObserver, ResizeObserver), layout reads
(cache them; 128 per task max), Canvas 2D (paths, Path2D, gradients, text, drawImage of `data:`
images, transforms, clipping), Web Animations, Intl, crypto.getRandomValues, TextEncoder, URL,
structuredClone, localStorage/sessionStorage.
**JS out**: every network API (throws NetworkDisabledError), location/history, alert/confirm/prompt,
clipboard (use copyText), share, geolocation, media devices, Blob, FileReader, createObjectURL,
fullscreen, focus, getImageData/putImageData, toDataURL, createPattern, canvas shadows,
globalCompositeOperation, ctx.filter, WebGL, OffscreenCanvas.

**Input**: click, pointer events with setPointerCapture, dblclick, contextmenu on
`touch-action: none`. No touch events, no keyboard, no wheel/scroll events.

## 7. Layout, gestures, lifecycle

- The widget fills the bubble with no padding of its own; `body` gets the app's text padding as its
  margin (about 8px 12px). `body{margin:0}` goes edge to edge.
- Unstyled `<button>` looks like the client's own button.
- Width 200–600 px (phones ~320–430): design for 320. Height 50–600 px, content beyond is clipped.
- Time in the corner: with no caption below, the app draws the time over the bottom corner.
  Default styles pad an unstyled body; if you pad yourself, set `body{padding:0}` and use
  `env(safe-area-inset-bottom)` and `--tg-content-safe-area-corner-right/left`.
- Gestures: taps and double taps are always the widget's. Vertical drags are always the chat's
  (the widget gets `pointercancel`). Holds and horizontal drags are claimed per element:
  `auto` → chat (menu, swipe-to-reply), `pan-y` → widget gets horizontal drags, `none` → widget
  gets drags and holds. The first 10 px of movement decide. The leading 20 px never claim.
- Off screen the widget is paused (no rAF, timers ≤1 Hz, `deactivated`). It may be destroyed and
  re-created at any time: redraw from state and localStorage on every start.
