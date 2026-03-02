import os

API_ID = int(os.environ.get('API_ID', 0))
API_HASH = os.environ.get('API_HASH', '')
BOT_B_TOKEN = os.environ.get('BOT_B_TOKEN', '')
BOT_A_CHAT_ID = int(os.environ.get('BOT_A_CHAT_ID', 7240340418))

# PAKAI SESSION PYROGRAM ANDA
SESSION_STRING = os.environ.get('SESSION_STRING', '')

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
ADMIN_CHAT_ID = int(os.environ.get('ADMIN_CHAT_ID', 0))
TESSERACT_PATH = '/usr/bin/tesseract'
