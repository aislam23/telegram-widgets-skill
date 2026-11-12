# Security checklist for Telegram widgets

Go through every item for every widget. Each item says what can go wrong and what to do.

## Contents
1. Threat model in one paragraph
2. Inputs from the widget
3. Authorization and ownership
4. Secrets and data exposure
5. Rendering untrusted text
6. Availability, rate limits and resource use
7. Concurrency and state integrity
8. Payments and the wallet
9. Privacy
10. Operational safety
11. Pre-release checklist

## 1. Threat model

The HTML, the CSS, the JS and both state strings are delivered to the user's device and can be read
by anyone who sees the message: in a group, every member; after a forward (test server today), anyone
in the target chat. Anything the widget sends to the bot can be forged by a modified client, except
`from` (the authenticated user who tapped) and `widget_id` (computed by the server). The bot is the
only trusted party and the only writer of state.

## 2. Inputs from the widget

- Treat `widget_query.data` exactly like `callback_data`: untrusted, attacker-controlled.
- Parse with an **anchored** pattern and length caps: `^g:([0-9.]{1,8}),([0-9.]{1,8}),(\d{1,6})$`.
  Reject anything else with a short answer instead of throwing.
- **Clamp** every number to its legal range (coordinates 0..1, zoom to an allow-list, offsets to the
  media length). Never pass widget input to a shell, SQL, a file path or ffmpeg filter syntax without
  converting it to a validated number or enum first.
- Validate the request against **your** state: is this widget still waiting for this action? Is the
  job already running? A replayed or stale request must be harmless.
- Answer malformed requests too (with a short text). An unanswered request becomes TIMEOUT for the
  user and keeps their one-request slot busy for 15 s.

## 3. Authorization and ownership

- Store the owner when you send the widget: `(chat_id, message_id) → user_id` (static widgets) or
  key actions by `(widget_id, from.id)` (shared widgets and forwards).
- On every request compare `from.id` with the stored owner before acting. In a private chat the
  chat id equals the user id, but do not rely on that once groups/inline arrive: in a group every
  member can tap.
- `viewer` inside the widget is only a display hint; never send it back as proof of identity.
- Paid or quota-limited actions: re-check the user's plan/quota when the job actually starts, not
  when the widget was sent (plans expire, queues are long).

## 4. Secrets and data exposure

- **No secrets in HTML, chat_data, public_data, answers or captions.** No API keys, no signed URLs,
  no internal ids you would not show in a message.
- **Never show raw exception text to users.** Real incident: an HTTP client error raised while
  downloading a Telegram file prints the request URL, and that URL contains the bot token
  (`https://api.telegram.org/file/bot<TOKEN>/videos/file_7.MOV`). Code that did
  `f"Error: {e}"` would send the token to the user on any HTTP error status. Fix: map exceptions to
  your own messages; if you must include a reason, strip URLs and the token first:

  ```python
  _URL = re.compile(r"https?://\S+")
  def public_reason(e: BaseException) -> str:
      text = _URL.sub("<link hidden>", str(e) or type(e).__name__)
      return text.replace(BOT_TOKEN, "<token hidden>")[:200]
  ```

- **Logs leak too.** Loguru's default `diagnose=True` prints local variable values in tracebacks,
  including those URLs. Use `logger.add(..., diagnose=False)` in production and never log full request
  URLs of the Bot API.
- `chat_data` in a group is visible to every member. Do not put one member's private data there.

## 5. Rendering untrusted text

- The widget's DOM is sandboxed, but injected markup can still spoof your UI (fake buttons, fake
  prices) or break layout. Use `textContent` for anything that came from a user, from the bot's
  error messages, or from external data. Use `innerHTML` only with constant templates.
- `openLink(url)` shows the full URL to the user, but still build links from an allow-list, never
  from request data or state that a user influenced.
- Cap lengths of every text you render (state is 1024 bytes, but a 1000-character name still breaks
  a 320 px layout).

## 6. Availability, rate limits and resource use

- `editMessageWidgetData` counts against the bot's message limits. Throttle progress pushes (1–2 s),
  push immediately only on mode changes, coalesce edits, and handle flood waits by skipping a frame
  rather than retrying in a loop.
- Shared widgets: at most one public_data edit per second; coalesce votes server-side.
- Do slow work after `answerWidgetQuery` in a background task, keep a strong reference to the task,
  and always cancel/cleanup on failure (temp files, subprocesses).
- Background requests (private chat) are limited to one every 5 s while visible: do not use them as a
  polling channel for data the bot can push with `editMessageWidgetData`.
- Inside the widget, stay well under the CPU/DOM/canvas limits (`references/platform.md` §4). A widget
  that hits a limit is stopped; two crashes in a row and it stays dead until the app restarts.
- Network timeouts on the bot side: library defaults can be short (aiogram's file download default is
  30 s for the whole file). Set explicit timeouts sized for your largest file and report timeouts as a
  clear "took too long, try again" message.

## 7. Concurrency and state integrity

- The authoritative state lives on the server. The widget's copy is a projection.
- **Register before you await.** Right after `sendWidget` returns, mark the widget busy and create any
  "waiting for a choice" record before doing anything else that awaits (saving to Redis, deleting an
  old message, checking a subscription). Otherwise a fast tap lands in the gap and starts a duplicate
  job that shares temp files with the first one.
- **One job per widget.** Keep a `busy` set keyed by `(chat_id, message_id)`; answer "already working"
  instead of starting a second job.
- **Serialize edits per message** (an asyncio.Lock per widget object) and make error/terminal states
  sticky: once the widget shows an error, later progress edits must be dropped. Otherwise a slow
  "downloading…" edit can land after the error and leave the user with an endless spinner.
- **Do not hold shared locks while waiting for a human.** If users have a per-user queue, wait for the
  widget choice before taking the queue lock; take it only for the actual work.
- Use a revision number (`"r": 41`) in shared state so clients ignore older snapshots.
- Persist the session (owner, media file_id, options) with a TTL so "redo" buttons work after a bot
  restart, and handle "session not found" gracefully.

## 8. Payments and the wallet

- `request(data, {wallet:true})` gives the bot the user's TON wallet card. Build the transaction on
  the bot, fresh, with `valid_until`. Never take amounts or recipients from request data.
- Verify the outcome on-chain (sender, recipients, amounts, success). The `msg_hash` alone proves
  nothing.
- After `TIMEOUT` the payment may already have been sent: ask the bot for the order status, never
  re-send blindly. Make orders idempotent.
- Signatures (`sign_data`) are for the domain `bot<bot_id>`: verify with the wallet's public key and
  tie the key to the address on-chain.
- Prefer Telegram Stars / regular invoices (`sendInvoice`) triggered by a widget request when you do
  not need TON specifically. A widget cannot pay by itself.

## 9. Privacy

- In the private chat, background requests reveal when the user has the chat open. Do not log or
  use that as tracking.
- `from` on a request is a full User object; store only what you need.
- localStorage is per message per device and never sent anywhere; still, do not store anything
  sensitive there.

## 10. Operational safety

- Feature flag (`WIDGETS_ENABLED`) and a fallback to the previous text/keyboard UI when `sendWidget`
  fails. Unsupported apps see only the caption: make it meaningful.
- Check the compressed size before sending and degrade (smaller image, no image) instead of failing.
- Validate state size before every edit (1024 bytes): drop optional fields first.
- Migrations for any new journal fields run before the new code serves traffic.
- Production rollout only after a live test on a separate test bot.

## 11. Pre-release checklist

- [ ] `allowed_updates` includes `widget_query` (and `shared_widget_query` if used)
- [ ] every query answered within 15 s, including errors and unknown data
- [ ] `data` parsed with anchored regex, numbers clamped, actions checked against server state
- [ ] owner check on `from.id`
- [ ] no secrets in HTML / state / answers / captions; user-facing errors scrubbed of URLs and token
- [ ] production logs do not print variables or Bot API URLs
- [ ] `textContent` for all non-constant text in the widget
- [ ] busy flag + waiting record registered immediately after send; one job per widget
- [ ] edits serialized; terminal error state cannot be overwritten
- [ ] progress edits throttled; shared widget edits ≤1/s
- [ ] explicit network timeouts sized for real files; cleanup on cancel
- [ ] compressed HTML ≤4000 bytes, state ≤1024 bytes, checked in tests
- [ ] feature flag + fallback path tested
- [ ] verified live in Telegram on a test bot; what was not verified is written down
