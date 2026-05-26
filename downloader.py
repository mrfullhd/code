import asyncio
import os
import re
import time
import logging
from pathlib import Path
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor

import yt_dlp
from config import DOWNLOAD_DIR, PROXY_URL, YOUTUBE_COOKIES_FILE, FREE_MAX_HEIGHT, AUDIO_OPTIONS

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=4)
_URL_RE = re.compile(r"https?://[^\s/$.?#].[^\s]*", re.IGNORECASE)


def extract_url(text):
    m = _URL_RE.search(text.strip())
    return m.group(0) if m else None


class Downloader:
    def __init__(self):
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    def _base(self):
        o = {"quiet": True, "no_warnings": True, "socket_timeout": 30,
             "retries": 5, "fragment_retries": 5,
             "http_chunk_size": 10 * 1024 * 1024, "concurrent_fragment_downloads": 4}
        if PROXY_URL:
            o["proxy"] = PROXY_URL
        if YOUTUBE_COOKIES_FILE and os.path.exists(YOUTUBE_COOKIES_FILE):
            o["cookiefile"] = YOUTUBE_COOKIES_FILE
        return o

    def _extract_sync(self, url):
        with yt_dlp.YoutubeDL({**self._base(), "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError("اطلاعات ویدیو دریافت نشد.")
            if info.get("_type") == "playlist":
                entries = info.get("entries", [])
                if not entries:
                    raise ValueError("پلی‌لیست خالی است.")
                info = entries[0]
            return info

    async def get_video_info(self, url):
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(_executor, self._extract_sync, url)
        except yt_dlp.utils.DownloadError as e:
            err = str(e).lower()
            if "private" in err or "members only" in err:
                raise ValueError("این ویدیو خصوصی یا محدود شده.")
            if "sign in" in err or "login" in err:
                raise ValueError("این ویدیو نیاز به لاگین دارد.")
            if "unavailable" in err or "not available" in err:
                raise ValueError("این ویدیو در دسترس نیست.")
            raise ValueError(f"خطا: {str(e)[:200]}")

    def parse_formats(self, info, is_vip=False):
        raw = info.get("formats", [])
        hmap = {}
        for f in raw:
            h = f.get("height")
            if not h or h < 100 or not f.get("vcodec") or f.get("vcodec") == "none":
                continue
            tbr = f.get("tbr") or f.get("vbr") or 0
            if h not in hmap or tbr > (hmap[h].get("tbr") or 0):
                hmap[h] = {**f, "tbr": tbr}

        videos = []
        for h in sorted(hmap.keys(), reverse=True):
            f = hmap[h]
            fs = f.get("filesize") or f.get("filesize_approx")
            fps = f.get("fps") or 0
            vip_req = h > FREE_MAX_HEIGHT
            videos.append({"height": h, "label": f"{h}p",
                           "filesize": fs, "filesize_approx": f.get("filesize") is None and bool(fs),
                           "fps": fps, "vcodec": f.get("vcodec", ""), "tbr": f.get("tbr", 0),
                           "vip_required": vip_req})

        audios = [{**ao, "vip_required": ao.get("vip_only", False)} for ao in AUDIO_OPTIONS]
        return {"video": videos, "audio": audios, "is_live": info.get("is_live", False)}

    def _dl_sync(self, url, fmt, tmpl, hook=None, is_audio=False, afmt="mp3", aqty="192"):
        opts = {**self._base(), "format": fmt, "outtmpl": tmpl,
                "merge_output_format": "mp4", "no_playlist": True,
                "writeinfojson": False, "writethumbnail": False}
        if is_audio:
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio",
                                       "preferredcodec": afmt, "preferredquality": aqty}]
        found = [None]

        def _hook(d):
            if d["status"] == "finished":
                found[0] = d.get("filename")
            if hook:
                hook(d)

        opts["progress_hooks"] = [_hook]
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if found[0] and os.path.exists(found[0]):
                return found[0]
            fn = ydl.prepare_filename(info)
            for ext in ["mp4", "mkv", "webm", afmt, "m4a", "opus"]:
                c = Path(fn).with_suffix(f".{ext}")
                if c.exists():
                    return str(c)
            for f in Path(fn).parent.iterdir():
                if f.stem == Path(fn).stem and f.is_file():
                    return str(f)
            return fn

    async def download(self, url, height=None, is_audio=False, audio_format="mp3",
                       audio_quality="192", user_id=0, progress_callback=None):
        loop = asyncio.get_event_loop()
        if is_audio:
            fspec = "bestaudio[ext=m4a]/bestaudio/best"
        elif height:
            fspec = (f"bestvideo[height={height}][ext=mp4]+bestaudio[ext=m4a]/"
                     f"bestvideo[height={height}]+bestaudio/"
                     f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
                     f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best")
        else:
            fspec = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

        ts = int(time.time())
        odir = os.path.join(DOWNLOAD_DIR, f"u{user_id}_{ts}")
        os.makedirs(odir, exist_ok=True)
        tmpl = os.path.join(odir, "%(title).80s.%(ext)s")
        last = [0]

        def shook(d):
            now = time.time()
            if not progress_callback or now - last[0] < 2:
                return
            last[0] = now
            s = d.get("status")
            if s == "downloading":
                dl = d.get("downloaded_bytes", 0)
                tot = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                asyncio.run_coroutine_threadsafe(
                    progress_callback(status="downloading", percent=(dl / tot * 100) if tot else 0,
                                      downloaded=dl, total=tot,
                                      speed=d.get("speed") or 0, eta=d.get("eta") or 0), loop)
            elif s == "finished":
                asyncio.run_coroutine_threadsafe(
                    progress_callback(status="merging", percent=100), loop)

        try:
            fp = await loop.run_in_executor(_executor, lambda: self._dl_sync(
                url, fspec, tmpl, shook if progress_callback else None,
                is_audio, audio_format, audio_quality))
        except yt_dlp.utils.DownloadError as e:
            raise ValueError(f"خطا در دانلود: {str(e)[:300]}")
        except Exception as e:
            raise ValueError(f"خطا: {str(e)[:200]}")

        if not fp or not os.path.exists(fp):
            raise ValueError("فایل دانلودشده پیدا نشد.")
        stat = os.stat(fp)
        return fp, {"filesize": stat.st_size, "filename": os.path.basename(fp)}

    @staticmethod
    def cleanup(fp):
        try:
            if os.path.isfile(fp):
                os.remove(fp)
            p = os.path.dirname(fp)
            if os.path.isdir(p) and not os.listdir(p):
                os.rmdir(p)
        except Exception as e:
            logger.warning(f"cleanup err: {e}")

    @staticmethod
    def fmt_dur(s):
        if not s:
            return "--:--"
        h, m, sec = s // 3600, (s % 3600) // 60, s % 60
        return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"

    @staticmethod
    def fmt_size(n, approx=False):
        if not n:
            return "?"
        p = "~" if approx else ""
        if n >= 1 << 30:
            return f"{p}{n/(1<<30):.1f}GB"
        if n >= 1 << 20:
            return f"{p}{n/(1<<20):.1f}MB"
        if n >= 1 << 10:
            return f"{p}{n/(1<<10):.1f}KB"
        return f"{p}{n}B"

    @staticmethod
    def fmt_views(v):
        if not v:
            return "?"
        if v >= 1_000_000_000:
            return f"{v/1_000_000_000:.1f}B"
        if v >= 1_000_000:
            return f"{v/1_000_000:.1f}M"
        if v >= 1_000:
            return f"{v/1_000:.1f}K"
        return str(v)

    @staticmethod
    def pbar(pct, n=12):
        f = int(pct / 100 * n)
        return f"{'|' * f}{'-' * (n - f)} {pct:.0f}%"

    # Aliases for compatibility
    def format_filesize(self, s, approx=False):
        return self.fmt_size(s, approx)

    def format_duration(self, s):
        return self.fmt_dur(s)

    def format_views(self, v):
        return self.fmt_views(v)

    def progress_bar(self, pct, n=12):
        return self.pbar(pct, n)
