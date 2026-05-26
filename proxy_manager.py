# proxy_manager.py
import random
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


class ProxyManager:
    def __init__(self, proxy_file: str = "working_proxies.txt"):
        self.proxies = []
        self.current_index = 0
        self.load_proxies(proxy_file)
    
    def load_proxies(self, proxy_file: str):
        """بارگذاری پروکسی‌ها از فایل"""
        try:
            with open(proxy_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and ':' in line:
                        # تبدیل IP:PORT به فرمت socks5://IP:PORT
                        proxy_url = f"socks5://{line}"
                        self.proxies.append(proxy_url)
            logger.info(f"Loaded {len(self.proxies)} proxies from {proxy_file}")
            print(f"✅ Loaded {len(self.proxies)} proxies from {proxy_file}")
        except FileNotFoundError:
            logger.warning(f"Proxy file {proxy_file} not found. Running without proxy.")
            print(f"⚠️ Proxy file {proxy_file} not found. Running without proxy.")
        except Exception as e:
            logger.error(f"Error loading proxies: {e}")
            print(f"❌ Error loading proxies: {e}")
    
    def get_next_proxy(self) -> Optional[str]:
        """دریافت پروکسی بعدی (Round-robin)"""
        if not self.proxies:
            return None
        proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)
        return proxy
    
    def get_random_proxy(self) -> Optional[str]:
        """دریافت پروکسی تصادفی"""
        if not self.proxies:
            return None
        return random.choice(self.proxies)
    
    def get_proxy_for_url(self, url: str, retry_count: int = 0) -> Optional[str]:
        """انتخاب پروکسی بر اساس URL و تعداد تلاش"""
        # می‌توانید منطق خاصی برای انتخاب پروکسی پیاده کنید
        # مثلاً برای YouTube از پروکسی‌های تصادفی استفاده کن
        if "youtube.com" in url or "youtu.be" in url:
            # برای یوتیوب از پروکسی‌های تصادفی استفاده کن
            return self.get_random_proxy()
        return self.get_next_proxy()
    
    def mark_failed(self, proxy: str):
        """علامت‌گذاری پروکسی خراب (اختیاری)"""
        # می‌توانید برای ردیابی پروکسی‌های خراب استفاده کنید
        pass