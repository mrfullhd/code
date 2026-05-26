# test_proxies_before_use.py
import asyncio
from proxy_manager import ProxyManager
from downloader import Downloader  # کلاس Downloader جدید

async def test_all_proxies():
    """تست همه پروکسی‌ها قبل از استفاده"""
    proxy_manager = ProxyManager("working_proxies.txt")
    working_proxies = []
    
    for proxy_url in proxy_manager.proxies:
        try:
            # تست با یک ویدیوی کوتاه و عمومی
            downloader = Downloader(use_proxy_rotation=False)
            # موقتاً پروکسی را تنظیم کن
            downloader.current_proxy = proxy_url
            
            info = await downloader.get_video_info("https://www.youtube.com/watch?v=jNQXAC9IVRw")
            if info:
                working_proxies.append(proxy_url)
                print(f"✓ {proxy_url} works")
        except Exception as e:
            print(f"✗ {proxy_url} failed: {str(e)[:50]}")
    
    # ذخیره پروکسی‌های کارا
    with open("working_proxies.txt", "w") as f:
        for proxy in working_proxies:
            f.write(proxy.replace("socks5://", "") + "\n")
    
    print(f"\nFound {len(working_proxies)} working proxies")

if __name__ == "__main__":
    asyncio.run(test_all_proxies())