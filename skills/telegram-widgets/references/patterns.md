# Proven widget patterns

## Contents
1. One template, many modes
2. Live progress for long jobs
3. Editor with autostart (pick a frame, a range, an option)
4. Redo from a finished widget
5. Poll / counter with a shared widget
6. Ticker without requests
7. Fitting an image into 4 KB
8. Server-side state holder

## 1. One template, many modes

The HTML is fixed at send time, so put every view the message will ever need into one template and
switch with a mode field in `chat_data`:

```
m = "p"  progress   {q: queue ahead, st: stage, p: percent}
m = "e"  editor     {a: autostart unix time, d: duration, w: waveform, c/y/z/s: current choice}
m = "d"  done       {choice fields, f: 1 if "fix" is possible}
m = "x"  error      {t: optional title}; the full text and buttons go to the caption
```

The widget renders from state on start and on every `chatDataChanged`. Keep local UI choices (the
circle position while dragging) in JS variables and seed them from state once.

## 2. Live progress for long jobs

- Send the widget as soon as the job is accepted (`m:"p"`, queue position or stage 0).
- Push stage changes immediately; push percent at most every 1–2 s from a ticker that reads the latest
  value written by the worker (for ffmpeg: `-progress pipe:1`, parse `out_time_us` against the
  duration).
- Draw an indeterminate spinner (rotate the SVG with a CSS animation) while the percent is unknown.
- Change the caption only on mode changes (old apps and the chat list see it).
- On error: terminal `m:"x"`, the explanation and any buttons (e.g. "Buy Premium") in the caption via
  `editMessageCaption` + `reply_markup`.

## 3. Editor with autostart

Use when a sensible default exists but some users want to adjust it:

1. Send the editor with `a = now + 15` (autostart time) and start the expensive preparation
   (download) in parallel right away.
2. The widget shows a countdown "Without a choice I will use the center in N s".
3. On the first interaction (pointerup or click) the widget sends `h`. The bot marks the session
   "touched" and extends the wait (e.g. to 10 min). Reset the flag in the widget if `h` fails.
4. "Make" sends the choice (`g:x,y,z,s`). If `h` is still in flight, queue it (pitfall 4).
5. The bot waits `autostart` seconds, or the extended time if touched; on timeout it uses the default.
   The wait happens outside any per-user lock.
6. When the user chose, switch the same widget to progress (`m:"p"`), then `m:"d"`.

Things that made it work on phones: tap to place (vertical drags scroll the chat, so a vertical-only
control is impossible), horizontal drag with `touch-action: pan-y`, zoom as three buttons, a time range
as a horizontal track with the window dragged sideways, and `pointercancel` restoring the previous
value.

## 4. Redo from a finished widget

Keep a server-side session per widget message (owner, media `file_id`, metadata, last state) in
Redis or a DB with a TTL of a few days. A request on a finished widget:

- answer "ok" fast, then run the job in the background, reusing the same widget for progress;
- refuse with a short answer if the session is missing, the owner differs or a job is already running;
- re-check plan limits (file size, subscription) at start.

## 5. Poll / counter with a shared widget

- `sendWidget(is_shared=true, allow_queries=true)` once; read `message.widget.id`.
- Votes arrive as `widget_query` (originals) or `shared_widget_query` (forwards); key them by
  `(widget_id, from.id)`.
- Answer with the new totals (the voter sees them at once), then coalesce `editSharedWidgetData`
  to at most once per second with a revision number `r`.
- The widget calls `watchPublicData()` and ignores states with a lower `r`.

## 6. Ticker without requests

`is_shared` without `allow_queries`; the bot updates `public_data` with `editSharedWidgetData` and a
`cache_time` that matches how often the value changes (10 s for a price).

## 7. Fitting an image into 4 KB

```python
STEPS = ((176, 45), (160, 40), (144, 36), (128, 32), (112, 28), (96, 24), (80, 20))
for side, quality in STEPS:
    data, mime = encode_frame(src, side, quality)          # WebP, JPEG fallback
    html = TEMPLATE.replace("%IMG%", f"data:{mime};base64,{b64(data)}")
    if len(zlib.compress(html.encode(), 9)) <= 4000:
        return html
return None                                                  # degrade: no image / no editor
```

Measured: a 2.5 KB template left room for a ~1.0–1.2 KB WebP (128–160 px wide). That is blurry when
stretched to a 300 px bubble, but enough to see where a face is. Only switch WebP off when ffmpeg says
the encoder is missing, not after any error.

Use the media's own small preview where the platform already made one (Telegram video `thumbnail`): it
downloads instantly even for a 500 MB file, so the editor appears before the download finishes.

## 8. Server-side state holder

One object per widget message:

```python
class WidgetProgress:
    state: dict            # authoritative chat_data, always sent whole
    caption: str
    _lock: asyncio.Lock    # edits go one at a time
    failed: bool           # terminal error; non-terminal edits are dropped after it

    async def push(force=True, terminal=False)   # throttled editMessageWidgetData
    async def stage(n, fraction=None)
    async def done(choice)
    async def fail(text, reply_markup=None, title=None)   # m:"x" + caption, terminal
```

Implementations: `adapters/python-aiogram.py`, `adapters/node-fetch.mjs`; pseudocode in `references/server-side.md`.
