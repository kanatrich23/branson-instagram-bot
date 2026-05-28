import os
import json
import time
import logging
import requests
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================
IG_APP_ID = os.environ.get("IG_APP_ID", "1314989590783813")
IG_APP_SECRET = os.environ.get("IG_APP_SECRET", "758e5f789208ba8b91f166f31df8a779")
IG_USER_ID = os.environ.get("IG_USER_ID", "17841401410456472")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")  # короткий токен при первом запуске

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8787132108:AAHXnoY38-SwxpJ3oU0O2tFCU5jiI7rZRRg")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "-1003764501174")

# Файл для хранения состояния
STATE_FILE = "state.json"
CHECK_INTERVAL = 1800  # проверять каждые 30 минут

# ============================================================
# УПРАВЛЕНИЕ ТОКЕНОМ
# ============================================================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"access_token": IG_ACCESS_TOKEN, "last_post_id": None, "token_expires": 0}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def exchange_token(short_token):
    """Обменять короткий токен на длинный (60 дней)"""
    url = "https://graph.instagram.com/access_token"
    params = {
        "grant_type": "ig_exchange_token",
        "client_secret": IG_APP_SECRET,
        "access_token": short_token
    }
    resp = requests.get(url, params=params)
    data = resp.json()
    if "access_token" in data:
        logger.info("✅ Токен успешно обменян на длинный")
        expires_in = data.get("expires_in", 5184000)  # 60 дней
        return data["access_token"], time.time() + expires_in
    else:
        logger.error(f"❌ Ошибка обмена токена: {data}")
        return short_token, time.time() + 3600

def refresh_token(token):
    """Обновить токен до истечения"""
    url = "https://graph.instagram.com/refresh_access_token"
    params = {
        "grant_type": "ig_refresh_token",
        "access_token": token
    }
    resp = requests.get(url, params=params)
    data = resp.json()
    if "access_token" in data:
        logger.info("✅ Токен успешно обновлён")
        expires_in = data.get("expires_in", 5184000)
        return data["access_token"], time.time() + expires_in
    else:
        logger.error(f"❌ Ошибка обновления токена: {data}")
        return token, time.time() + 86400

# ============================================================
# INSTAGRAM API
# ============================================================
def get_latest_posts(token, limit=5):
    """Получить последние посты из Instagram"""
    url = f"https://graph.instagram.com/v22.0/me/media"
    params = {
        "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,permalink",
        "limit": limit,
        "access_token": token
    }
    resp = requests.get(url, params=params)
    data = resp.json()
    
    if "data" in data:
        return data["data"]
    else:
        logger.error(f"❌ Ошибка получения постов: {data}")
        return []

# ============================================================
# TELEGRAM API
# ============================================================
def send_photo(caption, image_url):
    """Отправить фото в Telegram канал"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "photo": image_url,
        "caption": caption[:1024] if caption else "",
        "parse_mode": "HTML"
    }
    resp = requests.post(url, json=payload)
    return resp.json()

def send_video(caption, video_url):
    """Отправить видео в Telegram канал"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "video": video_url,
        "caption": caption[:1024] if caption else "",
        "parse_mode": "HTML"
    }
    resp = requests.post(url, json=payload)
    return resp.json()

def send_message(text):
    """Отправить текстовое сообщение"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": text[:4096],
        "parse_mode": "HTML"
    }
    resp = requests.post(url, json=payload)
    return resp.json()

def post_to_telegram(post):
    """Опубликовать Instagram пост в Telegram"""
    media_type = post.get("media_type", "IMAGE")
    caption = post.get("caption", "")
    permalink = post.get("permalink", "")
    
    # Добавляем ссылку на оригинал
    full_caption = f"{caption}\n\n🔗 <a href='{permalink}'>Смотреть в Instagram</a>" if permalink else caption

    if media_type == "IMAGE":
        image_url = post.get("media_url")
        if image_url:
            result = send_photo(full_caption, image_url)
            return result
    elif media_type in ["VIDEO", "REELS"]:
        video_url = post.get("media_url")
        if video_url:
            result = send_video(full_caption, video_url)
            return result
    elif media_type == "CAROUSEL_ALBUM":
        # Для карусели отправляем первое фото
        image_url = post.get("media_url")
        if image_url:
            result = send_photo(full_caption + "\n📸 Карусель — смотрите все фото в Instagram", image_url)
            return result
    
    # Если нет медиа — отправляем текст
    return send_message(full_caption)

# ============================================================
# ОСНОВНОЙ ЦИКЛ
# ============================================================
def main():
    logger.info("🚀 Branson Social Bot запущен")
    
    state = load_state()
    token = state.get("access_token", IG_ACCESS_TOKEN)
    token_expires = state.get("token_expires", 0)
    last_post_id = state.get("last_post_id")
    
    # Обмениваем короткий токен на длинный при первом запуске
    if token and token_expires == 0:
        logger.info("🔄 Обмениваем короткий токен на длинный...")
        token, token_expires = exchange_token(token)
        state["access_token"] = token
        state["token_expires"] = token_expires
        save_state(state)
    
    while True:
        try:
            # Обновляем токен если осталось меньше 7 дней
            if token_expires and time.time() > token_expires - 604800:
                logger.info("🔄 Обновляем токен...")
                token, token_expires = refresh_token(token)
                state["access_token"] = token
                state["token_expires"] = token_expires
                save_state(state)
            
            # Получаем последние посты
            posts = get_latest_posts(token)
            
            if not posts:
                logger.info("📭 Новых постов нет")
            else:
                # Проверяем новые посты
                new_posts = []
                for post in posts:
                    if post["id"] == last_post_id:
                        break
                    new_posts.append(post)
                
                if not last_post_id:
                    # Первый запуск — берём только самый последний пост
                    new_posts = [posts[0]] if posts else []
                    logger.info(f"🆕 Первый запуск — публикуем последний пост")
                
                # Публикуем новые посты (от старых к новым)
                for post in reversed(new_posts):
                    logger.info(f"📤 Публикуем пост {post['id']}...")
                    result = post_to_telegram(post)
                    if result.get("ok"):
                        logger.info(f"✅ Пост опубликован в Telegram")
                        last_post_id = post["id"]
                        state["last_post_id"] = last_post_id
                        save_state(state)
                    else:
                        logger.error(f"❌ Ошибка публикации: {result}")
                    time.sleep(2)
            
            logger.info(f"⏳ Следующая проверка через {CHECK_INTERVAL // 60} минут")
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
