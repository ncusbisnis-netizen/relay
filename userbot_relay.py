from pyrogram import Client, filters
from pyrogram.types import Message
import asyncio
import logging
import os
import cv2
import numpy as np
from PIL import Image
import pytesseract
import redis
import json
import time
import requests
import re
from config import *

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Setup Redis
redis_client = redis.from_url(REDIS_URL)

# Inisialisasi Pyrogram Client dengan session string
app = Client(
    "bengkel_relay",
    session_string=SESSION_STRING,  # PAKAI SESSION ANDA
    api_id=API_ID,
    api_hash=API_HASH
)

BOT_A_ID = BOT_A_CHAT_ID
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

bot_status = {
    'in_captcha': False,
    'last_captcha_time': 0
}

def notify_admin(message):
    if ADMIN_CHAT_ID:
        url = f"https://api.telegram.org/bot{BOT_B_TOKEN}/sendMessage"
        data = {
            'chat_id': ADMIN_CHAT_ID,
            'text': f"🤖 Relay Bot:\n{message}"
        }
        try:
            requests.post(url, json=data, timeout=5)
        except:
            pass

async def solve_captcha(photo_message: Message):
    """Solve captcha 6-digit dengan OCR"""
    try:
        # Download foto
        photo_path = await photo_message.download()
        
        # Baca dengan OpenCV
        img = cv2.imread(photo_path)
        
        # Preprocessing
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        
        kernel = np.ones((2,2), np.uint8)
        dilated = cv2.dilate(thresh, kernel, iterations=1)
        
        # OCR
        custom_config = r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789'
        text = pytesseract.image_to_string(dilated, config=custom_config)
        
        # Hapus file
        os.remove(photo_path)
        
        # Ambil 6 digit
        digits = re.findall(r'\d{6}', text)
        
        if digits:
            code = digits[0]
            logger.info(f"✅ OCR: {code}")
            return code
        else:
            logger.warning(f"❌ OCR gagal: {text}")
            return None
            
    except Exception as e:
        logger.error(f"Error OCR: {e}")
        return None

@app.on_message(filters.chat(BOT_A_ID))
async def handle_bot_reply(client, message: Message):
    """Handle balasan dari Bot A"""
    text = message.text or message.caption or ''
    
    # CEK CAPTCHA
    if message.photo and ('captcha' in text.lower() or 'verify' in text.lower()):
        logger.warning("🚫 CAPTCHA DETECTED!")
        
        bot_status['in_captcha'] = True
        bot_status['last_captcha_time'] = time.time()
        
        notify_admin("Captcha detected, solving...")
        
        code = await solve_captcha(message)
        
        if code:
            await client.send_message(BOT_A_ID, f"/verify {code}")
            logger.info(f"✅ Verifikasi: /verify {code}")
            
            await asyncio.sleep(3)
            bot_status['in_captcha'] = False
            notify_admin("Captcha solved!")
            
            await retry_pending_requests(client)
        else:
            logger.error("❌ Gagal solve captcha")
            notify_admin("OCR failed, waiting 5 min...")
            await asyncio.sleep(300)
            bot_status['in_captcha'] = False
        
        return
    
    # RESPON NORMAL (HASIL INFO)
    if not bot_status['in_captcha'] and not message.photo:
        request_id = redis_client.lpop('pending_requests')
        if request_id:
            request_id = request_id.decode('utf-8')
            request_data = json.loads(redis_client.get(request_id))
            
            url = f"https://api.telegram.org/bot{BOT_B_TOKEN}/sendMessage"
            data = {
                'chat_id': request_data['chat_id'],
                'text': text,
                'parse_mode': 'HTML'
            }
            
            try:
                requests.post(url, json=data)
                logger.info(f"✅ Response ke user {request_data['chat_id']}")
            except Exception as e:
                logger.error(f"Gagal forward: {e}")
                redis_client.rpush('pending_requests', request_id)

async def retry_pending_requests(client):
    """Kirim ulang request yang pending"""
    while True:
        request_id = redis_client.lpop('pending_requests')
        if not request_id:
            break
            
        request_id = request_id.decode('utf-8')
        request_data = json.loads(redis_client.get(request_id))
        
        cmd = f"{request_data['command']} {' '.join(request_data['args'])}"
        await client.send_message(BOT_A_ID, cmd)
        logger.info(f"🔄 Retry: {cmd}")
        await asyncio.sleep(2)

async def process_queue(client):
    """Monitor queue"""
    while True:
        if bot_status['in_captcha']:
            await asyncio.sleep(5)
            continue
        
        request_id = redis_client.lpop('pending_requests')
        if request_id:
            request_id = request_id.decode('utf-8')
            request_data = json.loads(redis_client.get(request_id))
            
            cmd = f"{request_data['command']} {' '.join(request_data['args'])}"
            await client.send_message(BOT_A_ID, cmd)
            logger.info(f"📤 Request: {cmd}")
            
            redis_client.setex(request_id, 300, json.dumps(request_data))
        
        await asyncio.sleep(3)

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    """Handler untuk /start"""
    await message.reply("✅ Userbot aktif!")

async def main():
    """Main function"""
    logger.info("🚀 Userbot starting...")
    
    # Kirim /start ke Bot A
    try:
        await app.send_message(BOT_A_ID, "/start")
        logger.info("✅ Session dengan Bot A aktif")
    except Exception as e:
        logger.warning(f"⚠️ Gagal kirim /start: {e}")
    
    # Jalankan queue processor
    await process_queue(app)

if __name__ == "__main__":
    app.run(main())
