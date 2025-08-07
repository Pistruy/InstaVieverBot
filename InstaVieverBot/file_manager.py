import os
import logging

logger = logging.getLogger(__name__)

def cleanup_temp_files():
    """Очищає тимчасові файли в папці InstaVieverBot/temp/."""
    temp_dir = 'InstaVieverBot/temp/'
    try:
        for file in os.listdir(temp_dir):
            if file.startswith('temp_video_') or file.startswith('temp_instagram_') or file.startswith('temp_pinterest_'):
                file_path = os.path.join(temp_dir, file)
                os.remove(file_path)
                logger.info(f"Видалено тимчасовий файл: {file_path}")
    except Exception as e:
        logger.error(f"Помилка очищення тимчасових файлів: {e}")
