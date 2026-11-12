# Testing widgets

## 1. Static checks (every change)

```bash
python scripts/check_widget.py path/to/widget.html            # size + forbidden features
python scripts/check_widget.py widget.html --image 1200        # reserve bytes for an image you inject later
```

The script counts the compressed size exactly as the server does (Python zlib, level 9), warns above
4000 bytes, fails above 4096, and flags features the sandbox removes (inputs, video, fetch, vh,
color-mix, oklch, overflow:auto, web fonts, alert, external scripts, canvas arcs past 2π, …).

Add a unit test in the bot that builds the real HTML (with a real image if you inject one) and asserts
the compressed size and every `chat_data` you can produce stay under the limits.

## 2. Local preview (layout only)

```bash
python scripts/preview_widget.py widget.html --chat-data '{"m":"e","d":135}' \
       --public-data texts.json --out preview.html --dark
```

Open `preview.html` at 320–430 px width. The stub logs `request()` calls to the console and resolves
them with `{result:"ok"}`. A browser draws more than Telegram does (removed features still render here)
and has different canvas behavior, so this only checks layout and logic.

## 3. Bot-side tests

- Fake the bot object and assert the sequence of `sendWidget` / `editMessageWidgetData` states per
  scenario: fast path, editor untouched (autostart), editor touched then chosen, redo, foreign user,
  garbage data, widget send refused (fallback), download failure during the editor.
- Real ffmpeg (or whatever worker) on generated media in CI, including cancellation.

## 4. Live test on a test bot (mandatory before production)

Use a separate bot token. Checklist:

- [ ] the tester has not blocked the bot and has sent /start
- [ ] `sendWidget` succeeds and the message shows the widget (not "unsupported")
- [ ] every mode renders: light and dark theme, smallest phone, desktop app
- [ ] taps reach the bot (`widget_query` arrives, answer within 15 s)
- [ ] fast double tap, tap while a request is in flight, drag then tap
- [ ] scroll the widget off screen and back, restart the app: state redraws
- [ ] errors: slow network, refused send, too large file; error text is clear and leak-free
- [ ] the fallback path with `WIDGETS_ENABLED=false`
- [ ] canvas drawing looks the same as in the browser (it may not: pitfall 1)

Write down what was verified live and what was only previewed.

## 5. Test server

Groups, inline mode and forwards work only on Telegram's test environment today. Create a test-server
account and bot (see Telegram's docs on the test environment) and point your library at
`https://api.telegram.org/bot<TOKEN>/test/<method>`.
