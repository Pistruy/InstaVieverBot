import logging
import aiohttp
from bs4 import BeautifulSoup
from utils import get_random_user_agent, get_random_delay

logger = logging.getLogger(__name__)

async def download_pinterest(url: str) -> list:
    """Завантажує медіа з Pinterest."""
    await asyncio.sleep(get_random_delay())
    try:
        headers = {'User-Agent': get_random_user_agent()}
        async with aiohttp.ClientSession() as session:
            proxy = os.getenv('PROXY')
            if proxy:
                async with session.get(url, headers=headers, timeout=10, proxy=proxy) as response:
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
