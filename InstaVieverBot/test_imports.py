print("Testing imports...")
import os
print("os imported")
import logging
print("logging imported")
import json
print("json imported")
import time
print("time imported")
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto, InputMediaVideo
print("telegram imported")
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
print("telegram.ext imported")
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
print("tenacity imported")
from tiktok_downloader import download_tiktok
print("tiktok_downloader imported")
from instagram_downloader import download_instagram, download_instagram_stories
print("instagram_downloader imported")
from pinterest_downloader import download_pinterest
print("pinterest_downloader imported")
from error_handler import handle_error
print("error_handler imported")
from utils import get_random_user_agent, get_random_delay
print("utils imported")
import telegram.error
print("telegram.error imported")
print("All imports successful!")
