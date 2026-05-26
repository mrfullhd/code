import aiosqlite
from datetime import date, datetime, timedelta
from typing import Optional
import logging

from config import DATABASE_PATH
logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.db_path = DATABASE_PATH

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    username TEXT, first_name TEXT,
                    is_vip INTEGER DEFAULT 0, vip_expiry TEXT,
                    join_date TEXT NOT NULL,
                    total_downloads INTEGER DEFAULT 0,
                    is_banned INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL, url TEXT NOT NULL,
                    title TEXT, quality TEXT, file_size INTEGER,
                    status TEXT DEFAULT 'pending', created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL, use_date TEXT NOT NULL,
                    count INTEGER DEFAULT 0, UNIQUE(user_id, use_date)
                );
                CREATE INDEX IF NOT EXISTS idx_u ON users(user_id);
                CREATE INDEX IF NOT EXISTS idx_d ON downloads(user_id);
                CREATE INDEX IF NOT EXISTS idx_du ON daily_usage(user_id, use_date);
            """)
            await db.commit()
        logger.info("DB ready")

    async def get_user(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as c:
                r = await c.fetchone()
                return dict(r) if r else None

    async def get_or_create_user(self, user_id, username=None, first_name=None):
        u = await self.get_user(user_id)
        if u:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("UPDATE users SET username=?,first_name=? WHERE user_id=?",
                                 (username, first_name, user_id))
                await db.commit()
            return u
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO users(user_id,username,first_name,join_date) VALUES(?,?,?,?)",
                             (user_id, username, first_name, datetime.now().isoformat()))
            await db.commit()
        return await self.get_user(user_id)

    async def is_banned(self, user_id):
        u = await self.get_user(user_id)
        return bool(u and u.get("is_banned"))

    async def set_vip(self, user_id, days=30):
        expiry = (datetime.now() + timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET is_vip=1,vip_expiry=? WHERE user_id=?",
                             (expiry, user_id))
            await db.commit()
        return True

    async def remove_vip(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET is_vip=0,vip_expiry=NULL WHERE user_id=?",
                             (user_id,))
            await db.commit()
        return True

    async def is_vip(self, user_id):
        u = await self.get_user(user_id)
        if not u or not u.get("is_vip"):
            return False
        exp = u.get("vip_expiry")
        if exp and datetime.now() > datetime.fromisoformat(exp):
            await self.remove_vip(user_id)
            return False
        return True

    async def get_vip_expiry(self, user_id) -> Optional[datetime]:
        u = await self.get_user(user_id)
        if u and u.get("vip_expiry"):
            return datetime.fromisoformat(u["vip_expiry"])
        return None

    async def get_daily_count(self, user_id):
        today = date.today().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT count FROM daily_usage WHERE user_id=? AND use_date=?",
                                  (user_id, today)) as c:
                r = await c.fetchone()
                return r[0] if r else 0

    async def increment_daily_count(self, user_id):
        today = date.today().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO daily_usage(user_id,use_date,count) VALUES(?,?,1)"
                " ON CONFLICT(user_id,use_date) DO UPDATE SET count=count+1",
                (user_id, today))
            await db.execute("UPDATE users SET total_downloads=total_downloads+1 WHERE user_id=?",
                             (user_id,))
            await db.commit()

    async def log_download(self, user_id, url, title=None, quality=None,
                           file_size=None, status="success"):
        async with aiosqlite.connect(self.db_path) as db:
            c = await db.execute(
                "INSERT INTO downloads(user_id,url,title,quality,file_size,status,created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (user_id, url, title, quality, file_size, status, datetime.now().isoformat()))
            await db.commit()
            return c.lastrowid

    async def get_stats(self):
        today = date.today().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as c:
                total = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM users WHERE is_vip=1") as c:
                vip = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM downloads") as c:
                dl = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM downloads WHERE DATE(created_at)=?",
                                  (today,)) as c:
                today_dl = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM users WHERE DATE(join_date)=?",
                                  (today,)) as c:
                today_u = (await c.fetchone())[0]
        return {"total_users": total, "vip_users": vip, "free_users": total - vip,
                "total_downloads": dl, "today_downloads": today_dl, "today_users": today_u}

    async def get_all_user_ids(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM users WHERE is_banned=0") as c:
                return [r[0] for r in await c.fetchall()]

    async def ban_user(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
            await db.commit()

    async def unban_user(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
            await db.commit()
