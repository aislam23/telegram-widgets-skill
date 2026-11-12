# Field-tested pitfalls

Every item below happened while shipping a real widget: a "pick the frame and the minute" editor plus a
live progress ring for a video bot. Each entry: symptom, cause, fix.

## Rendering

### 1. A diagonal stripe through a canvas "hole" that moves with it
- **Symptom**: a dimmed overlay with a circular cut-out looked perfect in Chrome, but in Telegram a
  dark wedge with a straight edge crossed the circle and followed it when dragged.
- **Cause**: the overlay was one path: `rect(0,0,w,h)` then `arc(x,y,r,0,7,true)`. After `rect()` the
  current point is the rectangle's corner, so `arc()` adds a line from the corner to the arc start, and
  the end angle `7` relies on the browser treating anything above 2π as a full turn. Telegram's
  renderer filled that connecting line and the partial arc differently.
- **Fix**: never rely on winding rules or implicit connecting lines. Draw the dim layer over the whole
  canvas, then clip to the circle and draw the image again:
  ```js
  cx.drawImage(img,0,0,w,h);
  cx.fillStyle='rgba(0,0,0,.55)'; cx.fillRect(0,0,w,h);
  cx.save(); cx.beginPath(); cx.moveTo(x+r,y); cx.arc(x,y,r,0,Math.PI*2); cx.closePath();
  cx.clip(); cx.drawImage(img,0,0,w,h); cx.restore();
  ```
  Always use exactly `Math.PI*2` and an explicit `moveTo` before arcs.
- **Lesson**: a browser preview is not proof. Verify every canvas effect in real Telegram.

### 2. Error text disappears a second after it is shown
- **Symptom**: the error view showed its title and an empty subtitle.
- **Cause**: a 1 s `setInterval` that updated the countdown line wrote `''` into the element with the
  same id that the error view used for its message.
- **Fix**: give each view its own element ids, or let the ticker touch only the view it belongs to.

### 3. Fixed colors and transparency
- Hard-coded colors break in dark themes and in outgoing bubbles (a widget sent via the bot sits in
  the user's bubble). Use `--tg-theme-*` variables. Mute with colors, not `opacity`: more than 16
  translucent or filtered elements stop the widget.

## Requests

### 4. "Press again" right after touching the editor
- **Symptom**: the user moved the circle, immediately pressed "Make", and got an error.
- **Cause**: moving the circle sent a small "user is interacting" request (`h`) to cancel the
  server-side autostart. Only one request may be in flight, so "Make" was rejected with BUSY.
- **Fix**: remember one pending primary action while a request is in flight and send it from the first
  request's settle handler. In the private chat that send is allowed as a background request; if it is
  refused, show "press again".
  ```js
  function q(d, ok, no){
    if(!W) return;
    if(B){ if(d[0]=='g' && cur[0]!='g') P=[d,ok]; return; }  // queue the primary action,
    B=1; cur=d;                                                 // but not a double tap of it
    function fail(e){ B=0; no ? no(e) : showError(); next(); }
    try { W.request(d).then(function(a){ B=0; ok&&ok(a.result); next(); }, fail); }
    catch(e){ fail(e); }                              // request() can throw synchronously
  }
  function next(){ if(P){ var p=P; P=0; q(p[0],p[1]); } }
  ```

### 5. A flag set before a request is never reset
- **Symptom**: after one failed "interacting" request the countdown vanished, but the server still
  auto-started 15 s later while the user was adjusting.
- **Cause**: `held=1` was set before `request('h')`; on rejection nothing reset it, so the widget never
  asked again.
- **Fix**: reset such flags in the rejection handler (`q('h',0,function(){held=0})`) and do not show an
  error for background bookkeeping requests.

### 6. Requests only from click or pointerup, synchronously
- Calls from `pointerdown`, timers, promise callbacks or after `await` are refused (NOT_ALLOWED) or count
  as background requests. Make the call directly in the handler.

### 7. Requests silently time out
- **Cause**: `allowed_updates` passed to getUpdates/setWebhook did not include `widget_query`
  (frameworks that compute it from registered handlers do not know the new type).
- **Fix**: append `widget_query` and `shared_widget_query` explicitly.

## Bot side

### 8. The framework does not know the update
- Example, aiogram 3.20: keeps unknown fields in `Update.model_extra` and then drops the update as an unknown
  type with a warning. Catch it in an outer middleware on `dp.update` before routing
  (`adapters/python-aiogram.py`). Other frameworks: see `references/frameworks.md`.

### 9. The HTML cannot be changed after sending
- A "progress" widget sent before you know whether you need an editor cannot become an editor with an
  image later. Decide first (use metadata you already have, such as video width, height, duration and
  the Telegram thumbnail), or delete the old message and send a new widget. Design one template whose
  modes are switched by `chat_data`.

### 10. Size budget blown by text
- 19 short Russian UI strings cost about 410 bytes compressed. Moving them into `public_data` (a static
  widget's free 1 KB) and indexing them freed room for an image. `data:` images barely compress:
  shrink them in a loop (WebP 176 to 80 px, quality 45 to 20) until `zlib.compress(html, 9) <= 4000`.

### 11. Holding a queue lock while waiting for a human
- **Symptom (found in review)**: a free-tier user opened the editor, touched it and walked away; all
  their other videos waited up to 10 minutes.
- **Fix**: run the "wait for choice" phase before acquiring the per-user queue lock, start the download
  in parallel during the wait, and take the lock only for encoding.

### 12. Duplicate jobs from a fast tap
- **Cause**: between `sendWidget` returning and the "waiting" record being registered there were
  several awaits (Redis save, deleting an old message). A tap in that gap started a second job on the
  same temp files.
- **Fix**: register busy and waiting state synchronously right after the send.

### 13. A late progress edit overwrites the error
- **Fix**: a per-widget lock around edits plus a `failed` flag that makes the error terminal; later
  non-terminal edits are dropped.

### 14. Library default timeouts
- Example: aiogram's `download_file` defaults to a 30 s timeout for the whole file. A 15 MB video on a
  0.4–0.5 MB/s link took 32–37 s and failed intermittently ("it worked, now the same file fails").
  Production logs showed the same failure for real users. Set an explicit timeout (for example 180 s)
  and map `TimeoutError`, whose `str()` is empty, to a clear message.

### 15. Raw exceptions shown to users leak the bot token
- See `references/security.md` §4. An HTTP client error's text includes the full file URL with the
  token. Scrub before showing, and disable variable dumps in production logs.

### 16. Video orientation
- Phones store portrait video as landscape pixels plus rotation metadata. ffmpeg auto-rotates on decode,
  so crop math must use the displayed size (swap width and height when rotation is ±90°), and the
  normalized coordinates from the widget must refer to the displayed frame. Telegram thumbnails are
  already in displayed orientation.

### 17. Cancelled downloads recreate temp files
- Cancelling a download task and deleting its file in the same tick can lose the race with a pending
  file write. Run `task.cancel(); await asyncio.gather(task, return_exceptions=True)` before cleanup.
  Kill ffmpeg subprocesses on cancellation.

### 18. "Bot was blocked by the user"
- Live tests on a fresh test bot fail with Forbidden if the tester blocked it earlier. Ask them to
  unblock it and send /start first.

### 19. Checks that need admin rights
- Channel-subscription gates via `getChatMember` fail with "member list is inaccessible" unless the bot
  is an administrator of the channel. A test bot needs the same setup as production.
