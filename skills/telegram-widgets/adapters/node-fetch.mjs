// Adapter: Node.js 18+ (or Deno / Bun), no dependencies, built-in fetch.
//
//   BOT_TOKEN=123:abc node node-fetch.mjs <chat_id> widget.html
//
// Sends the widget, long-polls for widget_query updates and answers them.
// Port the functions into grammY / Telegraf / your framework, or use them directly.
// Never log the request URL: it contains the bot token.

import { readFileSync } from "node:fs";
import { deflateSync } from "node:zlib";

const TOKEN = process.env.BOT_TOKEN;
const api = (method) => `https://api.telegram.org/bot${TOKEN}/${method}`; // test server: /bot<T>/test/<method>

export async function call(method, params = {}, timeoutMs = 60_000) {
  let res;
  try {
    res = await fetch(api(method), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (e) {
    // fetch errors can include the URL; report only the kind of failure
    throw new Error(`${method}: network error ${e?.name ?? "Error"}`);
  }
  const body = await res.json();
  if (!body.ok) throw new Error(`${method}: ${body.description}`);
  return body.result;
}

// Node's zlib may differ from the server by a few dozen bytes near the limit; keep headroom.
export const compressedSize = (html) => deflateSync(Buffer.from(html, "utf8"), { level: 9 }).length;

export function stateJson(state) {
  const clean = Object.fromEntries(Object.entries(state).filter(([, v]) => v != null));
  const s = JSON.stringify(clean);
  if (Buffer.byteLength(s, "utf8") > 1024) throw new Error("widget state over 1024 bytes");
  return s;
}

export async function sendWidget(chatId, html, { chatData = {}, publicData, caption, allowQueries = true } = {}) {
  if (compressedSize(html) > 4000) throw new Error("widget HTML over budget after zlib-9");
  return call("sendWidget", {
    chat_id: chatId, html, chat_data: stateJson(chatData), public_data: publicData,
    caption, allow_queries: allowQueries,
  });
}

export const editWidgetData = (chatId, messageId, state) =>
  call("editMessageWidgetData", { chat_id: chatId, message_id: messageId, chat_data: stateJson(state) });

export const answerWidgetQuery = (queryId, data) =>
  call("answerWidgetQuery", { widget_query_id: queryId, data }).catch(() => {}); // never throw from an answer

// Request data is untrusted: anchored pattern, then clamp.
export function parseGo(data) {
  const m = /^go:(\d)$/.exec(data ?? "");
  return m ? Math.min(Number(m[1]), 2) : null;
}

async function main() {
  const [chatId, file] = process.argv.slice(2);
  const msg = await sendWidget(Number(chatId), readFileSync(file, "utf8"), {
    chatData: { m: "e" }, caption: "Widget test",
  });
  console.log("sent message", msg.message_id);
  let offset;
  for (;;) {
    const updates = await call("getUpdates", {
      offset, timeout: 50, allowed_updates: ["message", "widget_query", "shared_widget_query"],
    }, 70_000);
    for (const u of updates) {
      offset = u.update_id + 1;
      const q = u.widget_query ?? u.shared_widget_query;
      if (!q) continue;
      const option = parseGo(q.data);
      await answerWidgetQuery(q.id, option == null ? "Unknown action" : "ok"); // answer first
      if (option != null && q.chat) {
        await editWidgetData(q.chat.id, q.message_id, { m: "p", p: null });   // then work
      }
    }
  }
}

if (import.meta.url === `file://${process.argv[1]}`) main();
