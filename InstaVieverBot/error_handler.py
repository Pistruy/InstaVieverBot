import logging

logger = logging.getLogger(__name__)

def handle_error(error: Exception) -> str:
    """Перетворює помилки в зрозумілі повідомлення."""
    error_str = str(error)
    if "private" in error_str.lower():
        return "Це відео/пост приватне або обмежене."
    elif "blocked" in error_str.lower():
        return "Ваш IP-адресу заблоковано для цього контенту."
    elif "captcha" in error_str.lower():
        return "Виявлено CAPTCHA. Оновіть cookies після ручної авторизації."
    elif "timeout" in error_str.lower():
        return "Таймаут при завантаженні контенту."
    elif "not found" in error_str.lower() or "unavailable" in error_str.lower():
        return "Контент не знайдено або недоступний."
    else:
        logger.error(f"Невідома помилка: {error_str}", exc_info=True)
        return f"Помилка: {error_str}"
