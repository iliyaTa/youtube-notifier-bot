import json
import re
import time
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


def send_photo(chat_id, photo_url, caption):
    try:
        resp = requests.post(f"{API}/sendPhoto", json={
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption,
        }, timeout=15)
        if resp.status_code != 200:
            # اگه عکس به هر دلیلی نشد، حداقل پیام متنی رو بفرست
            send_message(chat_id, caption)
    except Exception as e:
        print(f"خطا در ارسال عکس: {e}")
        send_message(chat_id, caption)


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
        link = entry.link
        is_short = "/shorts/" in link
        published_ts = None
        if getattr(entry, "published_parsed", None):
            published_ts = time.mktime(entry.published_parsed)
        videos.append({
            "id": entry.yt_videoid,
            "title": entry.title,
            "link": link,
            "is_short": is_short,
            "published_ts": published_ts,
        })
    return videos


def thumbnail_url(video_id):
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def get_chat(state, chat_id):
    key = str(chat_id)
    if key not in state["chats"]:
        state["chats"][key] = {"channels": {}, "seen": {}, "filters": {}}
    chat = state["chats"][key]
    chat.setdefault("filters", {})
    return chat


def get_filter(chat, channel_id):
    return chat["filters"].get(channel_id, "all")


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
                "/list\n"
                "/filter <آیدی کانال> <all|shorts|videos>\n"
                "/stats - آمار ۷ روز اخیر\n"
                "/test - فرستادن آخرین ویدیوی هر کانال (برای تست)\n"
                "/help - راهنمای کامل"
            )

        elif text.startswith("/help"):
            send_message(chat_id,
                "📖 راهنمای کامل دستورات:\n\n"
                "/add <لینک یا @هندل یا آیدی کانال>\n"
                "  یه کانال یوتیوب جدید اضافه می‌کنه تا ویدیوهاش رو نوتیف بگیری.\n"
                "  مثال: /add @MrBeast\n\n"
                "/remove <آیدی کانال>\n"
                "  یه کانال رو از لیست حذف می‌کنه. اگه بدون آیدی بزنی، لیست کانال‌ها رو نشون میده تا آیدی رو ببینی.\n\n"
                "/list\n"
                "  لیست کانال‌های ثبت‌شده به همراه آیدی و فیلتر فعلی هرکدوم رو نشون میده.\n\n"
                "/filter <آیدی کانال> <all|shorts|videos>\n"
                "  مشخص می‌کنه از یه کانال چه نوع محتوایی نوتیف بگیری:\n"
                "  all = همه، shorts = فقط شورت، videos = فقط ویدیوی عادی.\n"
                "  اگه بدون آرگومان بزنی، لیست کانال‌ها با فیلتر فعلی‌شون رو نشون میده.\n\n"
                "/stats\n"
                "  آمار ۷ روز اخیر هر کانال رو نشون میده (تعداد ویدیو و شورت).\n\n"
                "/test\n"
                "  آخرین ویدیوی هر کانال رو بدون چک کردن جدید بودن، برات می‌فرسته (برای تست ارسال پیام).\n\n"
                "/start\n"
                "  پیام خوش‌آمد و خلاصه‌ی دستورات.\n\n"
                "/help\n"
                "  همین راهنما."
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
            chat["filters"][channel_id] = "all"
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
            chat["filters"].pop(channel_id, None)
            send_message(chat_id, f"🗑 کانال «{name}» حذف شد.")

        elif text.startswith("/filter"):
            parts = text.split(maxsplit=2)
            if len(parts) < 3 or parts[2] not in ("all", "shorts", "videos"):
                if not chat["channels"]:
                    send_message(chat_id, "اول یه کانال با /add اضافه کن.")
                    continue
                lines = "\n".join(
                    f"{cid} - {name} (الان: {get_filter(chat, cid)})"
                    for cid, name in chat["channels"].items()
                )
                send_message(
                    chat_id,
                    "استفاده درست:\n/filter <آیدی کانال> <all|shorts|videos>\n\n"
                    "کانال‌های موجود:\n" + lines
                )
                continue
            channel_id, mode = parts[1], parts[2]
            if channel_id not in chat["channels"]:
                send_message(chat_id, "این کانال توی لیست نیست.")
                continue
            chat["filters"][channel_id] = mode
            name = chat["channels"][channel_id]
            mode_fa = {"all": "همه ویدیوها", "shorts": "فقط شورت", "videos": "فقط ویدیوی عادی"}[mode]
            send_message(chat_id, f"✅ فیلتر «{name}» روی «{mode_fa}» تنظیم شد.")

        elif text.startswith("/stats"):
            if not chat["channels"]:
                send_message(chat_id, "هیچ کانالی ثبت نشده. با /add اضافه کن.")
                continue
            send_message(chat_id, "در حال محاسبه آمار ۷ روز اخیر... ⏳")
            now = time.time()
            week_ago = now - 7 * 24 * 3600
            lines = []
            for channel_id, channel_name in chat["channels"].items():
                videos = fetch_latest_videos(channel_id)
                recent = [v for v in videos if v["published_ts"] and v["published_ts"] >= week_ago]
                shorts_count = sum(1 for v in recent if v["is_short"])
                videos_count = len(recent) - shorts_count
                lines.append(
                    f"• {channel_name}\n"
                    f"  کل: {len(recent)} | ویدیو: {videos_count} | شورت: {shorts_count}"
                )
            send_message(chat_id, "📊 آمار ۷ روز اخیر:\n\n" + "\n\n".join(lines))

        elif text.startswith("/test"):
            if not chat["channels"]:
                send_message(chat_id, "هیچ کانالی ثبت نشده. با /add اضافه کن.")
                continue
            send_message(chat_id, "در حال گرفتن آخرین ویدیوها... ⏳")
            for channel_id, channel_name in chat["channels"].items():
                videos = fetch_latest_videos(channel_id)
                if not videos:
                    send_message(chat_id, f"⚠️ نتونستم ویدیویی از «{channel_name}» بگیرم.")
                    continue
                v = videos[0]
                caption = f"🧪 تست - آخرین ویدیوی «{channel_name}»\n\n{v['title']}\n{v['link']}"
                send_photo(chat_id, thumbnail_url(v["id"]), caption)

        elif text.startswith("/list"):
            if not chat["channels"]:
                send_message(chat_id, "هیچ کانالی ثبت نشده. با /add اضافه کن.")
                continue
            lines = [
                f"• {name}\n  {cid}\n  فیلتر: {get_filter(chat, cid)}"
                for cid, name in chat["channels"].items()
            ]
            send_message(chat_id, "کانال‌های ثبت شده:\n\n" + "\n\n".join(lines))


def check_new_videos(state):
    for chat_id, chat in state["chats"].items():
        chat.setdefault("filters", {})
        for channel_id, channel_name in list(chat["channels"].items()):
            videos = fetch_latest_videos(channel_id)
            if not videos:
                continue
            seen_ids = chat["seen"].get(channel_id, [])
            new_videos = [v for v in videos if v["id"] not in seen_ids]

            if new_videos:
                mode = get_filter(chat, channel_id)
                to_send = new_videos
                if mode == "shorts":
                    to_send = [v for v in new_videos if v["is_short"]]
                elif mode == "videos":
                    to_send = [v for v in new_videos if not v["is_short"]]

                # محافظ: اگه به هر دلیلی تعداد زیادی ویدیو یهو "جدید" تشخیص داده شد
                # (مثلا باگ یا ریست شدن state)، فقط تازه‌ترین‌ها رو می‌فرستیم
                # تا سیل پیام به کاربر نریزیم.
                MAX_PER_RUN = 10
                capped = to_send[:MAX_PER_RUN]

                for v in reversed(capped):
                    kind = "🩳 شورت" if v["is_short"] else "🎬 ویدیو"
                    caption = f"{kind} جدید از «{channel_name}»\n\n{v['title']}\n{v['link']}"
                    send_photo(chat_id, thumbnail_url(v["id"]), caption)
                    time.sleep(0.4)  # جلوگیری از rate limit تلگرام

                # صرف نظر از فیلتر، همه‌ی آیدی‌های جدید رو seen ثبت می‌کنیم
                # تا بعداً با تغییر فیلتر دوباره فرستاده نشن
                merged = seen_ids + [v["id"] for v in new_videos]
                chat["seen"][channel_id] = merged[-300:]


def main():
    state = load_state()
    process_updates(state)
    check_new_videos(state)
    save_state(state)


if __name__ == "__main__":
    main()
