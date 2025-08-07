from instagrapi import Client
from instagrapi.types import Media
import os
import logging
import json
from utils import get_random_user_agent

logger = logging.getLogger(__name__)

def get_instagram_client():
    cl = Client()
    cl.logger.setLevel(logging.DEBUG)
    cl.set_user_agent(get_random_user_agent())
    session_file = "InstaVieverBot/instagram_session.json"
    proxy = os.getenv("PROXY")
    
    if proxy:
        cl.set_proxy(proxy)
        logger.debug(f"Використовуємо проксі: {proxy}")
    
    username = os.getenv("IG_USERNAME")
    password = os.getenv("IG_PASSWORD")
    
    if not username or not password:
        logger.error("IG_USERNAME або IG_PASSWORD не встановлено")
        raise ValueError("IG_USERNAME або IG_PASSWORD не встановлено")
    
    logger.debug(f"Використовуємо username: {username}")
    logger.debug(f"Використовуємо user-agent: {cl.user_agent}")
    
    if os.path.exists(session_file):
        try:
            cl.load_settings(session_file)
            logger.info("Сесію Instagram завантажено з файлу")
        except Exception as e:
            logger.error(f"Помилка завантаження сесії: {str(e)}", exc_info=True)
            cl.login(username, password)
            cl.dump_settings(session_file)
            logger.info("Нова сесія Instagram створена та збережена")
    else:
        cl.login(username, password)
        cl.dump_settings(session_file)
        logger.info("Нова сесія Instagram створена та збережена")
    
    return cl

async def download_instagram(url):
    try:
        cl = get_instagram_client()
        media_pk = cl.media_pk_from_url(url)
        media = cl.media_info(media_pk)
        logger.info(f"Завантажено медіа з Instagram: {url}, type={media.media_type}, resources_count={len(media.resources) if media.resources else 0}")
        return media
    except Exception as e:
        logger.error(f"Помилка instagrapi: {str(e)}", exc_info=True)
        return None

async def download_instagram_stories(url):
    try:
        cl = get_instagram_client()
        username = url.split("instagram.com/")[1].rstrip('/').split('/')[0]
        user_id = cl.user_id_from_username(username)
        stories = cl.user_stories(user_id)
        if not stories:
            logger.info(f"Stories для {username} відсутні або недоступні")
            return None
        logger.info(f"Завантажено Instagram Stories: count={len(stories)}")
        return stories
    except Exception as e:
        logger.error(f"Помилка завантаження Stories: {str(e)}", exc_info=True)
        return None