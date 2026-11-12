# Framework escape hatches

The skill is language-neutral: widgets are plain Bot API calls (`references/server-side.md`). This file
only shows how to reach those calls and the `widget_query` update in libraries that predate Bot API
10.4. Every library needs three things:

1. a way to call an arbitrary Bot API method;
2. a hook that sees the raw update before the router drops it as an unknown type;
3. `widget_query` (and `shared_widget_query`) in `allowed_updates`.

Verified live end to end: **aiogram 3.20** (see `adapters/python-aiogram.py`). The rest follow each
library's documented escape hatches; check them against your version, and switch to native support once
your library ships it.

## Python: aiogram 3.x (verified)

- Subclass `TelegramMethod` with `__returning__` and `__api_method__`; call as `await bot(SendWidget(...))`.
- `Update` keeps unknown fields in `update.model_extra`; read `widget_query` there in an **outer
  middleware on `dp.update`**, which runs before the dispatcher discards unknown types.
- `allowed_updates=dp.resolve_used_update_types() + ["widget_query", "shared_widget_query"]`.
- `bot.download_file()` defaults to a 30 s timeout for the whole file; pass a bigger one.

## Python: python-telegram-bot 20.8+ / 21.x

```python
msg = await bot.do_api_request("sendWidget", api_kwargs={...}, return_type=Message)
# unknown top-level update fields land in Update.api_kwargs
app.add_handler(TypeHandler(Update, on_any_update), group=-1)
app.run_polling(allowed_updates=Update.ALL_TYPES + ["widget_query", "shared_widget_query"])
```

## JavaScript / TypeScript: grammY

```ts
await (bot.api.raw as any).sendWidget({ chat_id, html, chat_data, allow_queries: true });
bot.use(async (ctx, next) => {
  const q = (ctx.update as any).widget_query;
  return q ? handleWidgetQuery(q) : next();
});
bot.start({ allowed_updates: ["message", "callback_query", "widget_query", "shared_widget_query"] as any });
```

## JavaScript: Telegraf

```js
await ctx.telegram.callApi("sendWidget", { chat_id, html, chat_data, allow_queries: true });
bot.use((ctx, next) => ctx.update.widget_query ? handleWidgetQuery(ctx.update.widget_query) : next());
bot.launch({ allowedUpdates: ["message", "callback_query", "widget_query", "shared_widget_query"] });
```

## JavaScript: no framework

`adapters/node-fetch.mjs` (Node 18+, Deno, Bun).

## Go, PHP, Java, C#, Rust, others

Most libraries expose a generic "make request" method (for example a `Raw`/`Request`/`execute`
function taking a method name and parameters) and give access to the raw update JSON. If yours does
not, make the four HTTP calls yourself (`adapters/curl.md` has the exact bodies) and read the raw
update JSON before deserializing it into the library's types.

## Webhooks

List the widget updates in `setWebhook(allowed_updates=...)`. Answer the query quickly from the
handler, do slow work in the background, and return HTTP 200 fast so Telegram does not retry.
