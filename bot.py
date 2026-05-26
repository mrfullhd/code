import os
import re
import json
import time
import logging
import asyncio
from datetime import date
from pathlib import Path
from typing import Optional, Dict, Tuple, Any
import aiohttp
import requests

# --- تنظیمات اولیه ---
BOT_TOKEN = "651070801:WKnxIXJk4Q4frV0SQCqWRqSEPkKBsq2ChQM"
CHANNEL_ID = "@ABSChanel"
CHANNEL_LINK = "https://ble.ir/ABSChanel"
MAX_SIZE_MB = 19
MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
DAILY_LIMIT = 3

BALE_API = "https://tapi.bale.ai"
BALE_FILE = "https://tapi.bale.ai/file"

# --- راه‌اندازی logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ذخیره‌سازی ---
user_downloads = {}
user_active_tasks = {}
pending_downloads = {}
membership_cache = {}

# =================== کلاس اصلی ربات ===================
class DownloadBot:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"{BALE_API}/bot{token}"
        self.file_url = f"{BALE_FILE}/bot{token}"
        self.session = None
        self.download_dir = Path(__file__).parent / "download"
        self.download_dir.mkdir(exist_ok=True)
        
        self.valid_extensions = ['mp4', 'mp3', 'zip', 'rar', '7z', 'pdf', 'jpg', 'jpeg', 'png', 'gif', 
                                 'mkv', 'avi', 'mov', 'm4a', 'flac', 'wav', 'doc', 'docx', 'xls', 
                                 'xlsx', 'ppt', 'pptx', 'txt', 'apk', 'exe', 'iso', 'bin']
    
    async def init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3600))
    
    async def close(self):
        if self.session:
            await self.session.close()
    
    # ========== توابع API بله ==========
    async def api_call(self, method: str, payload: Dict) -> Dict:
        url = f"{self.base_url}/{method}"
        try:
            async with self.session.post(url, json=payload) as resp:
                return await resp.json()
        except Exception as e:
            logger.error(f"API error: {e}")
            return {'ok': False}
    
    async def send_message(self, chat_id: int, text: str, reply_markup: Dict = None, parse_mode: str = "Markdown"):
        payload = {
            'chat_id': chat_id, 
            'text': text[:4096],
            'parse_mode': parse_mode
        }
        if reply_markup:
            payload['reply_markup'] = json.dumps(reply_markup)
        return await self.api_call('sendMessage', payload)
    
    async def edit_message(self, chat_id: int, message_id: int, text: str, reply_markup: Dict = None, parse_mode: str = "Markdown"):
        payload = {
            'chat_id': chat_id, 
            'message_id': message_id, 
            'text': text[:4096],
            'parse_mode': parse_mode
        }
        if reply_markup:
            payload['reply_markup'] = json.dumps(reply_markup)
        return await self.api_call('editMessageText', payload)
    
    async def delete_message(self, chat_id: int, message_id: int):
        payload = {'chat_id': chat_id, 'message_id': message_id}
        return await self.api_call('deleteMessage', payload)
    
    async def answer_callback(self, callback_id: str, text: str = None, show_alert: bool = False):
        payload = {'callback_query_id': callback_id}
        if text:
            payload['text'] = text
        if show_alert:
            payload['show_alert'] = True
        return await self.api_call('answerCallbackQuery', payload)
    
    # ========== منوی اصلی ربات (فقط برای اعضا) ==========
    def get_main_menu(self) -> Dict:
        """منوی اصلی ربات - فقط برای کاربران عضو"""
        return {
            'inline_keyboard': [
                [
                    {'text': '📥 ارسال لینک دانلود', 'callback_data': 'send_link'},
                    {'text': '📊 آمار امروز', 'callback_data': 'stats'}
                ],
                [
                    {'text': '📖 راهنما', 'callback_data': 'help'},
                    {'text': 'ℹ️ درباره ربات', 'callback_data': 'about'}
                ]
            ],
            'resize_keyboard': True
        }
    
    def get_check_membership_button(self) -> Dict:
        """دکمه بررسی عضویت (فقط برای کاربران غیرعضو)"""
        return {
            'inline_keyboard': [
                [
                    {'text': '✅ بررسی عضویت', 'callback_data': 'check_member'}
                ],
                [
                    {'text': '🔗 عضویت در کانال', 'url': CHANNEL_LINK}
                ]
            ]
        }
    
    def get_confirm_keyboard(self, user_id: int) -> Dict:
        """دکمه تأیید دانلود"""
        return {
            'inline_keyboard': [
                [
                    {'text': '✅ بله، شروع دانلود', 'callback_data': f'confirm_{user_id}'},
                    {'text': '❌ انصراف', 'callback_data': f'cancel_{user_id}'}
                ]
            ]
        }
    
    # ========== بررسی عضویت با کش ==========
    async def check_membership(self, user_id: int) -> bool:
        """بررسی عضویت کاربر در کانال (با کش 5 دقیقه)"""
        global membership_cache
        now = time.time()
        
        # چک کش
        if user_id in membership_cache:
            cached_time, is_member = membership_cache[user_id]
            if now - cached_time < 300:  # 5 دقیقه
                return is_member
        
        # بررسی واقعی
        try:
            payload = {
                'chat_id': CHANNEL_ID,
                'user_id': user_id
            }
            
            result = await self.api_call('getChatMember', payload)
            
            if result.get('ok'):
                result_data = result.get('result', {})
                status = result_data.get('status')
                
                is_member = status in ['member', 'administrator', 'creator']
                
                # ذخیره در کش
                membership_cache[user_id] = (now, is_member)
                
                return is_member
            else:
                return False
                
        except Exception as e:
            logger.error(f"Membership check error: {e}")
            return False
    
    # ========== حذف کش عضویت ==========
    def clear_membership_cache(self, user_id: int):
        """پاک کردن کش عضویت کاربر"""
        global membership_cache
        if user_id in membership_cache:
            del membership_cache[user_id]
    
    # ========== توابع دانلود و آپلود ==========
    async def upload_file_from_path(self, chat_id: int, filepath: Path) -> Dict:
        """آپلود فایل از مسیر موجود"""
        url = f"{self.base_url}/sendDocument"
        
        loop = asyncio.get_event_loop()
        
        def upload_sync():
            with open(filepath, 'rb') as f:
                files = {'document': (filepath.name, f, 'application/octet-stream')}
                data = {'chat_id': str(chat_id)}
                response = requests.post(url, data=data, files=files, timeout=120)
                return response.json()
        
        return await loop.run_in_executor(None, upload_sync)
    
    async def get_file_info(self, url: str) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, timeout=30) as resp:
                    if resp.status != 200:
                        return None, None, f"❌ خطا! وضعیت: {resp.status}"
                    
                    content_length = resp.headers.get('content-length')
                    file_size = int(content_length) if content_length else 0
                    
                    filename = url.split('/')[-1].split('?')[0]
                    if not filename:
                        filename = "file"
                    
                    return filename, file_size, None
                    
        except asyncio.TimeoutError:
            return None, None, "❌ زمان اتصال به سرور تمام شد!"
        except Exception as e:
            return None, None, f"❌ خطا: {str(e)}"
    
    async def download_file(self, url: str, user_id: int, on_progress=None) -> Tuple[Optional[Path], Optional[str]]:
        """دانلود فایل"""
        temp_path = None
        
        try:
            original_name = url.split('/')[-1].split('?')[0]
            if not original_name:
                original_name = "downloaded_file"
            
            original_name = re.sub(r'[<>:"/\\|?*]', '_', original_name)
            if len(original_name) > 50:
                name, ext = os.path.splitext(original_name)
                original_name = name[:45] + ext
            
            temp_filename = f"downloading_{user_id}_{int(time.time())}.tmp"
            temp_path = self.download_dir / temp_filename
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=120) as resp:
                    if resp.status != 200:
                        return None, f"❌ خطا در دانلود! وضعیت: {resp.status}"
                    
                    total_size = int(resp.headers.get('content-length', 0))
                    downloaded = 0
                    last_percent = 0
                    
                    with open(temp_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if downloaded > MAX_SIZE_BYTES:
                                temp_path.unlink()
                                return None, f"❌ حجم فایل از حد مجاز {MAX_SIZE_MB} مگابایت بیشتر شد!"
                            
                            if total_size > 0 and on_progress:
                                percent = int((downloaded / total_size) * 100)
                                if percent >= last_percent + 5:
                                    last_percent = percent
                                    await on_progress(percent)
                    
                    file_size = temp_path.stat().st_size
                    if file_size > MAX_SIZE_BYTES:
                        temp_path.unlink()
                        return None, f"❌ حجم فایل بیشتر از حد مجاز {MAX_SIZE_MB} مگابایت است!"
                    
                    final_path = self.download_dir / original_name
                    counter = 1
                    while final_path.exists():
                        name, ext = os.path.splitext(original_name)
                        final_path = self.download_dir / f"{name}_{counter}{ext}"
                        counter += 1
                    
                    temp_path.rename(final_path)
                    temp_path = None
                    
                    return final_path, None
                    
        except asyncio.TimeoutError:
            if temp_path and temp_path.exists():
                temp_path.unlink()
            return None, "❌ زمان اتمام دانلود تمام شد!"
        except Exception as e:
            if temp_path and temp_path.exists():
                temp_path.unlink()
            return None, f"❌ خطا در دانلود: {str(e)}"
    
    async def process_download(self, chat_id: int, user_id: int, url: str, status_msg_id: int):
        """پردازش دانلود و آپلود"""
        filepath = None
        
        try:
            async def update_progress(percent):
                bar_length = 20
                filled = int(bar_length * percent / 100)
                bar = "█" * filled + "░" * (bar_length - filled)
                await self.edit_message(chat_id, status_msg_id, 
                                      f"📥 **دانلود فایل...**\n\n`{bar}` {percent}%\n\n⏱ لطفاً صبر کنید...")
            
            await self.edit_message(chat_id, status_msg_id, "📥 **شروع دانلود...**\n\n⏱ در حال اتصال به سرور...")
            filepath, error = await self.download_file(url, user_id, update_progress)
            
            if error:
                await self.edit_message(chat_id, status_msg_id, f"{error}\n\n🔙 لطفاً دوباره تلاش کنید.")
                return
            
            file_size_mb = filepath.stat().st_size / (1024 * 1024)
            
            await self.edit_message(chat_id, status_msg_id, f"📤 **در حال آپلود...**\n\n📁 حجم: {file_size_mb:.2f} مگابایت\n\n⏱ در حال ارسال فایل...")
            
            result = await self.upload_file_from_path(chat_id, filepath)
            
            if result.get('ok'):
                self.increment_user_downloads(user_id)
                remaining = DAILY_LIMIT - self.get_user_today_downloads(user_id)
                
                result_text = (
                    f"✅ **فایل با موفقیت ارسال شد!**\n\n"
                    f"📁 **نام:** `{filepath.name[:40]}`\n"
                    f"💾 **حجم:** {file_size_mb:.2f} مگابایت\n"
                    f"📊 **دانلود امروز:** {self.get_user_today_downloads(user_id)} از {DAILY_LIMIT}\n"
                    f"⚡️ **باقی‌مانده:** {remaining}\n\n"
                    f"🎯 **برای دانلود مجدد، لینک جدید بفرستید**"
                )
                await self.edit_message(chat_id, status_msg_id, result_text)
            else:
                error_msg = result.get('description', 'ناشناخته')
                await self.edit_message(chat_id, status_msg_id, f"❌ **خطا در آپلود:** {error_msg}")
                
        except Exception as e:
            await self.edit_message(chat_id, status_msg_id, f"❌ **خطا:** {str(e)}")
        finally:
            if filepath and filepath.exists():
                try:
                    filepath.unlink()
                except Exception as e:
                    logger.error(f"Error deleting file: {e}")
            self.remove_active_task(user_id)
    
    # ========== توابع کمکی ==========
    
    def format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    
    def get_user_today_downloads(self, user_id: int) -> int:
        today = date.today().isoformat()
        if user_id not in user_downloads:
            return 0
        if user_downloads[user_id].get('date') != today:
            return 0
        return user_downloads[user_id].get('count', 0)
    
    def increment_user_downloads(self, user_id: int):
        today = date.today().isoformat()
        if user_id not in user_downloads or user_downloads[user_id].get('date') != today:
            user_downloads[user_id] = {'date': today, 'count': 0}
        user_downloads[user_id]['count'] += 1
    
    def has_active_task(self, user_id: int) -> bool:
        if user_id in user_active_tasks:
            if time.time() - user_active_tasks[user_id] < 600:
                return True
            else:
                del user_active_tasks[user_id]
        return False
    
    def set_active_task(self, user_id: int):
        user_active_tasks[user_id] = time.time()
    
    def remove_active_task(self, user_id: int):
        if user_id in user_active_tasks:
            del user_active_tasks[user_id]
    
    # ========== پردازش پیام‌ها ==========
    
    async def process_message(self, update: Dict[str, Any]):
        message = update.get('message')
        if not message:
            return
        
        chat_id = message.get('chat', {}).get('id')
        from_user = message.get('from') or message.get('from_user', {})
        user_id = from_user.get('id')
        
        if not chat_id or not user_id:
            return
        
        text = message.get('text', '').strip()
        
        # ========== دستور /start ==========
        if text == "/start":
            # بررسی عضویت
            is_member = await self.check_membership(user_id)
            
            if is_member:
                # اگر عضو هست، پیام خوش‌آمدگویی و منوی اصلی
                await self.send_message(
                    chat_id,
                    f"🌹 **سلام! خوش آمدی** 🌹\n\n"
                    f"✅ عضویت شما در کانال تایید شد.\n\n"
                    f"📥 **برای دانلود کافیه لینک فایل رو برام بفرستی**\n\n"
                    f"📊 محدودیت روزانه: {DAILY_LIMIT} فایل\n"
                    f"📁 حداکثر حجم: {MAX_SIZE_MB} مگابایت\n\n"
                    f"از منوی زیر استفاده کن:",
                    self.get_main_menu()
                )
            else:
                # اگر عضو نیست، پیام عضویت اجباری
                await self.send_message(
                    chat_id,
                    f"🔒 **عضویت اجباری** 🔒\n\n"
                    f"🚫 برای استفاده از ربات، ابتدا باید عضو کانال ما بشی!\n\n"
                    f"📢 **کانال:** {CHANNEL_ID}\n"
                    f"🔗 **لینک عضویت:** {CHANNEL_LINK}\n\n"
                    f"✅ **بعد از عضویت، روی دکمه «بررسی عضویت» کلیک کن**",
                    self.get_check_membership_button()
                )
            return
        
        # ========== برای پیام‌های غیر از /start ==========
        # بررسی عضویت
        is_member = await self.check_membership(user_id)
        
        if not is_member:
            # اگر عضو نیست، پیام عضویت اجباری
            await self.send_message(
                chat_id,
                f"🔒 **عضویت اجباری** 🔒\n\n"
                f"🚫 شما عضو کانال ما نیستی!\n\n"
                f"📢 **کانال:** {CHANNEL_ID}\n"
                f"🔗 **لینک عضویت:** {CHANNEL_LINK}\n\n"
                f"✅ بعد از عضویت، روی دکمه «بررسی عضویت» کلیک کن",
                self.get_check_membership_button()
            )
            return
        
        # ========== اگر عضو هست، پردازش پیام ==========
        
        # بررسی لینک
        if not (text.startswith('http://') or text.startswith('https://')):
            await self.send_message(
                chat_id,
                f"❌ **لینک نامعتبر!**\n\n"
                f"لطفاً یک لینک معتبر ارسال کنید:\n"
                f"`https://example.com/file.zip`\n\n"
                f"📊 برای مشاهده آمار از منو استفاده کن.",
                self.get_main_menu()
            )
            return
        
        # بررسی محدودیت روزانه
        if self.get_user_today_downloads(user_id) >= DAILY_LIMIT:
            await self.send_message(
                chat_id,
                f"⛔️ **به محدودیت روزانه رسیدی!**\n\n"
                f"📊 امروز {self.get_user_today_downloads(user_id)} فایل دانلود کرده‌ای.\n"
                f"🔢 حداکثر مجاز: {DAILY_LIMIT} فایل در روز\n\n"
                f"🕐 **فردا دوباره تلاش کن.**",
                self.get_main_menu()
            )
            return
        
        # بررسی تسک فعال
        if self.has_active_task(user_id):
            await self.send_message(
                chat_id,
                f"⏳ **در حال دانلود فایل قبلی...**\n\n"
                f"لطفاً صبر کنید تا دانلود فعلی تکمیل بشه.\n"
                f"حداکثر زمان انتظار: ۱۰ دقیقه",
                self.get_main_menu()
            )
            return
        
        # دریافت اطلاعات فایل
        status_msg = await self.send_message(chat_id, "🔍 **در حال بررسی لینک...**\n\n⏱ لطفاً چند لحظه صبر کنید...")
        status_msg_id = status_msg.get('result', {}).get('message_id')
        
        filename, file_size, error = await self.get_file_info(text)
        
        if error:
            await self.edit_message(chat_id, status_msg_id, error)
            return
        
        if file_size > MAX_SIZE_BYTES:
            size_mb = file_size / (1024 * 1024)
            await self.edit_message(chat_id, status_msg_id, 
                f"❌ **حجم فایل زیاد است!**\n\n"
                f"📁 حجم فایل: {size_mb:.1f} مگابایت\n"
                f"🔢 حداکثر مجاز: {MAX_SIZE_MB} مگابایت\n\n"
                f"لطفاً فایل کوچک‌تری ارسال کنید.")
            return
        
        # حذف پیام وضعیت
        await self.delete_message(chat_id, status_msg_id)
        
        # ذخیره لینک برای تأیید
        pending_downloads[user_id] = {
            'url': text,
            'filename': filename,
            'file_size': file_size,
            'timestamp': time.time()
        }
        
        size_text = self.format_size(file_size)
        rules_text = (
            f"📋 **تأییدیه دانلود** 📋\n\n"
            f"📁 **نام:** `{filename[:35]}`\n"
            f"💾 **حجم:** {size_text}\n"
            f"📊 **حد مجاز:** {MAX_SIZE_MB} مگابایت\n\n"
            f"⚠️ **توجه:** مسئولیت استفاده از فایل با خودته!\n\n"
            f"✅ آیا برای دانلود تأیید میکنی؟"
        )
        
        keyboard = self.get_confirm_keyboard(user_id)
        await self.send_message(chat_id, rules_text, keyboard)
    
    # ========== پردازش کلیک دکمه‌ها ==========
    
    async def process_callback(self, callback: Dict[str, Any]):
        message = callback.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        message_id = message.get('message_id')
        
        from_user = callback.get('from') or callback.get('from_user', {})
        user_id = from_user.get('id')
        
        data = callback.get('data', '')
        callback_id = callback.get('id', '')
        
        if not chat_id or not user_id:
            return
        
        await self.answer_callback(callback_id)
        
        # ========== دکمه بررسی عضویت ==========
        if data == 'check_member':
            # پاک کردن کش عضویت برای بررسی مجدد
            self.clear_membership_cache(user_id)
            
            # بررسی مجدد عضویت
            is_member = await self.check_membership(user_id)
            
            if is_member:
                # حذف پیام عضویت اجباری
                await self.delete_message(chat_id, message_id)
                
                # ارسال منوی اصلی
                await self.send_message(
                    chat_id,
                    f"🌹 **عضویت شما تایید شد!** 🌹\n\n"
                    f"✅ به ربات خوش آمدی.\n\n"
                    f"📥 **برای دانلود کافیه لینک فایل رو برام بفرستی**\n\n"
                    f"از منوی زیر استفاده کن:",
                    self.get_main_menu()
                )
            else:
                # هنوز عضو نشده
                await self.answer_callback(callback_id, "❌ شما هنوز عضو کانال نشدید! لطفاً ابتدا عضو شوید.", True)
            return
        
        # ========== منوی اصلی ==========
        
        if data == 'send_link':
            await self.send_message(
                chat_id,
                f"📥 **ارسال لینک دانلود**\n\n"
                f"لطفاً لینک مستقیم فایل مورد نظرت رو برام بفرست.\n\n"
                f"مثال: `https://example.com/file.zip`\n\n"
                f"📊 محدودیت‌ها:\n"
                f"• حداکثر حجم: {MAX_SIZE_MB} مگابایت\n"
                f"• تعداد روزانه: {DAILY_LIMIT} فایل",
                self.get_main_menu()
            )
            
        elif data == 'stats':
            used = self.get_user_today_downloads(user_id)
            remaining = DAILY_LIMIT - used
            has_active = self.has_active_task(user_id)
            
            stats_text = (
                f"📊 **آمار امروز شما** 📊\n\n"
                f"✅ دانلود شده: **{used}** فایل\n"
                f"⏳ باقی مانده: **{remaining}** فایل\n"
                f"🔢 سقف روزانه: **{DAILY_LIMIT}** فایل\n\n"
                f"{'⚡️ در حال دانلود...' if has_active else '✅ آماده برای دانلود'}\n\n"
                f"📥 برای دانلود، لینک فایل رو بفرست!"
            )
            await self.send_message(chat_id, stats_text, self.get_main_menu())
            
        elif data == 'help':
            help_text = (
                f"📖 **راهنمای کاربری ربات** 📖\n\n"
                f"**مراحل استفاده:**\n"
                f"1️⃣ لینک مستقیم فایل رو برام بفرست\n"
                f"2️⃣ ربات اطلاعات فایل رو بررسی میکنه\n"
                f"3️⃣ با تایید تو، دانلود شروع میشه\n"
                f"4️⃣ فایل دانلود و برات آپلود میشه\n\n"
                f"**محدودیت‌ها:**\n"
                f"• حداکثر حجم: {MAX_SIZE_MB} مگابایت\n"
                f"• تعداد در روز: {DAILY_LIMIT} فایل\n"
                f"• دانلود همزمان: فقط یک فایل\n\n"
                f"**فرمت‌های پشتیبانی:**\n"
                f"همه فرمت‌ها (ویدیو، صدا، عکس، PDF، ZIP و...)"
            )
            await self.send_message(chat_id, help_text, self.get_main_menu())
            
        elif data == 'about':
            about_text = (
                f"ℹ️ **درباره ربات** ℹ️\n\n"
                f"🤖 **نام:** ربات دانلودر حرفه‌ای\n"
                f"📡 **پلتفرم:** پیام‌رسان بله\n"
                f"📁 **حداکثر حجم:** {MAX_SIZE_MB} مگابایت\n"
                f"📊 **محدودیت روزانه:** {DAILY_LIMIT} فایل\n"
                f"🔒 **عضویت اجباری:** {CHANNEL_ID}\n\n"
                f"👨‍💻 **ساخته شده با:** Python + Love\n\n"
                f"🎯 **هدف:** دانلود آسان و سریع فایل‌ها"
            )
            await self.send_message(chat_id, about_text, self.get_main_menu())
        
        # ========== تأیید دانلود ==========
        elif data.startswith('confirm_'):
            confirm_user_id = int(data.split('_')[1])
            if confirm_user_id != user_id:
                await self.answer_callback(callback_id, "این دکمه مال شما نیست!", True)
                return
            
            if user_id not in pending_downloads:
                await self.edit_message(chat_id, message_id, 
                                      "❌ **لینک منقضی شده!**\n\nلطفاً دوباره لینک رو ارسال کنید.")
                return
            
            download_info = pending_downloads[user_id]
            url = download_info['url']
            del pending_downloads[user_id]
            
            await self.edit_message(chat_id, message_id, 
                                  "✅ **تأیید شد!**\n\n🎬 در حال آماده‌سازی برای دانلود...")
            
            self.set_active_task(user_id)
            
            status_msg = await self.send_message(chat_id, "🔄 **شروع دانلود...**\n\n⏱ در حال اتصال...")
            status_msg_id = status_msg.get('result', {}).get('message_id')
            
            asyncio.create_task(self.process_download(chat_id, user_id, url, status_msg_id))
        
        # ========== انصراف ==========
        elif data.startswith('cancel_'):
            cancel_user_id = int(data.split('_')[1])
            if cancel_user_id != user_id:
                await self.answer_callback(callback_id, "این دکمه مال شما نیست!", True)
                return
            
            if user_id in pending_downloads:
                del pending_downloads[user_id]
            await self.edit_message(chat_id, message_id, 
                                  "❌ **عملیات کنسل شد.**\n\n🎯 برای شروع دوباره، لینک جدید بفرست.")
    
    # ========== حلقه اصلی ==========
    async def run(self):
        await self.init_session()
        logger.info("🤖 ربات دانلودر شروع به کار کرد!")
        
        print("=" * 70)
        print("🚀 ربات دانلودر حرفه‌ای بله (نسخه ساده با عضویت اجباری)")
        print("=" * 70)
        print(f"📁 پوشه دانلود: {self.download_dir.absolute()}")
        print(f"📊 محدودیت روزانه: {DAILY_LIMIT} فایل")
        print(f"📁 حداکثر حجم: {MAX_SIZE_MB} مگابایت")
        print(f"🔒 کانال عضویت: {CHANNEL_ID}")
        print(f"🎨 طراحی: ساده، سریع، کاربرپسند")
        print("=" * 70)
        print("✅ ربات در حال اجراست...")
        print("📌 ویژگی‌ها:")
        print("   • عضویت اجباری ساده")
        print("   • منوی اصلی برای اعضا")
        print("   • بررسی خودکار عضویت")
        print("   • حذف خودکار پیام عضویت بعد از تایید")
        print("❌ Ctrl+C برای توقف")
        print("=" * 70)
        
        offset = 0
        while True:
            try:
                async with self.session.get(
                    f"{self.base_url}/getUpdates",
                    params={'offset': offset, 'timeout': 30}
                ) as resp:
                    data = await resp.json()
                    if data.get('ok') and data.get('result'):
                        for update in data['result']:
                            if 'message' in update:
                                await self.process_message(update)
                            elif 'callback_query' in update:
                                await self.process_callback(update['callback_query'])
                            offset = update['update_id'] + 1
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error: {e}")
                await asyncio.sleep(5)

# =================== اجرا ===================
async def main():
    bot = DownloadBot(BOT_TOKEN)
    try:
        await bot.run()
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
