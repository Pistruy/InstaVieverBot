import telegram
from telegram import InputMediaPhoto, InputMediaVideo, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging
import asyncio
import os
import signal
import sys
from collections import deque
import random
import time
import json
from instagram_downloader import download_instagram, download_instagram_stories
from tiktok_downloader import download_tiktok
from pinterest_downloader import download_pinterest
from file_manager import cleanup_temp_files
from error_handler import handle_error
from utils import get_random_user_agent, get_random_delay

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('InstaVieverBot/tiktok_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('BOT_TOKEN')
REQUEST_LIMITS = {
    'instagram': {'limit': 50, 'reset_interval': 3600},
    'tiktok': {'limit': 500, 'reset_interval': 86400},
    'pinterest': {'limit': 500, 'reset_interval': 86400}
}
REQUEST_COUNTS_FILE = "InstaVieverBot/request_counts.json"
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

def save_stats(user_id, link):
    try:
        with open("InstaVieverBot/stats.json", "r") as f:
            stats = json.load(f)
    except:
        stats = {}
    stats[str(user_id)] = stats.get(str(user_id), 0) + 1
    with open("InstaVieverBot/stats.json", "w") as f:
        json.dump(stats, f)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌟 Привіт! Я @InstaViewerBot. Надішли посилання на Instagram, TikTok або Pinterest-пост, і я покажу всі фото чи відео! 📸"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Як користуватися ботом:*\n"
        "1. Надішли посилання на Instagram-пост, профіль для Stories, TikTok-відео або Pinterest-пост.\n"
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
        with open("InstaVieverBot/stats.json", "r") as f:
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

async def send_media_group_in_batches(context, chat_id, media_group):
    """Надсилає медіа-групи партіями по 10 елементів."""
    batch_size = 10
    for i in range(0, len(media_group), batch_size):
        batch = media_group[i:i + batch_size]
        try:
            await context.bot.send_media_group(chat_id=chat_id, media=batch)
            await asyncio.sleep(get_random_delay())
        except Exception as e:
            logger.error(f"Помилка надсилання медіа-групи: {str(e)}")
            raise

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Отримано повідомлення: {update.message.text}, chat_type={update.message.chat.type}")
    text = update.message.text
    processing_msg = await update.message.reply_text("⏳ Обробляю твоє посилання...")
    carousel_msg = None
    beauty_msg = None
   
    try:
        if "instagram.com" in text:
            if not await check_request_limit('instagram', update, context):
                return
            save_stats(update.message.from_user.id, text)
            if "/p/" in text or "/reel/" in text:
                media = await download_instagram(text)
                if media:
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
                                await send_media_group_in_batches(context, update.message.chat_id, photo_group)
                    else:
                        await update.message.reply_text("Не вдалося визначити тип медіа.")
                else:
                    await update.message.reply_text("Не вдалося отримати Instagram медіа. Перевір, чи пост публічний.")
            else:
                stories = await download_instagram_stories(text)
                if stories:
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
                        await send_media_group_in_batches(context, update.message.chat_id, photo_group)
                else:
                    await update.message.reply_text("Не вдалося отримати Stories. Перевір, чи профіль публічний.")
       
        elif "tiktok.com" in text:
            if not await check_request_limit('tiktok', update, context):
                return
            save_stats(update.message.from_user.id, text)
            media = await download_tiktok(text)
            if media and media.get('type'):
                if media['type'] == 'video':
                    video_path = media.get('url', '')
                    if video_path and os.path.exists(video_path):
                        logger.info(f"Відправляємо TikTok відео: {video_path}")
                        beauty_msg = await update.message.reply_text("Диви яка краса!..")
                        with open(video_path, 'rb') as video_file:
                            await context.bot.send_video(chat_id=update.message.chat_id, video=video_file)
                        os.remove(video_path)
                    else:
                        await update.message.reply_text("Не вдалося отримати TikTok відео.")
                elif media['type'] == 'image':
                    images = media.get('urls', [])
                    if images:
                        carousel_msg = await update.message.reply_text(f"Ого, тут ціла галерея з {len(images)} шедеврів!")
                        beauty_msg = await update.message.reply_text("Диви яка краса!..")
                        photo_group = [InputMediaPhoto(media=img) for img in images if img]
                        await send_media_group_in_batches(context, update.message.chat_id, photo_group)
                else:
                    await update.message.reply_text("Невідомий тип TikTok контенту.")
            else:
                await update.message.reply_text("Не вдалося отримати TikTok медіа. Перевір, чи пост публічний.")
       
        elif "pinterest.com" in text or "pin.it" in text:
            if not await check_request_limit('pinterest', update, context):
                return
            save_stats(update.message.from_user.id, text)
            media = await download_pinterest(text)
            if media:
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
                    await send_media_group_in_batches(context, update.message.chat_id, photo_group)
                else:
                    await update.message.reply_text("У Pinterest-пості немає фото, лише відео.")
            else:
                await update.message.reply_text("Не вдалося отримати Pinterest медіа. Перевір, чи пост публічний.")
   
    except Exception as e:
        error_msg = handle_error(e)
        logger.error(f"Помилка обробки: {str(e)}", exc_info=True)
        await context.bot.send_message(chat_id="YOUR_ADMIN_TELEGRAM_ID", text=f"Помилка бота: {str(e)}")
        await update.message.reply_text(error_msg)
   
    finally:
        await asyncio.sleep(get_random_delay())
        try:
            if processing_msg:
                await context.bot.delete_message(chat_id=update.message.chat_id, message_id=processing_msg.message_id)
            if carousel_msg:
                await context.bot.delete_message(chat_id=update.message.chat_id, message_id=carousel_msg.message_id)
            if beauty_msg:
                await context.bot.delete_message(chat_id=update.message.chat_id, message_id=beauty_msg.message_id)
        except Exception as delete_error:
            logger.error(f"Помилка видалення повідомлень: {str(delete_error)}")
        cleanup_temp_files()
        await context.bot.send_message(chat_id=update.message.chat_id, text="Виконано за допомогою @InstaViewerBot")

def signal_handler(sig, frame):
    logger.info("Отримано Ctrl+C, завершуємо роботу...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def main():
    logger.info("Executing main()...")
    if not TOKEN:
        logger.error("BOT_TOKEN не встановлено")
        raise ValueError("BOT_TOKEN не встановлено")
   
    logger.info("Building Application...")
    application = Application.builder().token(TOKEN).build()
    logger.info("Application built successfully!")
   
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("feedback", feedback))
    application.add_handler(CommandHandler("donate", donate))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
   
    logger.info("Handlers added, starting polling...")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Помилка під час роботи бота: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
