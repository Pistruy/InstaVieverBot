import telegram
from telegram import ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto, InputMediaVideo, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import json
import os
from instagrapi import Client
import logging
import asyncio
import aiohttp
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from bs4 import BeautifulSoup
import random
import time
from collections import deque
import re
try:
    import brotli
except ImportError:
    brotli = None
try:
    import brotlipy
except ImportError:
    brotlipy = None

# Налаштування логування
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота, Instagram-акаунт і проксі
TOKEN = os.getenv('BOT_TOKEN')
IG_USERNAME = os.getenv('IG_USERNAME', 'Kubgodua')
IG_PASSWORD = os.getenv('IG_PASSWORD', 'wearechempion')
TIKTOK_TOKEN = os.getenv('TIKTOK_TOKEN')
PROXY = os.getenv('PROXY')

# Ліміти запитів
REQUEST_LIMITS = {
    'instagram': {'limit': 50, 'reset_interval': 3600},
    'tiktok': {'limit': 500, 'reset_interval': 86400},
    'pinterest': {'limit': 500, 'reset_interval': 86400}
}
REQUEST_COUNTS_FILE = "request_counts.json"

# Список User-Agent для ротації
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
]

# Зберігання останніх затримок для унікальності
DELAY_HISTORY = deque(maxlen=3)

def load_request_counts():
    try:
        with open(REQUEST_COUNTS_FILE, "r") as f:
            return json.load(f)
    except:
        return {
            'instagram': {'count': 0, 'last_reset': time.time()},
            'tiktok': {'count': 0, 'last_reset': time.time()},
            'pinterest': {'count': 0, 'last_reset': time.time()}
        }

def save_request_counts(counts):
    with open(REQUEST_COUNTS_FILE, "w") as f:
        json.dump(counts, f)

async def check_request_limit(platform, update, context):
    counts = load_request_counts()
    current_time = time.time()
    platform_data = counts.get(platform, {'count': 0, 'last_reset': current_time})
    
    reset_interval = REQUEST_LIMITS[platform]['reset_interval']
    if current_time - platform_data['last_reset'] >= reset_interval:
        platform_data['count'] = 0
        platform_data['last_reset'] = current_time
        counts[platform] = platform_data
        save_request_counts(counts)
    
    if platform_data['count'] >= REQUEST_LIMITS[platform]['limit']:
        wait_time = reset_interval - (current_time - platform_data['last_reset'])
        logger.warning(f"Досягнуто ліміт для {platform}: {platform_data['count']}/{REQUEST_LIMITS[platform]['limit']}. Чекаємо {wait_time} секунд.")
        await update.message.reply_text("Будь ласка, надсилайте не більше одного посилання за раз.")
        await asyncio.sleep(wait_time)
        platform_data['count'] = 0
        platform_data['last_reset'] = current_time
        counts[platform] = platform_data
        save_request_counts(counts)
        return False
    
    platform_data['count'] += 1
    counts[platform] = platform_data
    save_request_counts(counts)
    logger.info(f"Запит до {platform}: {platform_data['count']}/{REQUEST_LIMITS[platform]['limit']}")
    return True

def get_random_delay():
    while True:
        delay = random.uniform(1, 6)
        rounded_delay = round(delay, 2)
        if rounded_delay not in DELAY_HISTORY:
            DELAY_HISTORY.append(rounded_delay)
            return rounded_delay

def get_random_user_agent():
    return random.choice(USER_AGENTS)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Надіслати посилання")],
        [KeyboardButton("Допомога")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🌟 Привіт! Я @InstaViewerBot. Надішли посилання на Instagram (пост або профіль для Stories), TikTok або Pinterest-пост, і я покажу всі фото чи відео! 📸",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Як користуватися ботом:*\n"
        "1. Надішли посилання на Instagram-пост (https://www.instagram.com/p/XXXXX/), профіль для Stories (https://www.instagram.com/username/), TikTok-відео (https://www.tiktok.com/@user/video/XXXXX) або Pinterest-пост (https://www.pinterest.com/pin/XXXXX/).\n"
        "2. Я поверну всі фото, відео або Stories!\n"
        "📌 *Порада:* Переконайся, що контент публічний.\n"
        "Інші команди: /start, /about, /stats, /feedback, /donate",
        parse_mode="Markdown"
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Я @InstaViewerBot — твій помічник для швидкого перегляду Instagram, TikTok та Pinterest-контенту без переходів! "
        "Створений для зручності та швидкості. 😎"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    try:
        with open("stats.json", "r") as f:
            stats = json.load(f)
        count = stats.get(user_id, 0)
        await update.message.reply_text(f"📊 Ти надіслав {count} посилань!")
    except:
        await update.message.reply_text("Ще немає статистики. Надішли перше посилання!")

async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✍️ Напиши свій відгук чи пропозицію, і ми розглянемо її!")

async def donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💙 Підтримайте українських розробників! Ваш донат допоможе нам створювати ще крутіші проєкти!\n"
        "💳 Monobank: 7777 4444 7777 4444",
        parse_mode="Markdown"
    )

def save_stats(user_id, link):
    try:
        with open("stats.json", "r") as f:
            stats = json.load(f)
    except:
        stats = {}
    stats[str(user_id)] = stats.get(str(user_id), 0) + 1
    with open("stats.json", "w") as f:
        json.dump(stats, f)

async def get_instagram_media(url, update, context):
    if not await check_request_limit('instagram', update, context):
        return None
    await asyncio.sleep(get_random_delay())
    try:
        cl = Client()
        cl.set_user_agent(get_random_user_agent())
        if PROXY:
            cl.set_proxy(PROXY)
        session_file = "instagram_session.json"
        if os.path.exists(session_file):
            cl.load_settings(session_file)
        cl.login(IG_USERNAME, IG_PASSWORD)
        cl.dump_settings(session_file)
        media_pk = cl.media_pk_from_url(url)
        media = cl.media_info(media_pk)
        logger.info(f"Отримано Instagram медіа: type={media.media_type}, resources_count={len(media.resources) if media.resources else 0}")
        return media
    except Exception as e:
        logger.error(f"Помилка instagrapi: {str(e)}")
        return None

async def get_instagram_stories(url, update, context):
    if not await check_request_limit('instagram', update, context):
        return None
    await asyncio.sleep(get_random_delay())
    try:
        cl = Client()
        cl.set_user_agent(get_random_user_agent())
        if PROXY:
            cl.set_proxy(PROXY)
        session_file = "instagram_session.json"
        if os.path.exists(session_file):
            cl.load_settings(session_file)
        cl.login(IG_USERNAME, IG_PASSWORD)
        cl.dump_settings(session_file)
        username = url.split("instagram.com/")[1].rstrip('/').split('/')[0]
        user_id = cl.user_id_from_username(username)
        stories = cl.user_stories(user_id)
        if not stories:
            logger.info(f"Stories для {username} відсутні або недоступні")
            return None
        logger.info(f"Отримано Instagram Stories: count={len(stories)}")
        return stories
    except Exception as e:
        logger.error(f"Помилка отримання Stories: {str(e)}")
        return None

async def get_tiktok_media(url, update, context):
    if not await check_request_limit('tiktok', update, context):
        return None
    await asyncio.sleep(get_random_delay())
    logger.info("Пропускаємо TikTokApi, використовуємо лише fallback")
    return await get_tiktok_media_fallback(url, update, context)

async def get_tiktok_media_fallback(url, update, context):
    if not await check_request_limit('tiktok', update, context):
        return None
    await asyncio.sleep(get_random_delay())
    try:
        headers = {
            'User-Agent': get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.tiktok.com/',
            'Connection': 'keep-alive',
            'Accept-Encoding': 'gzip, deflate',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'X-Tiktok-Region': 'US'  # Додаємо для обходу регіональних обмежень
        }
        if TIKTOK_TOKEN:
            headers['Cookie'] = f"msToken={TIKTOK_TOKEN}"
        async with aiohttp.ClientSession() as session:
            if PROXY:
                async with session.get(url, headers=headers, timeout=15, proxy=PROXY) as response:
                    content = await response.read()
                    response_text = await response.text()
            else:
                async with session.get(url, headers=headers, timeout=15) as response:
                    content = await response.read()
                    response_text = await response.text()
        with open("tiktok_response_raw.html", "wb") as f:
            f.write(content)
        logger.info(f"Збережено tiktok_response_raw.html: розмір={len(content)} байт")
        logger.info(f"Статус відповіді TikTok: {response.status}")
        logger.info(f"Заголовки відповіді TikTok: {dict(response.headers)}")
        with open("tiktok_response.html", "w", encoding="utf-8") as f:
            f.write(response_text)
        logger.info(f"Збережено tiktok_response.html: перші 1000 символів: {response_text[:1000]}")
        
        soup = BeautifulSoup(response_text, 'html.parser')
        
        # Пошук meta-тегів
        meta_tags = soup.find_all('meta')
        logger.info(f"Знайдено meta-тегів: {len(meta_tags)}")
        for tag in meta_tags:
            if tag.get('property') in ['og:video', 'og:image']:
                logger.info(f"Meta tag: {tag}")
        
        video_tag = soup.find('meta', {'property': 'og:video'})
        if video_tag and video_tag.get('content'):
            logger.info(f"Отримано TikTok відео через meta: url={video_tag['content']}")
            return {'type': 'video', 'url': video_tag['content']}
        
        image_tag = soup.find('meta', {'property': 'og:image'})
        if image_tag and image_tag.get('content'):
            logger.info(f"Отримано TikTok зображення через meta: url={image_tag['content']}")
            return {'type': 'image', 'urls': [image_tag['content']]}
        
        # Пошук у <video> тегах
        video_element = soup.find('video')
        if video_element and video_element.get('src'):
            logger.info(f"Отримано TikTok відео через <video> тег: url={video_element['src']}")
            return {'type': 'video', 'url': video_element['src']}
        
        # Пошук у скриптах
        script = soup.find('script', {'id': '__NEXT_DATA__'})
        if script and script.string:
            try:
                json_data = json.loads(script.string)
                logger.info(f"Знайдено __NEXT_DATA__: {json.dumps(json_data, indent=2)[:1000]}")
                video_url = json_data.get('props', {}).get('pageProps', {}).get('itemInfo', {}).get('itemStruct', {}).get('video', {}).get('playAddr')
                if video_url:
                    logger.info(f"Отримано TikTok відео через __NEXT_DATA__: url={video_url}")
                    return {'type': 'video', 'url': video_url}
                images = json_data.get('props', {}).get('pageProps', {}).get('itemInfo', {}).get('itemStruct', {}).get('imagePost', {}).get('images', [])
                if images:
                    image_urls = [img.get('displayImage') for img in images if img.get('displayImage')]
                    logger.info(f"Отримано TikTok зображення через __NEXT_DATA__: count={len(image_urls)}")
                    return {'type': 'image', 'urls': image_urls}
            except json.JSONDecodeError as e:
                logger.error(f"Помилка парсингу __NEXT_DATA__: {str(e)}")
        
        scripts = soup.find_all('script')
        logger.info(f"Знайдено скриптів: {len(scripts)}")
        for script in scripts:
            if script.string and 'itemInfo' in script.string:
                try:
                    json_data = json.loads(script.string)
                    logger.info(f"Знайдено itemInfo в скрипті: {json.dumps(json_data, indent=2)[:1000]}")
                    video_url = json_data.get('itemInfo', {}).get('itemStruct', {}).get('video', {}).get('playAddr')
                    if video_url:
                        logger.info(f"Отримано TikTok відео через скрипт: url={video_url}")
                        return {'type': 'video', 'url': video_url}
                    images = json_data.get('itemInfo', {}).get('itemStruct', {}).get('imagePost', {}).get('images', [])
                    if images:
                        image_urls = [img.get('displayImage') for img in images if img.get('displayImage')]
                        logger.info(f"Отримано TikTok зображення через скрипт: count={len(image_urls)}")
                        return {'type': 'image', 'urls': image_urls}
                except json.JSONDecodeError:
                    continue
        
        logger.info("TikTok медіа не знайдено через fallback")
        return None
    except Exception as e:
        logger.error(f"Помилка TikTok fallback: {str(e)}")
        return None

async def get_pinterest_media(url, update, context):
    if not await check_request_limit('pinterest', update, context):
        return None
    await asyncio.sleep(get_random_delay())
    try:
        headers = {'User-Agent': get_random_user_agent()}
        async with aiohttp.ClientSession() as session:
            if PROXY:
                async with session.get(url, headers=headers, timeout=10, proxy=PROXY) as response:
                    response_text = await response.text()
            else:
                async with session.get(url, headers=headers, timeout=10) as response:
                    response_text = await response.text()
        soup = BeautifulSoup(response_text, 'html.parser')
        media = []
        og_image = soup.find('meta', {'property': 'og:image'})
        og_video = soup.find('meta', {'property': 'og:video'})
        if og_image and og_image.get('content'):
            media.append({'type': 'photo', 'url': og_image['content']})
        if og_video and og_video.get('content'):
            media.append({'type': 'video', 'url': og_video['content']})
        image_tags = soup.find_all('img', {'src': True})
        for img in image_tags:
            src = img['src']
            if src and 'pinimg.com' in src and src not in [m['url'] for m in media]:
                media.append({'type': 'photo', 'url': src})
        if not media:
            logger.info("Pinterest медіа не знайдено")
            return None
        logger.info(f"Отримано Pinterest медіа: count={len(media)}")
        return media
    except Exception as e:
        logger.error(f"Помилка Pinterest: {str(e)}")
        return None

@retry(stop=stop_after_attempt(7), wait=wait_fixed(3), retry=retry_if_exception_type((aiohttp.ClientError, telegram.error.RetryAfter)))
async def send_media_group_with_retry(bot, chat_id, media):
    logger.info(f"Відправляємо альбом із {len(media)} фото")
    try:
        result = await bot.send_media_group(chat_id=chat_id, media=media)
        logger.info(f"Альбом із {len(media)} фото успішно відправлено")
        return result
    except telegram.error.RetryAfter as e:
        logger.warning(f"Flood control: Retry in {e.retry_after} seconds")
        await asyncio.sleep(e.retry_after)
        raise

@retry(stop=stop_after_attempt(5), wait=wait_fixed(3), retry=retry_if_exception_type(telegram.error.TimedOut))
async def delete_message_with_retry(bot, chat_id, message_id):
    logger.info(f"Видаляємо повідомлення: message_id={message_id}")
    return await bot.delete_message(chat_id=chat_id, message_id=message_id)

async def send_final_message_with_retry(bot, chat_id):
    logger.info("Відправляємо фінальне повідомлення 'Виконано за допомогою @InstaViewerBot'")
    try:
        await bot.send_message(chat_id=chat_id, text="Виконано за допомогою @InstaViewerBot")
    except telegram.error.RetryAfter as e:
        logger.warning(f"Flood control для фінального повідомлення: Retry in {e.retry_after} seconds")
        await asyncio.sleep(e.retry_after)
        await bot.send_message(chat_id=chat_id, text="Виконано за допомогою @InstaViewerBot")
    except telegram.error.TimedOut as timeout_error:
        logger.error(f"Тайм-аут при відправці повідомлення 'Виконано за допомогою @InstaViewerBot': {str(timeout_error)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Отримано повідомлення: {update.message.text}, chat_type={update.message.chat.type}")
    text = update.message.text
    if update.message.chat.type == "private":
        if text == "Надіслати посилання":
            await update.message.reply_text("Встав посилання на Instagram, TikTok або Pinterest-пост:")
        elif text == "Допомога":
            await help_command(update, context)
    
    if "instagram.com" in text or "tiktok.com" in text or "pinterest.com" in text:
        processing_msg = await update.message.reply_text("⏳ Обробляю твоє посилання...")
        carousel_msg = None
        beauty_msg = None
        try:
            if "instagram.com" in text:
                if "/p/" in text or "/reel/" in text:
                    media = await get_instagram_media(text, update, context)
                    if media:
                        save_stats(update.message.from_user.id, text)
                        if media.media_type == 1:
                            logger.info(f"Відправляємо Instagram фото: {media.thumbnail_url}")
                            await context.bot.send_photo(chat_id=update.message.chat_id, photo=str(media.thumbnail_url))
                        elif media.media_type == 2:
                            logger.info(f"Відправляємо Instagram відео: {media.video_url}")
                            await context.bot.send_video(chat_id=update.message.chat_id, video=str(media.video_url))
                        elif media.media_type == 8:
                            if media.resources:
                                photo_count = sum(1 for resource in media.resources if resource.media_type == 1)
                                carousel_msg = await update.message.reply_text(f"Ого, тут ціла галерея з {photo_count} шедеврів!")
                                photo_group = []
                                for i, resource in enumerate(media.resources, 1):
                                    logger.info(f"Обробка Instagram ресурсу {i}: type={resource.media_type}, url={resource.thumbnail_url or resource.video_url}")
                                    if resource.media_type == 1:
                                        photo_group.append(InputMediaPhoto(media=str(resource.thumbnail_url)))
                                    elif resource.media_type == 2:
                                        await context.bot.send_video(chat_id=update.message.chat_id, video=str(resource.video_url))
                                if photo_group:
                                    beauty_msg = await update.message.reply_text("Диви яка краса!..")
                                    if len(photo_group) <= 5:
                                        await asyncio.sleep(get_random_delay())
                                        try:
                                            await send_media_group_with_retry(context.bot, update.message.chat_id, photo_group)
                                        except telegram.error.TimedOut as timeout_error:
                                            logger.error(f"Тайм-аут при відправці альбому з {len(photo_group)} фото: {str(timeout_error)}")
                                            return
                                        except telegram.error.RetryAfter as retry_error:
                                            logger.warning(f"Flood control при відправці альбому з {len(photo_group)} фото: Retry in {retry_error.retry_after} seconds")
                                            await asyncio.sleep(retry_error.retry_after)
                                            await send_media_group_with_retry(context.bot, update.message.chat_id, photo_group)
                                    else:
                                        for i in range(0, len(photo_group), 3):
                                            chunk = photo_group[i:i+3]
                                            await asyncio.sleep(get_random_delay())
                                            try:
                                                await send_media_group_with_retry(context.bot, update.message.chat_id, chunk)
                                            except telegram.error.TimedOut as timeout_error:
                                                logger.error(f"Тайм-аут при відправці альбому з {len(chunk)} фото: {str(timeout_error)}")
                                                continue
                                            except telegram.error.RetryAfter as retry_error:
                                                logger.warning(f"Flood control при відправці альбому з {len(chunk)} фото: Retry in {retry_error.retry_after} seconds")
                                                await asyncio.sleep(retry_error.retry_after)
                                                await send_media_group_with_retry(context.bot, update.message.chat_id, chunk)
                                else:
                                    await update.message.reply_text("У каруселі немає фото, лише відео.")
                            else:
                                await update.message.reply_text("Не вдалося отримати медіа з каруселі.")
                        else:
                            await update.message.reply_text("Не вдалося визначити тип медіа.")
                    else:
                        await update.message.reply_text("Не вдалося отримати Instagram медіа. Перевір, чи пост публічний.")
                else:
                    stories = await get_instagram_stories(text, update, context)
                    if stories:
                        save_stats(update.message.from_user.id, text)
                        carousel_msg = await update.message.reply_text(f"Ого, знайшов {len(stories)} Stories!")
                        photo_group = []
                        for i, story in enumerate(stories, 1):
                            logger.info(f"Обробка Story {i}: type={story.media_type}, url={story.thumbnail_url or story.video_url}")
                            if story.media_type == 1:
                                photo_group.append(InputMediaPhoto(media=str(story.thumbnail_url)))
                            elif story.media_type == 2:
                                await context.bot.send_video(chat_id=update.message.chat_id, video=str(story.video_url))
                        if photo_group:
                            beauty_msg = await update.message.reply_text("Диви яка краса!..")
                            for i in range(0, len(photo_group), 3):
                                chunk = photo_group[i:i+3]
                                await asyncio.sleep(get_random_delay())
                                try:
                                    await send_media_group_with_retry(context.bot, update.message.chat_id, chunk)
                                except telegram.error.TimedOut as timeout_error:
                                    logger.error(f"Тайм-аут при відправці альбому з {len(chunk)} фото: {str(timeout_error)}")
                                    continue
                                except telegram.error.RetryAfter as retry_error:
                                    logger.warning(f"Flood control при відправці альбому з {len(chunk)} фото: Retry in {retry_error.retry_after} seconds")
                                    await asyncio.sleep(retry_error.retry_after)
                                    await send_media_group_with_retry(context.bot, update.message.chat_id, chunk)
                        else:
                            await update.message.reply_text("У Stories немає фото, лише відео.")
                    else:
                        await update.message.reply_text("Не вдалося отримати Stories. Перевір, чи профіль публічний або чи акаунт підписаний.")
            
            elif "tiktok.com" in text:
                media = await get_tiktok_media(text, update, context)
                if media and media.get('type'):
                    save_stats(update.message.from_user.id, text)
                    if media['type'] == 'video':
                        video_url = media.get('url', '')
                        if video_url:
                            logger.info(f"Відправляємо TikTok відео: {video_url}")
                            beauty_msg = await update.message.reply_text("Диви яка краса!..")
                            await context.bot.send_video(chat_id=update.message.chat_id, video=video_url)
                        else:
                            await update.message.reply_text("Не вдалося отримати TikTok відео.")
                    elif media['type'] == 'image':
                        images = media.get('urls', [])
                        if images:
                            carousel_msg = await update.message.reply_text(f"Ого, тут ціла галерея з {len(images)} шедеврів!")
                            beauty_msg = await update.message.reply_text("Диви яка краса!..")
                            photo_group = [InputMediaPhoto(media=img) for img in images if img]
                            if photo_group:
                                for i in range(0, len(photo_group), 3):
                                    chunk = photo_group[i:i+3]
                                    await asyncio.sleep(get_random_delay())
                                    try:
                                        await send_media_group_with_retry(context.bot, update.message.chat_id, chunk)
                                    except telegram.error.TimedOut as timeout_error:
                                        logger.error(f"Тайм-аут при відправці альбому з {len(chunk)} фото: {str(timeout_error)}")
                                        continue
                                    except telegram.error.RetryAfter as retry_error:
                                        logger.warning(f"Flood control при відправці альбому з {len(chunk)} фото: Retry in {retry_error.retry_after} seconds")
                                        await asyncio.sleep(retry_error.retry_after)
                                        await send_media_group_with_retry(context.bot, update.message.chat_id, chunk)
                            else:
                                await update.message.reply_text("У TikTok-пості немає доступних зображень.")
                        else:
                            await update.message.reply_text("Не вдалося отримати TikTok зображення.")
                    else:
                        await update.message.reply_text("Невідомий тип TikTok контенту.")
                else:
                    await update.message.reply_text("Не вдалося отримати TikTok медіа. Перевір, чи пост публічний.")
            
            elif "pinterest.com" in text:
                media = await get_pinterest_media(text, update, context)
                if media:
                    save_stats(update.message.from_user.id, text)
                    photo_group = []
                    for i, item in enumerate(media, 1):
                        logger.info(f"Обробка Pinterest ресурсу {i}: type={item['type']}, url={item['url']}")
                        if item['type'] == 'photo':
                            photo_group.append(InputMediaPhoto(media=item['url']))
                        elif item['type'] == 'video':
                            await context.bot.send_video(chat_id=update.message.chat_id, video=item['url'])
                    if photo_group:
                        carousel_msg = await update.message.reply_text(f"Ого, тут ціла галерея з {len(photo_group)} шедеврів!")
                        beauty_msg = await update.message.reply_text("Диви яка краса!..")
                        for i in range(0, len(photo_group), 3):
                            chunk = photo_group[i:i+3]
                            await asyncio.sleep(get_random_delay())
                            try:
                                await send_media_group_with_retry(context.bot, update.message.chat_id, chunk)
                            except telegram.error.TimedOut as timeout_error:
                                logger.error(f"Тайм-аут при відправці альбому з {len(chunk)} фото: {str(timeout_error)}")
                                continue
                            except telegram.error.RetryAfter as retry_error:
                                logger.warning(f"Flood control при відправці альбому з {len(chunk)} фото: Retry in {retry_error.retry_after} seconds")
                                await asyncio.sleep(retry_error.retry_after)
                                await send_media_group_with_retry(context.bot, update.message.chat_id, chunk)
                    else:
                        await update.message.reply_text("У Pinterest-пості немає фото, лише відео.")
                else:
                    await update.message.reply_text("Не вдалося отримати Pinterest медіа. Перевір, чи пост публічний.")
        except aiohttp.ClientError as timeout_error:
            logger.error(f"Ігноруємо тайм-аут: {str(timeout_error)}")
            raise
        except telegram.error.TimedOut as timeout_error:
            logger.error(f"Тайм-аут Telegram API: {str(timeout_error)}")
            raise
        except telegram.error.RetryAfter as retry_error:
            logger.warning(f"Flood control у handle_message: Retry in {retry_error.retry_after} seconds")
            await asyncio.sleep(retry_error.retry_after)
        except Exception as e:
            logger.error(f"Помилка обробки: {str(e)}")
            try:
                await update.message.reply_text(f"Помилка: {str(e)}")
            except telegram.error.RetryAfter as retry_error:
                logger.warning(f"Flood control при відправці повідомлення про помилку: Retry in {retry_error.retry_after} seconds")
                await asyncio.sleep(retry_error.retry_after)
                await update.message.reply_text(f"Помилка: {str(e)}")
            raise
        finally:
            await asyncio.sleep(get_random_delay())
            try:
                logger.info(f"Спроба видалити processing_msg: message_id={processing_msg.message_id}")
                await delete_message_with_retry(context.bot, update.message.chat_id, processing_msg.message_id)
                if carousel_msg:
                    logger.info(f"Спроба видалити carousel_msg: message_id={carousel_msg.message_id}")
                    await delete_message_with_retry(context.bot, update.message.chat_id, carousel_msg.message_id)
                if beauty_msg:
                    logger.info(f"Спроба видалити beauty_msg: message_id={beauty_msg.message_id}")
                    await delete_message_with_retry(context.bot, update.message.chat_id, beauty_msg.message_id)
            except Exception as delete_error:
                logger.error(f"Помилка видалення повідомлень: {str(delete_error)}")
        
        if "instagram.com" in text or "tiktok.com" in text or "pinterest.com" in text:
            await send_final_message_with_retry(context.bot, update.message.chat_id)

def main():
    if not TOKEN:
        logger.error("BOT_TOKEN не встановлено. Додайте токен до змінної середовища.")
        raise ValueError("BOT_TOKEN не встановлено. Отримайте токен від @BotFather і додайте до ~/.bashrc.")
    try:
        application = Application.builder().token(TOKEN).get_updates_pool_timeout(60).get_updates_connect_timeout(60).get_updates_read_timeout(60).get_updates_write_timeout(60).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("about", about))
        application.add_handler(CommandHandler("stats", stats))
        application.add_handler(CommandHandler("feedback", feedback))
        application.add_handler(CommandHandler("donate", donate))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Критична помилка в main: {str(e)}")
        raise

if __name__ == "__main__":
    main()