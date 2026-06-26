import os
import requests

token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not token:
    raise SystemExit("Missing TELEGRAM_BOT_TOKEN secret.")

url = f"https://api.telegram.org/bot{token}/getUpdates"
r = requests.get(url, timeout=20)
print(f"Telegram getUpdates status: {r.status_code}")

if r.status_code >= 400:
    print(r.text[:500])
    raise SystemExit("Telegram getUpdates failed. Check the bot token secret.")

data = r.json()
updates = data.get("result", [])

if not updates:
    print("")
    print("No updates found.")
    print("Go to your CatWatch Alerts Telegram group, send this message, then run this workflow again:")
    print("CatWatch test")
    raise SystemExit(0)

seen = set()
print("")
print("Possible TELEGRAM_CHAT_ID values:")
for u in updates:
    msg = u.get("message") or u.get("channel_post") or u.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id in seen or chat_id is None:
        continue
    seen.add(chat_id)
    title = chat.get("title") or chat.get("username") or chat.get("first_name") or "Unknown"
    typ = chat.get("type") or "unknown"
    print(f"CHAT_ID={chat_id} | type={typ} | name={title}")

print("")
print("Copy the CHAT_ID for your CatWatch Alerts group/channel into GitHub secret TELEGRAM_CHAT_ID.")
