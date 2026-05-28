import os
import json
import time
import logging
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8787132108:AAHXnoY38-SwxpJ3oU0O2tFCU5jiI7rZRRg")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "-1003764501174")

STATE_FILE = "state.json"
CHECK_INTERVAL = 1800

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_post_id": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def get_latest_posts(limit=5):
    # Новый Instagram Login API использует /me/media
    url = "https://graph.instagram.com/me/media"
    params = {
        "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,permalink",
        "limit": limit,
        "access_token": IG_ACCESS_TOKEN
    }
    resp = requests.get(url, params=params)
    data = resp.json()
    if "data" in data:
        return data["data"]
    else:
        logger.error(f"❌ Ошибка получения постов: {data}")
        return []

def send_photo(caption, image_url):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "photo": image_url,
        "caption": caption[:1024] if caption else "",
        "parse_mode": "HTML"
    }
    return requests.post(url, json=payload).json()

def send_video(caption, video_url):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "video": video_url,
        "caption": caption[:1024] if caption else "",
        "parse_mode": "HTML"
    }
    return requests.post(url, json=payload).json()

def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": text[:4096],
        "parse_mode": "HTML"
    }
    return requests.post(url, json=payload).json()

def post_to_telegram(post):
    media_type = post.get("media_type", "IMAGE")
    caption = post.get("caption", "")
    permalink = post.get("permalink", "")
    full_caption = f"{caption}\n\n🔗 <a href='{permalink}'>Смотреть в Instagram</a>" if permalink else caption

    if media_type == "IMAGE":
        image_url = post.get("media_url")
        if image_url:
            return send_photo(full_caption, image_url)
    elif media_type in ["VIDEO", "REELS"]:
        video_url = post.get("media_url")
        if video_url:
            return send_video(full_caption, video_url)
    elif media_type == "CAROUSEL_ALBUM":
        image_url = post.get("media_url")
        if image_url:
            return send_photo(full_caption + "\n📸 Карусель — смотрите все фото в Instagram", image_url)
    return send_message(full_caption)

def main():
    logger.info("🚀 Branson Social Bot запущен")

    if not IG_ACCESS_TOKEN:
        logger.error("❌ IG_ACCESS_TOKEN не задан!")
        return

    state = load_state()
    last_post_id = state.get("last_post_id")

    while True:
        try:
            posts = get_latest_posts()

            if posts:
                new_posts = []
                for post in posts:
                    if post["id"] == last_post_id:
                        break
                    new_posts.append(post)

                if not last_post_id:
                    new_posts = [posts[0]] if posts else []
                    logger.info("🆕 Первый запуск — публикуем последний пост")

                for post in reversed(new_posts):
                    logger.info(f"📤 Публикуем пост {post['id']}...")
                    result = post_to_telegram(post)
                    if result.get("ok"):
                        logger.info("✅ Пост опубликован в Telegram")
                        last_post_id = post["id"]
                        state["last_post_id"] = last_post_id
                        save_state(state)
                    else:
                        logger.error(f"❌ Ошибка публикации: {result}")
                    time.sleep(2)
            else:
                logger.info("📭 Новых постов нет")

            logger.info(f"⏳ Следующая проверка через {CHECK_INTERVAL // 60} минут")
            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
