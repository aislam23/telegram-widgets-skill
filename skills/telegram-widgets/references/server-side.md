# Bot side, language-neutral

Everything here is plain Bot API over HTTPS and applies to any language or framework. Adapters with
working code: `adapters/` (Python with aiogram, Python stdlib, Node.js fetch, curl). Framework escape
hatches: `references/frameworks.md`.

## Contents
1. The four calls you need
2. Receiving requests
3. The widget state holder
4. Handling a request
5. Long jobs
6. Sessions and restarts
7. Fallback

## 1. The four calls you need

All are `POST https://api.telegram.org/bot<TOKEN>/<method>` with a JSON body.

| Call | Body | Notes |
|---|---|---|
| `sendWidget` | `chat_id, html, chat_data?, public_data?, caption?, allow_queries?, is_shared?, reply_parameters?, reply_markup?` | returns the Message; store `message_id` |
| `answerWidgetQuery` | `widget_query_id, data?` | within 15 s, for every query |
| `editMessageWidgetData` | `chat_id, message_id, chat_data?, public_data?` | counts as a sent message |
| `editMessageCaption` | `chat_id, message_id, caption, reply_markup?` | text and buttons under the widget |

Plus `sendSharedWidget` / `editSharedWidgetData` for shared widgets, `deleteMessage` to replace a
widget whose layout must change.

## 2. Receiving requests

- Long polling: `getUpdates` with `allowed_updates` that **lists** `widget_query` and
  `shared_widget_query`. Webhook: same list in `setWebhook`.
- If your framework drops unknown update types, intercept the raw update before routing
  (`references/frameworks.md`).
- Handle updates concurrently: a slow job must not block other users' answers.

## 3. The widget state holder

One object per widget message, in memory while a job runs, persisted when it must survive restarts:

```
WidgetMessage
  chat_id, message_id, owner_user_id
  state            # authoritative chat_data, always sent whole, <= 1024 bytes
  caption
  failed = false   # terminal error flag
  lock             # one edit at a time
  last_push_at

  push(force, terminal=false):
      if not force and now - last_push_at < 1..2 s: return        # throttle
      with lock:
          if failed and not terminal: return                       # error is final
          editMessageWidgetData(chat_id, message_id, json(state))  # "not modified" = success

  progress(percent):  state.m = "p"; state.p = percent; push(force = mode changed)
  done(fields):       state.m = "d"; merge fields; push()
  fail(text, buttons, title):
      failed = true; state.m = "x"; state.t = title
      push(terminal); editMessageCaption(text_without_secrets, buttons)
```

## 4. Handling a request

```
on widget_query q:
    key = (q.chat.id, q.message_id)             # shared widget / forward: (q.widget_id, q.from.id)
    session = sessions.get(key)
    if session is None or session.owner != q.from.id:
        answer(q.id, "Not available");  return
    action = parse(q.data)                      # anchored regex, length cap, clamp numbers
    if action is None:
        answer(q.id, "Unknown action"); return
    if key in busy:
        answer(q.id, "Already working"); return
    if session.waiting_for_choice:              # e.g. an editor with autostart
        session.choice = action; wake the waiter
        answer(q.id, "ok");  return
    busy.add(key)
    answer(q.id, "ok")                          # answer first ...
    start_background(run_job(session, action))  # ... then work; remove key from busy at the end
```

Rules behind it: answer every query (also errors) within 15 s; `from` and `widget_id` are trustworthy,
`data` is not; one job per widget; never act on another user's widget.

## 5. Long jobs

```
send widget (mode p or e)  ->  register busy + waiting record IMMEDIATELY
(optional) wait for a choice outside any per-user lock, prepare in parallel
take the per-user lock / queue slot
run: push stage changes now, percent every 1-2 s
success: done(); persist session (for "redo")
failure: fail(safe message) - map exceptions, never echo raw error text
finally: release busy, cancel and await helpers, delete temp files
```

Set explicit network timeouts sized for real payloads; library defaults can be as short as 30 s for a
whole file download.

## 6. Sessions and restarts

Persist `{owner, chat_id, message_id, media ids, options, last state}` in Redis or a DB with a TTL
(days). Buttons on old widgets keep working after a restart, and a missing session gets a polite
answer ("send the file again") instead of a timeout.

## 7. Fallback

`sendWidget` can fail (older clients are fine, they show the caption; but server errors, size limits
or a disabled feature flag happen). Keep the previous text/keyboard flow and switch to it when the send
fails or `WIDGETS_ENABLED=false`.
