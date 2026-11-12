# Adapter: plain HTTP with curl

Works from any language: these are the exact JSON bodies to POST. Replace `$TOKEN`; never paste the
URL into logs, issues or error messages.

```bash
API="https://api.telegram.org/bot$TOKEN"      # test server: https://api.telegram.org/bot$TOKEN/test

# size check (must be <= 4096; aim for <= 4000)
python3 -c 'import sys,zlib; print(len(zlib.compress(sys.stdin.buffer.read(), 9)))' < widget.html

# send (jq builds the JSON so the HTML is escaped correctly)
jq -n --rawfile html widget.html --arg chat "$CHAT_ID" \
  '{chat_id: ($chat|tonumber), html: $html, chat_data: "{\"m\":\"e\"}",
    caption: "Choose an option", allow_queries: true}' |
curl -s "$API/sendWidget" -H 'Content-Type: application/json' -d @-

# receive taps: allowed_updates must name the widget updates
curl -s "$API/getUpdates" -H 'Content-Type: application/json' \
  -d '{"timeout":50,"allowed_updates":["message","widget_query","shared_widget_query"]}'

# answer within 15 seconds (data up to 1024 bytes, optional)
curl -s "$API/answerWidgetQuery" -H 'Content-Type: application/json' \
  -d '{"widget_query_id":"8123456789012345678","data":"ok"}'

# change the widget's state (counts as a sent message: throttle)
curl -s "$API/editMessageWidgetData" -H 'Content-Type: application/json' \
  -d '{"chat_id":111111111,"message_id":4242,"chat_data":"{\"m\":\"p\",\"p\":40}"}'

# caption and buttons under the widget
curl -s "$API/editMessageCaption" -H 'Content-Type: application/json' \
  -d '{"chat_id":111111111,"message_id":4242,"caption":"Done"}'
```

Webhook: `setWebhook` with `"allowed_updates":[..., "widget_query", "shared_widget_query"]`.
