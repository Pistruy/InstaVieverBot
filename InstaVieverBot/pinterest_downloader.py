import logging
import asyncio
import httpx
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from utils import get_random_user_agent, get_random_delay
import os
import json

logger = logging.getLogger(__name__)

async def resolve_pinterest_url(url: str) -> str:
    """Розгортає коротке посилання pin.it у повне."""
    if 'pin.it' not in url:
        return url
    headers = {
        'User-Agent': get_random_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            response = await client.get(url, headers=headers)
            resolved_url = str(response.url)
            logger.info(f"Розгорнуто pin.it: {url} -> {resolved_url}")
            return resolved_url
    except httpx.HTTPError as e:
        logger.error(f"Помилка розгортання pin.it: {str(e)}")
        return url

async def pinterest_login(page, username, password):
    """Авторизація на Pinterest через Playwright."""
    try:
        await page.goto('https://www.pinterest.com/login/', timeout=30000)
        await page.wait_for_load_state('networkidle', timeout=30000)
        await asyncio.sleep(get_random_delay())
        logger.info("Заповнюємо форму логіну Pinterest")
        await page.fill('input[id="email"]', username)
        await page.fill('input[id="password"]', password)
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(10000)
        if 'login' in page.url or 'auth' in page.url:
            logger.error("Авторизація не вдалася, можливо, потрібна CAPTCHA")
            await page.screenshot(path='InstaVieverBot/pinterest_login_screenshot.png')
            return False
        logger.info("Успішна авторизація на Pinterest")
        await page.context.storage_state(path='InstaVieverBot/pinterest_cookies.json')
        return True
    except PlaywrightTimeoutError:
        logger.error("Таймаут під час авторизації Pinterest")
        return False
    except Exception as e:
        logger.error(f"Помилка авторизації Pinterest: {str(e)}")
        return False

async def download_pinterest(url: str) -> list:
    """Завантажує медіа з Pinterest."""
    await asyncio.sleep(get_random_delay())
    cookies_file = 'InstaVieverBot/pinterest_cookies.json'
    username = os.getenv('PINTEREST_USERNAME')
    password = os.getenv('PINTEREST_PASSWORD')
    
    resolved_url = await resolve_pinterest_url(url)
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=get_random_user_agent())
            
            if os.path.exists(cookies_file):
                try:
                    with open(cookies_file, 'r') as f:
                        cookies = json.load(f)['cookies']
                    await context.add_cookies(cookies)
                    logger.info(f"Завантажено cookies з {cookies_file}")
                except json.JSONDecodeError:
                    logger.warning(f"Помилка формату {cookies_file}. Спроба авторизації.")

            page = await context.new_page()
            
            await page.goto(resolved_url, timeout=60000, wait_until='networkidle')
            if 'login' in page.url or 'auth' in page.url:
                logger.info("Потрібна авторизація для Pinterest")
                if not await pinterest_login(page, username, password):
                    await browser.close()
                    return None

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)

            media = []
            video_elements = await page.query_selector_all('video[src*="pinimg.com"]')
            for video in video_elements:
                src = await video.get_attribute('src')
                if src:
                    media.append({'type': 'video', 'url': src})
            
            image_elements = await page.query_selector_all('img[src*="pinimg.com"]')
            for img in image_elements:
                src = await img.get_attribute('src')
                if src and '75x75_RS' not in src and 'default_140.png' not in src and 'videos/thumbnails' not in src:
                    if src not in [m['url'] for m in media]:
                        media.append({'type': 'photo', 'url': src})

            await browser.close()
            
            if not media:
                logger.info("Pinterest медіа не знайдено")
                return None
            logger.info(f"Отримано Pinterest медіа: count={len(media)}")
            return media
    except PlaywrightTimeoutError:
        logger.error(f"Таймаут при завантаженні Pinterest: {resolved_url}")
        return None
    except Exception as e:
        logger.error(f"Помилка Pinterest: {str(e)}", exc_info=True)
        return None
