import logging
from instagram_downloader import get_instagram_client, download_instagram

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG, filename='InstaVieverBot/tiktok_bot.log')
logger = logging.getLogger(__name__)

try:
    logger.info("Testing Instagram login...")
    client = get_instagram_client()
    logger.info("Instagram client initialized successfully!")
    url = "https://www.instagram.com/p/DMx0SNuRcIS/"
    logger.info(f"Testing download for {url}...")
    media = download_instagram(url)
    logger.info(f"Media downloaded: {media}")
except Exception as e:
    logger.error(f"Error: {str(e)}", exc_info=True)