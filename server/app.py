#!/usr/bin/env python3
"""Городской компас: статика dist/ + API авторизации и профиля (только стандартная библиотека).

Запуск:  python server/app.py [--port 4183] [--host 127.0.0.1]

Безопасность:
  * пароли — PBKDF2-HMAC-SHA256 (240 000 итераций) с индивидуальной солью;
  * сессия — случайный токен 256 бит в HttpOnly-cookie (SameSite=Lax), в базе хранится только его SHA-256;
  * ограничение попыток входа (5 неудач за 10 минут на почту+IP), одинаковый ответ для «нет почты» и «неверный пароль»;
  * тела запросов только JSON, лимит размера, строгая проверка полей;
  * статика отдаётся только из dist/, выход за каталог невозможен.
Для публикации в интернет поставьте за HTTPS-прокси и включите COMPASS_SECURE_COOKIE=1.
"""
import os
import argparse, gzip, hashlib, hmac, json, mimetypes, os, re, secrets, sqlite3, threading, time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
DB_PATH = ROOT / "data" / "users.db"
PBKDF2_ITERS = 240_000
SESSION_TTL = 30 * 24 * 3600
MAX_BODY = 200_000
SECURE_COOKIE = os.environ.get("COMPASS_SECURE_COOKIE") == "1"
EMAIL_RX = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
COLORS = {"teal", "violet", "amber", "rose", "sky", "lime", "slate"}

_db_lock = threading.Lock()
_fails = {}  # (email, ip) -> [timestamps]
_file_cache = {}  # (путь, etag) -> (байты, gzip-байты)


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db():
    with _db_lock, db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL DEFAULT '',
          color TEXT NOT NULL DEFAULT 'teal', salt BLOB NOT NULL, hash BLOB NOT NULL, created REAL NOT NULL,
          settings TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS sessions(
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created REAL NOT NULL, expires REAL NOT NULL);
        """)


def hash_pw(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERS)


def public_user(row):
    return {"id": row["id"], "email": row["email"], "name": row["name"], "color": row["color"], "created": row["created"]}


class Handler(BaseHTTPRequestHandler):
    server_version = "Compass/1.0"

    # ---------- вспомогательное ----------
    def log_message(self, fmt, *args):
        pass

    def send_json(self, code, obj, extra_headers=()):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in extra_headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return None
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n <= 0 or n > MAX_BODY:
            return None
        try:
            data = json.loads(self.rfile.read(n))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def ip(self):
        return self.client_address[0]

    def cookie_header(self, token, max_age):
        parts = [f"sid={token}", "Path=/", "HttpOnly", "SameSite=Lax", f"Max-Age={max_age}"]
        if SECURE_COOKIE:
            parts.append("Secure")
        return ("Set-Cookie", "; ".join(parts))

    def current_user(self):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        try:
            c = cookies.SimpleCookie(raw)
            token = c["sid"].value
        except Exception:
            return None
        th = hashlib.sha256(token.encode()).hexdigest()
        with _db_lock, db() as con:
            row = con.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?",
                              (th, time.time())).fetchone()
        return row

    def new_session(self, con, user_id):
        token = secrets.token_urlsafe(32)
        con.execute("INSERT INTO sessions VALUES(?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time(), time.time() + SESSION_TTL))
        con.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
        return token

    def same_origin(self):
        # защита от CSRF поверх SameSite: если Origin указан, он должен совпадать с Host
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return urlparse(origin).netloc == (self.headers.get("Host") or "")

    # ---------- маршруты ----------
    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self.api("GET", path)
        return self.static(path)

    def do_POST(self):
        self.api("POST", urlparse(self.path).path)

    def do_PUT(self):
        self.api("PUT", urlparse(self.path).path)

    def do_DELETE(self):
        self.api("DELETE", urlparse(self.path).path)

    def static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (DIST / rel).resolve()
        if DIST.resolve() not in target.parents and target != DIST.resolve():
            return self.send_json(404, {"error": "not_found"})
        if not target.is_file():
            return self.send_json(404, {"error": "not_found"})
        st = target.stat()
        etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
        if self.headers.get("If-None-Match") == etag:  # браузер уже держит свежую копию
            self.send_response(304)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        textual = ctype.startswith("text/") or ctype.endswith(("javascript", "json", "svg+xml"))
        data = _file_cache.get((str(target), etag))
        if data is None:
            data = target.read_bytes()
            gz = gzip.compress(data, 6) if textual and len(data) > 1024 else None
            _file_cache.clear() if len(_file_cache) > 64 else None
            _file_cache[(str(target), etag)] = data = (data, gz)
        raw, gz = data
        use_gz = gz is not None and "gzip" in (self.headers.get("Accept-Encoding") or "")
        body = gz if use_gz else raw
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if textual else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", etag)
        # фото именованы по содержимому — кешируем надолго; остальное проверяем по ETag
        self.send_header("Cache-Control", "public, max-age=604800, immutable" if rel.startswith("assets/photos/") else "no-cache")
        if textual:
            self.send_header("Vary", "Accept-Encoding")
        if use_gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def api(self, method, path):
        if method != "GET" and not self.same_origin():
            return self.send_json(403, {"error": "bad_origin"})
        try:
            handler = {
                ("POST", "/api/register"): self.register, ("POST", "/api/login"): self.login, ("POST", "/api/logout"): self.logout,
                ("GET", "/api/me"): self.me, ("PUT", "/api/me"): self.update_me, ("DELETE", "/api/me"): self.delete_me,
                ("PUT", "/api/password"): self.change_password,
                ("GET", "/api/settings"): self.get_settings, ("PUT", "/api/settings"): self.put_settings,
            }.get((method, path))
            if not handler:
                return self.send_json(404, {"error": "not_found"})
            handler()
        except Exception as e:  # не отдаём внутренности наружу
            print("ошибка API:", repr(e))
            self.send_json(500, {"error": "server_error"})

    def need_user(self):
        u = self.current_user()
        if not u:
            self.send_json(401, {"error": "unauthorized"})
        return u

    # ---------- обработчики ----------
    def register(self):
        d = self.read_json()
        if d is None:
            return self.send_json(400, {"error": "bad_request"})
        email = str(d.get("email", "")).strip().lower()
        password = str(d.get("password", ""))
        name = re.sub(r"\s+", " ", str(d.get("name", "")).strip())[:60]
        if not EMAIL_RX.match(email):
            return self.send_json(400, {"error": "bad_email", "message": "Проверьте адрес почты"})
        if len(password) < 8 or len(password) > 128:
            return self.send_json(400, {"error": "bad_password", "message": "Пароль — от 8 до 128 символов"})
        salt = secrets.token_bytes(16)
        pw = hash_pw(password, salt)
        with _db_lock, db() as con:
            if con.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                return self.send_json(409, {"error": "exists", "message": "Эта почта уже зарегистрирована"})
            cur = con.execute("INSERT INTO users(email,name,color,salt,hash,created) VALUES(?,?,?,?,?,?)",
                              (email, name or email.split("@")[0], secrets.choice(sorted(COLORS)), salt, pw, time.time()))
            token = self.new_session(con, cur.lastrowid)
            row = con.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
        self.send_json(201, {"user": public_user(row), "settings": {}}, [self.cookie_header(token, SESSION_TTL)])

    def login(self):
        d = self.read_json()
        if d is None:
            return self.send_json(400, {"error": "bad_request"})
        email = str(d.get("email", "")).strip().lower()
        password = str(d.get("password", ""))
        key = (email, self.ip())
        now = time.time()
        recent = [t for t in _fails.get(key, []) if now - t < 600]
        if len(recent) >= 5:
            return self.send_json(429, {"error": "rate_limited", "message": "Слишком много попыток. Подождите несколько минут"})
        with _db_lock, db() as con:
            row = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            ok = False
            if row:
                ok = hmac.compare_digest(hash_pw(password, row["salt"]), row["hash"])
            else:
                hash_pw(password, b"\x00" * 16)  # выравниваем время ответа
            if not ok:
                _fails[key] = recent + [now]
                return self.send_json(401, {"error": "invalid", "message": "Неверная почта или пароль"})
            _fails.pop(key, None)
            token = self.new_session(con, row["id"])
        self.send_json(200, {"user": public_user(row), "settings": json.loads(row["settings"] or "{}")}, [self.cookie_header(token, SESSION_TTL)])

    def logout(self):
        raw = self.headers.get("Cookie")
        if raw:
            try:
                token = cookies.SimpleCookie(raw)["sid"].value
                with _db_lock, db() as con:
                    con.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
            except Exception:
                pass
        self.send_json(200, {"ok": True}, [self.cookie_header("", 0)])

    def me(self):
        u = self.need_user()
        if u:
            self.send_json(200, {"user": public_user(u), "settings": json.loads(u["settings"] or "{}")})

    def update_me(self):
        u = self.need_user()
        if not u:
            return
        d = self.read_json()
        if d is None:
            return self.send_json(400, {"error": "bad_request"})
        name = re.sub(r"\s+", " ", str(d.get("name", u["name"])).strip())[:60] or u["name"]
        color = d.get("color", u["color"])
        if color not in COLORS:
            return self.send_json(400, {"error": "bad_color"})
        with _db_lock, db() as con:
            con.execute("UPDATE users SET name=?, color=? WHERE id=?", (name, color, u["id"]))
            row = con.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
        self.send_json(200, {"user": public_user(row)})

    def change_password(self):
        u = self.need_user()
        if not u:
            return
        d = self.read_json()
        if d is None:
            return self.send_json(400, {"error": "bad_request"})
        old, new = str(d.get("old", "")), str(d.get("new", ""))
        if not hmac.compare_digest(hash_pw(old, u["salt"]), u["hash"]):
            return self.send_json(403, {"error": "invalid", "message": "Текущий пароль указан неверно"})
        if len(new) < 8 or len(new) > 128:
            return self.send_json(400, {"error": "bad_password", "message": "Новый пароль — от 8 до 128 символов"})
        salt = secrets.token_bytes(16)
        with _db_lock, db() as con:
            con.execute("UPDATE users SET salt=?, hash=? WHERE id=?", (salt, hash_pw(new, salt), u["id"]))
            con.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))  # выходим на всех устройствах
            token = self.new_session(con, u["id"])
        self.send_json(200, {"ok": True}, [self.cookie_header(token, SESSION_TTL)])

    def delete_me(self):
        u = self.need_user()
        if not u:
            return
        d = self.read_json() or {}
        if not hmac.compare_digest(hash_pw(str(d.get("password", "")), u["salt"]), u["hash"]):
            return self.send_json(403, {"error": "invalid", "message": "Неверный пароль"})
        with _db_lock, db() as con:
            con.execute("DELETE FROM users WHERE id=?", (u["id"],))
        self.send_json(200, {"ok": True}, [self.cookie_header("", 0)])

    def get_settings(self):
        u = self.need_user()
        if u:
            self.send_json(200, {"settings": json.loads(u["settings"] or "{}")})

    def put_settings(self):
        u = self.need_user()
        if not u:
            return
        d = self.read_json()
        s = d.get("settings") if d else None
        if not isinstance(s, dict) or len(json.dumps(s)) > 120_000:
            return self.send_json(400, {"error": "bad_request"})
        allowed = {k: s[k] for k in ("A", "rentOv", "excluded", "fav", "compare", "filters", "userFlats", "userPolys") if k in s}
        with _db_lock, db() as con:
            con.execute("UPDATE users SET settings=? WHERE id=?", (json.dumps(allowed, ensure_ascii=False), u["id"]))
        self.send_json(200, {"ok": True})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT") or 4183))
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    init_db()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"Городской компас: http://{a.host}:{a.port}/")
    srv.serve_forever()


if __name__ == "__main__":
    main()
