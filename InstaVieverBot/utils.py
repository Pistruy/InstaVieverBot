import random
from collections import deque

# Список User-Agent для ротації
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
]

# Зберігання останніх затримок
DELAY_HISTORY = deque(maxlen=3)

def get_random_delay():
    """Повертає випадкову затримку, уникаючи повторень."""
    while True:
        delay = random.uniform(1, 6)
        rounded_delay = round(delay, 2)
        if rounded_delay not in DELAY_HISTORY:
            DELAY_HISTORY.append(rounded_delay)
            return rounded_delay

def get_random_user_agent():
    """Повертає випадковий User-Agent."""
    return random.choice(USER_AGENTS)
