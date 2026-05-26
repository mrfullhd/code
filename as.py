# test_proxies_with_cookie_file.py
import asyncio
import sys
import os
import yt_dlp
from typing import List, Tuple, Optional
from datetime import datetime


class ProxyTester:
    def __init__(self, proxy_file: str = "working_proxies.txt", cookie_file: str = None, output_file: str = None):
        self.proxy_file = proxy_file
        self.cookie_file = cookie_file
        self.output_file = output_file or f"valid_proxies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        self.proxies = []
        self.load_proxies()
        self.check_cookie_file()
    
    def load_proxies(self):
        """بارگذاری پروکسی‌ها از فایل"""
        try:
            with open(self.proxy_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and ':' in line:
                        # پرش از خطوط توضیحی
                        if line.startswith('#') or line.startswith('//'):
                            continue
                        # تبدیل IP:PORT به فرمت socks5://IP:PORT
                        if not line.startswith('socks5://'):
                            self.proxies.append(f"socks5://{line}")
                        else:
                            self.proxies.append(line)
            print(f"✅ Loaded {len(self.proxies)} proxies from {self.proxy_file}")
        except FileNotFoundError:
            print(f"❌ Proxy file {self.proxy_file} not found!")
            print(f"💡 Please create {self.proxy_file} with proxies (one per line, format: IP:PORT)")
            sys.exit(1)
    
    def check_cookie_file(self):
        """بررسی وجود فایل کوکی"""
        if self.cookie_file and os.path.exists(self.cookie_file):
            print(f"✅ Cookie file found: {self.cookie_file}")
            return True
        
        # اگر کوکی مشخص نشده یا وجود ندارد، چند مسیر پیشفرض را چک کن
        default_paths = [
            "cookies.txt",
            "youtube_cookies.txt",
            "cookies/youtube.txt",
            "../cookies.txt",
            "apps/youtube-downloader/cookies.txt"
        ]
        
        for path in default_paths:
            if os.path.exists(path):
                self.cookie_file = path
                print(f"✅ Cookie file found: {self.cookie_file}")
                return True
        
        print("⚠️ No cookie file found! Testing may fail with bot detection.")
        return False
    
    def get_ytdl_opts(self, proxy_url: str) -> dict:
        """گرفتن تنظیمات yt-dlp با کوکی فایل"""
        opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 15,
            'retries': 3,
            'proxy': proxy_url,
        }
        
        # اضافه کردن کوکی فایل اگر وجود داشته باشد
        if self.cookie_file and os.path.exists(self.cookie_file):
            opts['cookiefile'] = self.cookie_file
        
        return opts
    
    def test_proxy(self, proxy_url: str, test_url: str = "https://www.youtube.com/watch?v=jNQXAC9IVRw") -> Tuple[bool, str]:
        """تست یک پروکسی با استفاده از فایل کوکی"""
        
        opts = self.get_ytdl_opts(proxy_url)
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                # فقط اطلاعات بگیر، دانلود نکن
                info = ydl.extract_info(test_url, download=False)
                
                if info:
                    title = info.get('title', 'Unknown')
                    duration = info.get('duration', 0)
                    return True, f"✅ Success - '{title}' ({duration}s)"
                else:
                    return False, "❌ No info returned"
                    
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e).lower()
            
            # تشخیص نوع خطا
            if "sign in" in error_msg or "login" in error_msg:
                return False, "❌ Login required - Cookie may be expired"
            elif "bot" in error_msg or "unable to extract" in error_msg:
                return False, "❌ Bot detected - Cookie may be invalid"
            elif "proxy" in error_msg or "connection" in error_msg:
                return False, "❌ Proxy connection failed"
            elif "unavailable" in error_msg:
                return False, "❌ Video unavailable"
            elif "private" in error_msg:
                return False, "❌ Video is private"
            else:
                short_err = error_msg[:80].replace('\n', ' ')
                return False, f"❌ Error: {short_err}"
                
        except Exception as e:
            return False, f"❌ Exception: {str(e)[:80]}"
    
    async def test_all_proxies(self, max_proxies: int = None, delay: float = 0.5):
        """تست همه پروکسی‌ها"""
        
        proxies_to_test = self.proxies[:max_proxies] if max_proxies else self.proxies
        working_proxies = []
        failed_proxies = []
        
        print(f"\n🚀 Testing {len(proxies_to_test)} proxies from {self.proxy_file}...")
        print(f"📁 Cookie file: {self.cookie_file if self.cookie_file else 'Not found!'}")
        print(f"💾 Output file: {self.output_file}")
        print("-" * 70)
        
        for i, proxy in enumerate(proxies_to_test, 1):
            # نمایش پروکسی به صورت خلاصه
            proxy_short = proxy.replace('socks5://', '')[:40]
            print(f"[{i:3d}/{len(proxies_to_test)}] Testing {proxy_short}...", end=" ", flush=True)
            
            success, message = self.test_proxy(proxy)
            
            if success:
                print(f"\n     {message}")
                working_proxies.append(proxy)
            else:
                print(f"{message}")
                failed_proxies.append((proxy, message))
            
            # کمی تأخیر برای جلوگیری از ریت لیمیت
            await asyncio.sleep(delay)
        
        # نمایش نتایج
        print("\n" + "=" * 70)
        print("📊 RESULTS SUMMARY")
        print("=" * 70)
        print(f"✅ Working proxies: {len(working_proxies)}/{len(proxies_to_test)}")
        print(f"❌ Failed proxies: {len(failed_proxies)}/{len(proxies_to_test)}")
        
        # ذخیره پروکسی‌های کارا در فایل جدید
        if working_proxies:
            with open(self.output_file, 'w') as f:
                # نوشتن هدر
                f.write(f"# Valid proxies tested on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Total working: {len(working_proxies)}/{len(proxies_to_test)}\n")
                f.write("# Format: IP:PORT\n\n")
                
                for proxy in working_proxies:
                    # ذخیره بدون پروتکل
                    clean_proxy = proxy.replace('socks5://', '')
                    f.write(clean_proxy + '\n')
            
            print(f"\n💾 Valid proxies saved to: {self.output_file}")
            
            # نمایش نمونه از پروکسی‌های کارا
            print("\n📝 Valid proxies list:")
            for proxy in working_proxies[:20]:
                print(f"  {proxy.replace('socks5://', '')}")
            
            if len(working_proxies) > 20:
                print(f"  ... and {len(working_proxies) - 20} more")
            
            # همچنین ذخیره با فرمت JSON برای استفاده برنامه‌ای
            json_file = self.output_file.replace('.txt', '.json')
            import json
            with open(json_file, 'w') as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "total_tested": len(proxies_to_test),
                    "working_count": len(working_proxies),
                    "working_proxies": [p.replace('socks5://', '') for p in working_proxies]
                }, f, indent=2)
            print(f"💾 JSON format saved to: {json_file}")
            
        else:
            print("\n❌ No working proxies found!")
            print("\n💡 Troubleshooting tips:")
            print("  1. Check if your cookie file is valid:")
            print(f"     yt-dlp --cookies {self.cookie_file} --simulate https://youtube.com")
            print("  2. Make sure proxies are alive:")
            print("     curl -x socks5://IP:PORT https://httpbin.org/ip")
            print("  3. Try extracting fresh cookies from browser")
        
        return working_proxies, failed_proxies
    
    async def test_single_proxy(self, proxy: str):
        """تست یک پروکسی خاص"""
        print(f"\n🔍 Testing single proxy: {proxy}")
        print("-" * 50)
        
        success, message = self.test_proxy(proxy)
        print(f"Result: {message}")
        
        return success


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Test SOCKS5 proxies with cookie file')
    parser.add_argument('-i', '--input', default='working_proxies.txt', 
                        help='Input proxy file (default: working_proxies.txt)')
    parser.add_argument('-o', '--output', default=None, 
                        help='Output file for valid proxies (default: valid_proxies_TIMESTAMP.txt)')
    parser.add_argument('-c', '--cookie', default=None, 
                        help='Cookie file path (cookies.txt)')
    parser.add_argument('-m', '--max', type=int, default=None, 
                        help='Maximum proxies to test')
    parser.add_argument('-s', '--single', type=str, default=None, 
                        help='Test a single proxy (IP:PORT)')
    parser.add_argument('-d', '--delay', type=float, default=0.5, 
                        help='Delay between tests (seconds)')
    
    args = parser.parse_args()
    
    # اگر کاربر آرگومان تک پروکسی داده
    if args.single:
        tester = ProxyTester(args.input, args.cookie, args.output)
        proxy_to_test = args.single
        if not proxy_to_test.startswith('socks5://'):
            proxy_to_test = f"socks5://{proxy_to_test}"
        await tester.test_single_proxy(proxy_to_test)
    else:
        tester = ProxyTester(args.input, args.cookie, args.output)
        await tester.test_all_proxies(max_proxies=args.max, delay=args.delay)


if __name__ == "__main__":
    asyncio.run(main())
