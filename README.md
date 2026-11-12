# Telegram Widgets Skill

**English** · [Русский](README.ru.md)

An agent skill that teaches AI coding agents (Claude Code, Claude apps, OpenAI Codex and others) to
build **Telegram Bot API 10.4 widgets** correctly and securely: interactive HTML blocks that a bot sends
inside a chat message.

It is language- and framework-agnostic. The bot side is plain Bot API over HTTPS, so it works for bots
in Python, Node.js, Go, PHP, Java or anything else. Ready-made adapters are included for Python
(aiogram and the standard library), Node.js and curl.

## Why this exists

Widgets are new and unusual: the HTML runs in a QuickJS sandbox with no network, must fit into
**4096 bytes after zlib compression**, cannot change its own state, may only send 64-byte requests on a
tap, and is drawn by Telegram's own renderer, which differs from a browser. Most mistakes only show up
in real Telegram. This skill packs the official rules together with lessons from shipping a real
production widget (a "pick the frame and the minute" editor with a live progress ring for a video bot),
including bugs that a browser preview never showed:

- a canvas path that rendered fine in Chrome but drew a stripe through the image in Telegram;
- requests rejected with `BUSY` when the user tapped right after interacting;
- a 30-second library download timeout that failed the same file intermittently;
- raw error text that could leak the **bot token** to users through an HTTP client's error message;
- a per-user queue lock held while waiting for a human to choose.

## What the agent gets

```
skills/telegram-widgets/
├── SKILL.md                    # the workflow the agent follows (6 steps)
├── references/
│   ├── platform.md             # methods, fields, limits, allowed HTML/CSS/JS, TelegramWidget API
│   ├── security.md             # threat model and a pre-release security checklist
│   ├── pitfalls.md             # 19 field-tested bugs: symptom, cause, fix
│   ├── server-side.md          # bot-side architecture in pseudocode (any language)
│   ├── frameworks.md           # escape hatches for aiogram, python-telegram-bot, grammY, Telegraf, others
│   ├── patterns.md             # live progress, editor with autostart, poll, ticker, image budget
│   └── testing.md              # size checks, local preview, live test checklist
├── templates/
│   └── widget-skeleton.html    # safe widget starting point
├── adapters/
│   ├── python-aiogram.py       # aiogram 3.x methods, middleware, state holder (verified live)
│   ├── python-stdlib.py        # no dependencies
│   ├── node-fetch.mjs          # Node 18+ / Deno / Bun, no dependencies
│   └── curl.md                 # raw HTTP bodies for any language
└── scripts/
    ├── check_widget.py         # compressed size the way the server counts it + forbidden-feature lint
    └── preview_widget.py       # local browser preview with a TelegramWidget stub
```

The workflow makes the agent: check where widgets are available (production: private chats only),
design the state and request protocol first, plan the 4 KB budget, build from the safe skeleton, wire
the bot side with authorization, strict parsing, rate limiting and a fallback, and verify in real
Telegram before calling it done.

## Install

### Claude Code

```bash
git clone https://github.com/aislam23/telegram-widgets-skill.git
mkdir -p ~/.claude/skills
cp -r telegram-widgets-skill/skills/telegram-widgets ~/.claude/skills/
```

For one project only, copy it into `<project>/.claude/skills/` instead. The skill loads automatically
when a task mentions Telegram widgets or interactive bot messages.

### Claude apps (claude.ai, desktop)

Download `telegram-widgets.zip` from the
[latest release](https://github.com/aislam23/telegram-widgets-skill/releases/latest) and upload it as a
custom skill in the app's skills settings.

### OpenAI Codex CLI

```bash
mkdir -p ~/.codex/skills
cp -r telegram-widgets-skill/skills/telegram-widgets ~/.codex/skills/
```

If your Codex version has no skills support, add a line to your project's `AGENTS.md`:
`For Telegram widgets, follow skills/telegram-widgets/SKILL.md and the files it references.`

### Other agents (Cursor, Gemini CLI, Windsurf, and so on)

Copy the `skills/telegram-widgets` folder into your repository and point the agent's rules file
(`AGENTS.md`, `.cursor/rules`, `GEMINI.md`) at `skills/telegram-widgets/SKILL.md`.

## Use

Just ask for what you want; the skill triggers on its own:

- "Add a live progress widget to my video bot instead of the 'Processing…' message."
- "Make a poll widget for my Go bot, with results that update for everyone."
- "My widget works in the browser but looks broken in Telegram."
- "Port our callback-button settings menu to a widget, the bot uses grammY."

Tools you can run yourself:

```bash
python3 skills/telegram-widgets/scripts/check_widget.py my-widget.html
python3 skills/telegram-widgets/scripts/preview_widget.py my-widget.html \
        --chat-data '{"m":"p","p":40}' --out preview.html --dark
```

## Status and accuracy

- Written for **Telegram Bot API 10.4** (November 2026), widget profile 1.
- Verified live in Telegram: `sendWidget`, `editMessageWidgetData`, `editMessageCaption` on a widget,
  `deleteMessage`, `widget_query` delivery and answers through aiogram 3.20, the canvas fix and the
  request-queue fix.
- From the official documentation, not exercised live: groups, inline mode, forwards and shared widgets
  (test server only at the time of writing), the TON wallet flow, and the framework snippets other than
  aiogram. They are marked as such in the files.
- Widgets are rolling out in steps. If the official docs say something newer, they win.

Official docs: [Widgets guide](https://core.telegram.org/bots/widgets) ·
[Bot API](https://core.telegram.org/bots/api) · [Changelog](https://core.telegram.org/bots/api-changelog)

## Contributing

Issues and pull requests are welcome, especially: new pitfalls with a reproducible symptom, adapters for
more languages, and corrections when Telegram changes limits or availability. Please keep the skill
language-neutral and explain the reason behind every rule.

## License

[MIT](LICENSE)
