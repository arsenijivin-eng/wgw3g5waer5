import sqlite3
from datetime import datetime, timedelta, timezone

class DB:
    def __init__(self, path):
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.init()

    def init(self):
        self.c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY, username TEXT, referrer INTEGER,
          trial_used INTEGER DEFAULT 0, expires_at TEXT, balance REAL DEFAULT 0,
          state TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS links(
          id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, link TEXT, used INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS devices(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, link TEXT,
          created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS orders(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, days INTEGER,
          method TEXT, rub REAL, stars INTEGER, status TEXT DEFAULT 'pending',
          created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS promos(
          code TEXT PRIMARY KEY, amount REAL, uses_left INTEGER
        );
        CREATE TABLE IF NOT EXISTS withdrawals(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL,
          card TEXT, status TEXT DEFAULT 'pending', created_at TEXT
        );
        """)
        self.c.commit()

    def user(self, uid, username="", referrer=None):
        r=self.c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not r:
            self.c.execute("INSERT INTO users(id,username,referrer,created_at) VALUES(?,?,?,?)",
                           (uid,username,referrer if referrer and referrer != uid else None,
                            datetime.now(timezone.utc).isoformat()))
            self.c.commit()
            r=self.c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return r

    def activate_trial(self, uid):
        r=self.user(uid)
        if r["trial_used"]: return None
        exp=datetime.now(timezone.utc)+timedelta(days=3)
        self.c.execute("UPDATE users SET trial_used=1,expires_at=? WHERE id=?",
                       (exp.isoformat(),uid))
        self.c.commit()
        return exp.isoformat()

    def add_link(self, kind, link):
        self.c.execute("INSERT INTO links(kind,link) VALUES(?,?)",(kind,link))
        self.c.commit()

    def take_link(self, kind, uid):
        r=self.c.execute("SELECT id,link FROM links WHERE kind=? AND used=0 ORDER BY id LIMIT 1",(kind,)).fetchone()
        if not r:return None
        self.c.execute("UPDATE links SET used=1 WHERE id=?",(r["id"],))
        self.c.commit()
        return r["link"]

    def add_device(self, uid, link):
        r=self.user(uid)
        if self.device_count(uid) >= 3: return False
        self.c.execute("INSERT INTO devices(user_id,link,created_at) VALUES(?,?,?)",
                       (r["id"],link,datetime.now(timezone.utc).isoformat()))
        self.c.commit(); return True

    def device_count(self, uid):
        r=self.c.execute("SELECT COUNT(*) n FROM devices WHERE user_id=?",(uid,)).fetchone()
        return r["n"]

    def create_order(self, uid, days, method, rub, stars):
        self.c.execute("INSERT INTO orders(user_id,days,method,rub,stars,created_at) VALUES(?,?,?,?,?,?)",
                       (uid,days,method,rub,stars,datetime.now(timezone.utc).isoformat()))
        self.c.commit()
        return self.c.execute("SELECT last_insert_rowid()").fetchone()[0]

    def balance(self, uid):
        r=self.user(uid)
        return float(r["balance"] or 0)

    def set_state(self, uid, state):
        self.c.execute("UPDATE users SET state=? WHERE id=?",(state,uid)); self.c.commit()

    def clear_state(self, uid):
        self.set_state(uid,None)

    def get_state(self, uid):
        r=self.user(uid); return r["state"]

    def add_promo(self, code, amount, uses):
        self.c.execute("INSERT OR REPLACE INTO promos(code,amount,uses_left) VALUES(?,?,?)",(code.upper(),amount,uses))
        self.c.commit()

    def use_promo(self, uid, code):
        r=self.c.execute("SELECT * FROM promos WHERE code=? AND uses_left>0",(code.upper(),)).fetchone()
        if not r:return "❌ Промокод недействителен."
        self.c.execute("UPDATE promos SET uses_left=uses_left-1 WHERE code=?",(code.upper(),))
        self.c.execute("UPDATE users SET balance=balance+? WHERE id=?",(r["amount"],uid))
        self.c.commit()
        return f"✅ Промокод применён!\nНачислено: {r['amount']:.2f}₽"

    def all_user_ids(self):
        return [r["id"] for r in self.c.execute("SELECT id FROM users").fetchall()]

    def find_user(self, query):
        r = None
        if query.isdigit():
            r = self.c.execute("SELECT * FROM users WHERE id=?", (int(query),)).fetchone()
        else:
            r = self.c.execute("SELECT * FROM users WHERE lower(username)=lower(?)", (query,)).fetchone()
        if not r:
            return "❌ Пользователь не найден."
        refs = self.c.execute("SELECT COUNT(*) n FROM users WHERE referrer=?", (r["id"],)).fetchone()["n"]
        purchases = self.c.execute("SELECT COUNT(*) n FROM orders WHERE user_id=? AND status='paid'", (r["id"],)).fetchone()["n"]
        devices = self.device_count(r["id"])
        exp = r["expires_at"] or "—"
        return (f"👤 Пользователь\n\nID: {r['id']}\nUsername: @{r['username'] or 'нет'}\n"
                f"👥 Приглашено: {refs}\n🛒 Покупок: {purchases}\n"
                f"📱 Устройств: {devices}/3\n💰 Баланс: {float(r['balance'] or 0):.2f}₽\n"
                f"⏳ Подписка до: {exp}")

    def stats_detailed(self):
        total = self.c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        trials = self.c.execute("SELECT COUNT(*) n FROM users WHERE trial_used=1").fetchone()["n"]
        active = self.c.execute(
            "SELECT COUNT(*) n FROM users WHERE expires_at IS NOT NULL AND expires_at>?",
            (datetime.now(timezone.utc).isoformat(),)).fetchone()["n"]
        orders = self.c.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"]
        paid = self.c.execute("SELECT COUNT(*) n FROM orders WHERE status='paid'").fetchone()["n"]
        revenue = self.c.execute("SELECT COALESCE(SUM(rub),0) s FROM orders WHERE status='paid'").fetchone()["s"]
        refs = self.c.execute("SELECT COUNT(*) n FROM users WHERE referrer IS NOT NULL").fetchone()["n"]
        links = self.c.execute("SELECT COUNT(*) n FROM links WHERE used=0").fetchone()["n"]
        return (f"📊 Статистика CristyVPN\n\n👥 Зашли в бота: {total}\n"
                f"🎁 Взяли пробный период: {trials}\n🟢 Активных подписок: {active}\n"
                f"🛒 Заказов: {orders}\n✅ Оплаченных: {paid}\n"
                f"💰 Выручка: {float(revenue or 0):.2f}₽\n"
                f"👥 Пользователей с рефералами: {refs}\n🔗 Свободных ссылок: {links}")

    def purchases_stats(self):
        rows = self.c.execute(
            "SELECT days, COUNT(*) n, COALESCE(SUM(rub),0) s FROM orders "
            "WHERE status='paid' GROUP BY days ORDER BY days").fetchall()
        if not rows:
            return "📈 Покупок пока нет."
        lines = ["📈 Статистика покупок\n"]
        for r in rows:
            lines.append(f"▸ {r['days']} дней: {r['n']} покупок • {float(r['s']):.2f}₽")
        total = self.c.execute("SELECT COUNT(*) n FROM orders WHERE status='paid'").fetchone()["n"]
        lines.append(f"\nВсего оплачено заказов: {total}")
        return "\n".join(lines)

    def users_page(self):
        rows = self.c.execute(
            "SELECT id,username,trial_used,expires_at,balance FROM users ORDER BY id DESC LIMIT 30").fetchall()
        if not rows:
            return "👥 Пользователей пока нет."
        out = ["👥 Последние 30 пользователей\n"]
        for r in rows:
            out.append(f"ID {r['id']} • @{r['username'] or 'нет'} • "
                       f"пробник={'да' if r['trial_used'] else 'нет'} • баланс={float(r['balance'] or 0):.2f}₽")
        return "\n".join(out)

    def stats(self):
        u=self.c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        o=self.c.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"]
        l=self.c.execute("SELECT COUNT(*) n FROM links WHERE used=0").fetchone()["n"]
        return f"📊 Статистика\n\n👥 Пользователей: {u}\n🛒 Заказов: {o}\n🔗 Свободных ссылок: {l}"

    def orders_text(self):
        rows=self.c.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 20").fetchall()
        if not rows:return "🛒 Заказов пока нет."
        return "🛒 Последние заказы:\n\n" + "\n".join(
            f"#{r['id']} • ID {r['user_id']} • {r['days']}д • {r['rub']}₽ • {r['method']} • {r['status']}" for r in rows
        )

    def withdraws_text(self):
        rows=self.c.execute("SELECT * FROM withdrawals ORDER BY id DESC LIMIT 20").fetchall()
        if not rows:return "💸 Заявок на вывод пока нет."
        return "💸 Последние выводы:\n\n" + "\n".join(
            f"#{r['id']} • ID {r['user_id']} • {r['amount']}₽ • {r['status']}" for r in rows
        )