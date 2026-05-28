import os
import json
import time
import logging
import re
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8787132108:AAHXnoY38-SwxpJ3oU0O2tFCU5jiI7rZRRg")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "-1003764501174")

STATE_FILE = "state.json"
BACKFILL_LIMIT = 200
INTERVAL_BACKFILL = 3600
INTERVAL_MONITOR = 1800

# Старые номера в любом формате
OLD_NUMBERS = [
    '77767485353', '77763653553', '77767345353',
    '+77767485353', '+77763653553', '+77767345353',
]

NEW_PHONE_BLOCK = 'Контакты:\n📱 <a href="https://wa.me/77767355353">WhatsApp: +7 776 735 5353</a>\n🌐 <a href="https://branson-recruitment.kz">branson-recruitment.kz</a>'

def clean_caption(text):
    if not text:
        return text

    # Проверяем есть ли старые номера в тексте
    has_old_numbers = any(num.replace('+', '') in text.replace(' ', '').replace('-', '') 
                         for num in OLD_NUMBERS)

    cleaned = text

    # Удаляем строки содержащие старые номера (вместе с именами)
    lines = cleaned.split('\n')
    new_lines = []
    skip_next = False
    for line in lines:
        line_clean = line.replace(' ', '').replace('-', '').replace('+', '')
        is_old_number_line = any(num.replace('+', '') in line_clean for num in OLD_NUMBERS)
        
        if is_old_number_line:
            continue  # пропускаем строку со старым номером
        new_lines.append(line)

    cleaned = '\n'.join(new_lines)

    # Удаляем заголовок "Наши телефоны:" если остался пустым
    cleaned = re.sub(r'Наши телефоны:?\s*\n\n', '', cleaned)
    cleaned = re.sub(r'Наши телефоны:?\s*$', '', cleaned, flags=re.MULTILINE)

    # Убираем лишние пустые строки
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = cleaned.strip()

    # Если были старые номера — добавляем новый номер
    if has_old_numbers:
        cleaned = cleaned + f"\n\n{NEW_PHONE_BLOCK}"

    return cleaned

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "last_post_id": None,
        "backfill_done": False,
        "backfill_queue": [],
        "backfill_posts_data": {}
    }

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def get_all_posts(limit=200):
    all_posts = []
    url = "https://graph.instagram.com/me/media"
    params = {
        "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,permalink",
        "limit": 25,
        "access_token": IG_ACCESS_TOKEN
    }
    while len(all_posts) < limit:
        resp = requests.get(url, params=params)
        data = resp.json()
        if "data" not in data:
            logger.error(f"❌ Ошибка получения постов: {data}")
            break
        all_posts.extend(data["data"])
        next_cursor = data.get("paging", {}).get("cursors", {}).get("after")
        if not next_cursor:
            break
        params["after"] = next_cursor
        time.sleep(1)
    return all_posts[:limit]

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

    cleaned = clean_caption(caption)
    full_caption = f"{cleaned}\n\n🔗 <a href='{permalink}'>Смотреть в Instagram</a>" if permalink else cleaned

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

    if not state.get("backfill_done"):
        if not state.get("backfill_queue"):
            logger.info("📥 Загружаем все посты из Instagram...")
            posts = get_all_posts(BACKFILL_LIMIT)
            logger.info(f"📊 Найдено постов: {len(posts)}")

            queue = [p["id"] for p in reversed(posts)]
            posts_data = {p["id"]: p for p in posts}

            last_id = state.get("last_post_id")
            if last_id and last_id in queue:
                idx = queue.index(last_id)
                queue = queue[idx+1:]

            state["backfill_queue"] = queue
            state["backfill_posts_data"] = posts_data
            save_state(state)
            logger.info(f"📋 В очереди {len(queue)} постов. Темп: 20/день (каждый час)")

        queue = state.get("backfill_queue", [])
        posts_data = state.get("backfill_posts_data", {})

        if queue:
            post_id = queue[0]
            post = posts_data.get(post_id)

            if post:
                logger.info(f"📤 Публикуем пост {post_id} (осталось: {len(queue)})")
                result = post_to_telegram(post)
                if result.get("ok"):
                    logger.info(f"✅ Опубликован. Осталось: {len(queue)-1}")
                    state["backfill_queue"] = queue[1:]
                    state["last_post_id"] = post_id
                    save_state(state)
                else:
                    logger.error(f"❌ Ошибка: {result}")
                    state["backfill_queue"] = queue[1:]
                    save_state(state)
            else:
                state["backfill_queue"] = queue[1:]
                save_state(state)

            remaining = len(state["backfill_queue"])
            if remaining == 0:
                logger.info("🎉 Все посты опубликованы! Переключаемся на мониторинг.")
                state["backfill_done"] = True
                save_state(state)
            else:
                days_left = remaining / 20
                logger.info(f"⏳ Осталось: {remaining} (~{days_left:.1f} дней). Следующий через 1 час.")
                time.sleep(INTERVAL_BACKFILL)
                main()
        else:
            state["backfill_done"] = True
            save_state(state)
            main()

    else:
        logger.info("👁 Режим мониторинга новых постов")
        while True:
            try:
                resp = requests.get("https://graph.instagram.com/me/media", params={
                    "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,permalink",
                    "limit": 5,
                    "access_token": IG_ACCESS_TOKEN
                })
                posts = resp.json().get("data", [])
                last_post_id = state.get("last_post_id")
                new_posts = []
                for post in posts:
                    if post["id"] == last_post_id:
                        break
                    new_posts.append(post)

                if new_posts:
                    for post in reversed(new_posts):
                        logger.info(f"📤 Новый пост: {post['id']}")
                        result = post_to_telegram(post)
                        if result.get("ok"):
                            logger.info("✅ Опубликован в Telegram")
                            state["last_post_id"] = post["id"]
                            save_state(state)
                        time.sleep(2)
                else:
                    logger.info("📭 Новых постов нет")

                logger.info("⏳ Следующая проверка через 30 минут")
                time.sleep(INTERVAL_MONITOR)

            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
                time.sleep(60)

if __name__ == "__main__":
    main()
