import json
import re
from pathlib import Path
import subprocess

import requests

BOT_TOKEN = subprocess.os.environ["BOT_TOKEN"]
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
STATE_FILE = Path("state.json")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_update_id": 0, "chats": {}}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def send_message(chat_id, text):
    try:
        requests.post(f"{API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=15)
    except Exception as e:
        print(f"خطا در ارسال پیام: {e}")


def resolve_channel_id(text: str):
    text = text.strip()
    m = re.fullmatch(r"UC[\w-]{22}", text)
    if m:
        url = f"https://www.youtube.com/channel/{text}"
    elif text.startswith("http"):
        url = text
    elif text.startswith("@"):
        url = f"https://www.youtube.com/{text}"
    else:
        url = f"https://www.youtube.com/@{text}"

    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    except Exception as e:
        print(f"خطا در گرفتن صفحه کانال: {e}")
        return None

    if resp.status_code != 200:
        return None

    html = resp.text
    m = re.search(r'"channelId":"(UC[\w-]{22})"', html)
    if not m:
        m = re.search(r'channel_id=(UC[\w-]{22})', html)
    if not m:
        return None
    channel_id = m.group(1)

    name_m = re.search(r'"author":"([^"]+)"', html)
    if not name_m:
        name_m = re.search(r'<title>([^<]+)</title>', html)
    channel_name = name_m.group(1) if name_m else channel_id

    return channel_id, channel_name


def fetch_latest_videos(channel_id: str):
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        resp = requests.get(feed_url, timeout=15)
    except Exception as e:
        print(f"خطا در گرفتن فید: {e}")
        return []
    if resp.status_code != 200:
        return []

    import feedparser
    feed = feedparser.parse(resp.text)
    videos = []
    for entry in feed.entries:
        videos.append({
            "id": entry.yt_videoid,
            "title": entry.title,
            "link": entry.link,
        })
    return videos


def get_chat(state, chat_id):
    key = str(chat_id)
    if key not in state["chats"]:
        state["chats"][key] = {"channels": {}, "seen": {}}
    return state["chats"][key]


def process_updates(state):
    resp = requests.get(f"{API}/getUpdates", params={
        "offset": state["last_update_id"] + 1,
        "timeout": 0,
    }, timeout=20)
    updates = resp.json().get("result", [])

    for update in updates:
        state["last_update_id"] = update["update_id"]
        msg = update.get("message")
        if not msg or "text" not in msg:
            continue

        chat_id = msg["chat"]["id"]
        text = msg["text"].strip()
        chat = get_chat(state, chat_id)

        if text.startswith("/start"):
            send_message(chat_id,
                "سلام! 👋\n"
                "/add <لینک یا @هندل یا آیدی کانال>\n"
                "/remove <آیدی کانال>\n"
                "/list"
            )

        elif text.startswith("/add"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                send_message(chat_id, "مثال: /add @MrBeast")
                continue
            query = parts[1]
            result = resolve_channel_id(query)
            if not result:
                send_message(chat_id, "❌ کانال پیدا نشد.")
                continue
            channel_id, channel_name = result
            if channel_id in chat["channels"]:
                send_message(chat_id, f"کانال «{channel_name}» از قبل توی لیست هست.")
                continue
            videos = fetch_latest_videos(channel_id)
            chat["channels"][channel_id] = channel_name
            chat["seen"][channel_id] = [v["id"] for v in videos]
            send_message(chat_id, f"✅ کانال «{channel_name}» اضافه شد.")

        elif text.startswith("/remove"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                if not chat["channels"]:
                    send_message(chat_id, "لیست خالیه.")
                    continue
                lines = "\n".join(f"{cid} - {name}" for cid, name in chat["channels"].items())
                send_message(chat_id, f"آیدی کانالی که میخوای حذف کنی رو بفرست:\n{lines}")
                continue
            channel_id = parts[1].strip()
            if channel_id not in chat["channels"]:
                send_message(chat_id, "این کانال توی لیست نیست.")
                continue
            name = chat["channels"].pop(channel_id)
            chat["seen"].pop(channel_id, None)
            send_message(chat_id, f"🗑 کانال «{name}» حذف شد.")

        elif text.startswith("/list"):
            if not chat["channels"]:
                send_message(chat_id, "هیچ کانالی ثبت نشده. با /add اضافه کن.")
                continue
            lines = [f"• {name}\n  {cid}" for cid, name in chat["channels"].items()]
            send_message(chat_id, "کانال‌های ثبت شده:\n\n" + "\n\n".join(lines))


def check_new_videos(state):
    for chat_id, chat in state["chats"].items():
        for channel_id, channel_name in list(chat["channels"].items()):
            videos = fetch_latest_videos(channel_id)
            if not videos:
                continue
            seen_ids = chat["seen"].get(channel_id, [])
            new_videos = [v for v in videos if v["id"] not in seen_ids]

            if new_videos:
                for v in reversed(new_videos):
                    text = f"🎬 ویدیو جدید از «{channel_name}»\n\n{v['title']}\n{v['link']}"
                    send_message(chat_id, text)
                chat["seen"][channel_id] = [v["id"] for v in videos]


def main():
    state = load_state()
    process_updates(state)
    check_new_videos(state)
    save_state(state)


if __name__ == "__main__":
    main()
