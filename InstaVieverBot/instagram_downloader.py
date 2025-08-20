import os
import json
import logging
import asyncio
import time
from instagrapi import Client
from instagrapi.exceptions import ClientError, ClientForbiddenError, UnknownError
from utils import get_random_user_agent, get_random_delay
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

async def browser_login(username, password, user_agent):
    """Логін через Playwright для оновлення сесії."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=user_agent)
            page = await context.new_page()
            try:
                await page.goto('https://www.instagram.com/accounts/login/', timeout=60000)  # Збільшено таймаут
                await page.wait_for_load_state('networkidle', timeout=60000)
                await asyncio.sleep(get_random_delay())
                logger.info("Заповнюємо форму логіну Instagram")
                await page.fill('input[name="username"]', username)
                await page.fill('input[name="password"]', password)
                await page.click('button[type="submit"]')
                await page.wait_for_timeout(15000)  # Збільшено затримку після кліку
                if 'login' in page.url or 'challenge' in page.url:
                    logger.error("Авторизація не вдалася, можливо, потрібна CAPTCHA")
                    await page.screenshot(path='InstaVieverBot/instagram_login_screenshot.png')
                    return None
                storage_state = await context.storage_state()
                return storage_state
            finally:
                await context.close()
                await browser.close()
    except PlaywrightTimeoutError:
        logger.error("Таймаут під час авторизації Instagram. Спробуйте збільшити таймаут або використовувати проксі.")
        return None
    except Exception as e:
        logger.error(f"Помилка авторизації через Playwright: {str(e)}")
        return None

def convert_playwright_to_instagrapi(storage_state, user_agent):
    """Конвертує Playwright storage state у формат instagrapi."""
    if not storage_state:
        return None
    session = {
        "authorization_data": {},
        "cookies": {},
        "last_login": time.time(),
        "device_settings": {
            "app_version": "269.0.0.18.75",
            "android_version": 26,
            "android_release": "8.0.0",
            "dpi": "480dpi",
            "resolution": "1080x1920",
            "manufacturer": "OnePlus",
            "device": "devitron",
            "model": "6T Dev",
            "cpu": "qcom",
            "version_code": "314665256"
        },
        "user_agent": user_agent,
        "country": "US",
        "country_code": 1,
        "locale": "en_US",
        "timezone_offset": -14400
    }
    for cookie in storage_state.get("cookies", []):
        if "instagram.com" in cookie["domain"]:
            session["cookies"][cookie["name"]] = cookie["value"]
            if cookie["name"] == "sessionid":
                session["authorization_data"]["sessionid"] = cookie["value"]
    return session

async def get_instagram_client():
    """Отримує клієнт instagrapi з сесією або авторизацією."""
    cl = Client()
    cl.delay_range = [5, 15]  # Збільшено затримки
    cl.request_timeout = 30  # Збільшено таймаут
    session_file = "InstaVieverBot/instagram_session.json"
    user_agent = get_random_user_agent()
    cl.set_user_agent(user_agent)
    # Додайте проксі, якщо є (замініть на ваш)
    # cl.set_proxy("http://your_proxy:port")

    if os.path.exists(session_file):
        try:
            with open(session_file, "r") as f:
                session = json.load(f)
            last_login = session.get("last_login", 0)
            if time.time() - last_login < 24 * 3600:
                cl.set_settings(session)
                logger.info("Завантажено сесію з instagram_session.json")
                try:
                    await asyncio.sleep(get_random_delay())
                    cl.get_timeline_feed()
                    logger.info("Сесія валідна")
                    return cl
                except Exception as e:
                    logger.warning(f"Сесія невалідна: {str(e)}. Спроба авторизації.")
            else:
                logger.info("Сесія застаріла, потрібна повторна авторизація")
        except json.JSONDecodeError:
            logger.warning("Помилка формату instagram_session.json. Спроба авторизації.")
        except Exception as e:
            logger.warning(f"Помилка завантаження сесії: {str(e)}. Спроба авторизації.")

    username = os.getenv('IG_USERNAME')
    password = os.getenv('IG_PASSWORD')
    if not username or not password:
        logger.error("INSTAGRAM_USERNAME або INSTAGRAM_PASSWORD не встановлено")
        raise ValueError("INSTAGRAM_USERNAME або INSTAGRAM_PASSWORD не встановлено")

    try:
        await asyncio.sleep(get_random_delay())
        storage_state = await browser_login(username, password, user_agent)
        if storage_state:
            session = convert_playwright_to_instagrapi(storage_state, user_agent)
            if session:
                cl.set_settings(session)
                with open(session_file, "w") as f:
                    json.dump(session, f)
                logger.info("Сесію збережено через Playwright")
                return cl
        logger.warning("Playwright авторизація не вдалася. Рекомендуємо ручний експорт сесії.")
        # Якщо Playwright провалився, не намагаємося cl.login(), щоб уникнути циклу
        raise Exception("Автоматизована авторизація провалилася. Виконайте ручний експорт сесії з браузера.")
    except Exception as e:
        logger.error(f"Помилка авторизації: {str(e)}")
        raise Exception("Помилка авторизації. Можливо, потрібна CAPTCHA або оновлення CSRF-токена. Спробуйте ручний експорт сесії.")

async def download_instagram(url: str):
    """Завантажує медіа з Instagram поста."""
    try:
        cl = await get_instagram_client()
        await asyncio.sleep(get_random_delay())
        media_pk = cl.media_pk_from_url(url)
        result = cl.private_request(f"media/{media_pk}/info/")["items"][0]
        media_type = result.get("media_type")
        logger.info(f"Завантажено Instagram медіа: type={media_type}")

        class Media:
            def __init__(self, data):
                self.media_type = data.get("media_type")
                self.thumbnail_url = data.get("image_versions2", {}).get("candidates", [{}])[0].get("url")
                self.video_url = data.get("video_versions", [{}])[0].get("url") if self.media_type == 2 else None
                self.resources = []
                if self.media_type == 8:
                    for item in data.get("carousel_media", []):
                        resource = Media(item)
                        self.resources.append(resource)

        media = Media(result)
        return media
    except UnknownError as e:
        if "useragent mismatch" in str(e).lower():
            logger.error("Помилка useragent mismatch. Очищаємо сесію та повторюємо авторизацію.")
            if os.path.exists("InstaVieverBot/instagram_session.json"):
                os.remove("InstaVieverBot/instagram_session.json")
            cl = await get_instagram_client()  # Повторна авторизація
            await asyncio.sleep(get_random_delay())
            media_pk = cl.media_pk_from_url(url)
            result = cl.private_request(f"media/{media_pk}/info/")["items"][0]
            media_type = result.get("media_type")
            logger.info(f"Завантажено Instagram медіа після повторної авторизації: type={media_type}")
            
            class Media:
                def __init__(self, data):
                    self.media_type = data.get("media_type")
                    self.thumbnail_url = data.get("image_versions2", {}).get("candidates", [{}])[0].get("url")
                    self.video_url = data.get("video_versions", [{}])[0].get("url") if self.media_type == 2 else None
                    self.resources = []
                    if self.media_type == 8:
                        for item in data.get("carousel_media", []):
                            resource = Media(item)
                            self.resources.append(resource)

            media = Media(result)
            return media
        else:
            logger.error(f"Помилка завантаження Instagram медіа: {str(e)}", exc_info=True)
            return None
    except Exception as e:
        logger.error(f"Помилка завантаження Instagram медіа: {str(e)}", exc_info=True)
        return None

async def download_instagram_stories(url: str):
    """Завантажує Instagram Stories."""
    try:
        cl = await get_instagram_client()
        await asyncio.sleep(get_random_delay())
        username = url.split("/")[-2] if url.endswith("/") else url.split("/")[-1]
        user_id = cl.user_id_from_username(username)
        stories = cl.user_stories(user_id)
        logger.info(f"Завантажено {len(stories)} Instagram Stories для {username}")
        return stories
    except Exception as e:
        logger.error(f"Помилка завантаження Instagram Stories: {str(e)}", exc_info=True)
        return None
