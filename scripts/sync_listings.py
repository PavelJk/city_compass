#!/usr/bin/env python3
"""Загрузка объявлений о продаже квартир -> dist/data/listings.json.

Источники (только разрешённые, без парсинга сайтов):
  1. файлы CSV/JSON в data/inbox/  (ручная или внешняя выгрузка);
  2. сохранённые HTML-страницы выдачи (Авито, Этажи и др.) в data/inbox/*.html;
  3. архивные датасеты Kaggle (geo_lat/geo_lon/area/rooms/price) — фильтр по bbox;
  4. URL-фиды (CSV/JSON) из scripts/sources.json -> "feeds";
  5. платный API ads-api.ru (ключи в переменных ADS_API_USER / ADS_API_TOKEN).
Геокодирование адресов: Nominatim (OSM), кеш в data/geocode-cache.json.
Нас. пункты: Йошкар-Ола, Медведево, Семёновка, Руэм.
"""
import csv, html, json, os, re, shutil, sys, time, zlib, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "data" / "inbox"
CACHE = ROOT / "data" / "geocode-cache.json"
OUT = ROOT / "dist" / "data" / "listings.json"
PHOTOS = ROOT / "dist" / "assets" / "photos"
CFG = ROOT / "scripts" / "sources.json"
UA = "invest-karta-student-project/1.0"

PLACES = {  # название -> (регэксп, центр, радиус допустимого отклонения, градусы)
    "Йошкар-Ола": (r"йошкар", (56.6388, 47.8908), 0.12),
    "Медведево": (r"медведев", (56.6350, 47.8170), 0.06),
    "Семёновка": (r"сем[её]новк", (56.6552, 47.9771), 0.05),
    "Руэм": (r"руэм", (56.6310, 47.7560), 0.05),
}
VIEWBOX = "47.60,56.80,48.10,56.50"  # lon_left,lat_top,lon_right,lat_bottom

COLS = {  # синонимы колонок -> поле
    "address": ["адрес", "address"], "area": ["площадь", "area"],
    "rooms": ["комнаты", "rooms"], "price": ["цена", "price"],
    "rent": ["аренда", "rent"], "url": ["ссылка", "url", "link"],
    "name": ["название", "name", "title"], "source": ["источник", "source"],
    "market": ["рынок", "market"], "complex": ["complex", "жк"], "image_local": ["image_local"], "image_remote": ["image_remote"], "item_id": ["item_id"],
    "lat": ["lat", "широта", "geo_lat"], "lng": ["lng", "lon", "долгота", "geo_lon"],
}


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def num(v):
    if v in (None, ""):
        return None
    s = re.sub(r"[^\d,.]", "", str(v)).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def normalize(row):
    low = {str(k).strip().lower(): v for k, v in row.items()}
    out = {}
    for f, names in COLS.items():
        for n in names:
            if low.get(n) not in (None, ""):
                out[f] = low[n]
                break
    return out


def read_file(path):
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, list) else data.get("listings", [])
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(bbox_filter(csv.DictReader(f)))


def bbox_filter(reader):
    """Большие датасеты (Kaggle): держим в памяти только строки внутри нашей области."""
    for row in reader:
        lat, lng = num(row.get("geo_lat")), num(row.get("geo_lon"))
        if lat is None and lng is None and "geo_lat" not in row:
            yield row
        elif lat and lng and 56.50 <= lat <= 56.80 and 47.60 <= lng <= 48.10:
            yield row


def fetch_feed(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8-sig")
    if url.lower().split("?")[0].endswith(".json") or raw.lstrip().startswith(("[", "{")):
        data = json.loads(raw)
        return data if isinstance(data, list) else data.get("listings", [])
    return list(csv.DictReader(raw.splitlines()))


def best_srcset(tag):
    """Самая крупная ссылка из srcset (элементы вида «url 318w»)."""
    m = re.search(r'srcset="([^"]+)"', tag)
    if not m:
        return ""
    best, bw = "", -1
    for part in html.unescape(m.group(1)).split(","):
        bits = part.strip().split()
        if bits and bits[0].startswith("http"):
            w = int(re.sub(r"\D", "", bits[1]) or 0) if len(bits) > 1 else 0
            if w > bw:
                best, bw = bits[0], w
    return best


def pick_imgs(blk, title, addr, itemprop=False):
    """Все <img> карточки, чей alt соответствует объявлению (слайды галереи); рекламные и чужие картинки отбрасываем."""
    head = html.unescape(title or "").replace("\xa0", " ").strip()
    area = (re.search(r"\d+(?:[.,]\d+)?\s*м²", head) or [""])[0].replace(" ", "")
    tail = (addr or "").split(",")[-1].strip().lower()
    out = []
    for m in re.finditer(r"<img[^>]*>", blk):
        tag = m.group()
        if itemprop and 'itemprop="image"' not in tag:
            continue
        alt = html.unescape((re.search(r'alt="([^"]*)"', tag) or [0, ""])[1]).replace("\xa0", " ")
        alt_n = alt.replace(" ", "").lower()
        if (area and area.lower() in alt_n) or (head[:12] and head[:12].lower() in alt.lower()) or (len(tail) > 4 and tail in alt.lower()):
            out.append(tag)
    return out


def img_pair(tag, path):
    """(локальный файл из сохранённой страницы, крупная ссылка) для одного <img>."""
    m1 = re.search(r' src="([^"]+)"', tag)
    src = html.unescape(m1.group(1)) if m1 else ""
    local = "" if src.startswith("http") or not src else str(path.parent / (path.stem + "_files") / Path(src).name.replace("\xa0", " "))
    remote = best_srcset(tag) or (src if src.startswith("http") else "")
    return local, remote


def pick_img(blk, title, addr, itemprop=False):
    """Первая <img> карточки, чей alt соответствует объявлению (заголовок/площадь или адрес). Рекламные и чужие картинки отбрасываем."""
    head = html.unescape(title or "").replace(" ", " ").strip()
    area = (re.search(r"\d+(?:[.,]\d+)?\s*м²", head) or [""])[0].replace(" ", "")
    tail = (addr or "").split(",")[-1].strip().lower()
    for m in re.finditer(r"<img[^>]*>", blk):
        tag = m.group()
        if itemprop and 'itemprop="image"' not in tag:
            continue
        alt = html.unescape((re.search(r'alt="([^"]*)"', tag) or [0, ""])[1]).replace(" ", " ")
        alt_n = alt.replace(" ", "").lower()
        if (area and area.lower() in alt_n) or (head[:12] and head[:12].lower() in alt.lower()) or (len(tail) > 4 and tail in alt.lower()):
            return tag
    return None


def read_html(path):
    """Сохранённая страница выдачи (Ctrl+S): карточки Авито/Этажей + JSON-LD."""
    t = path.read_text(encoding="utf-8", errors="ignore")
    rows = []
    ttl = (re.search(r"<title>(.*?)</title>", t, re.S) or [None, ""])[1]
    tt = html.unescape(ttl)
    page_market = "new" if re.search(r"новостро", tt, re.I) else "secondary" if re.search(r"вторичк", tt, re.I) else None
    # фото из JSON-LD страницы (есть даже у карточек, где картинка в разметке не подгружена): id объявления -> ссылка
    ld_img = {}
    for m in re.finditer(r'\{"@type":"Offer",[^{}]*?"url":"[^"]*?_(\d+)"[^{}]*?"image":"([^"]+)"', t):
        ld_img.setdefault(m.group(1), html.unescape(m.group(2)).replace("\u0026", "&"))
    # галерея из встроенного состояния страницы: "<id объявления>":{"type":"item","value":{...,"urls":{"933x699":"https://…"}}}
    t2 = t.replace('\\"', '"')
    marks = [(m.start(), m.end(), m.group(1)) for m in re.finditer(r'"(\d{7,12})":\{"type":"item","value":\{', t2)]
    for i, (st, en, iid) in enumerate(marks):
        seg = t2[en:(marks[i + 1][0] if i + 1 < len(marks) else en + 60000)]
        u = re.search(r'"urls":\{([^{}]*)\}', seg)
        if u:
            sizes = re.findall(r'"(\d+)x\d+":"(https?://[^"]+)"', u.group(1))
            if sizes:
                ld_img[iid] = html.unescape(max(sizes, key=lambda x: int(x[0]))[1])
    new_rx = re.compile(r"item-development-name|от застройщика", re.I)
    for m in re.finditer(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', t, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        for o in (d if isinstance(d, list) else [d]):
            for el in (o.get("itemListElement") or [o]):
                it = el.get("item", el) if isinstance(el, dict) else {}
                offer = it.get("offers") or {}
                if isinstance(offer, list):
                    offer = offer[0] if offer else {}
                if it.get("name") and offer.get("price"):
                    addr = it.get("address") or offer.get("availableAtOrFrom") or {}
                    addr = addr.get("streetAddress") if isinstance(addr, dict) else addr
                    rows.append({"name": it["name"], "price": offer["price"],
                                 "address": addr or "", "url": it.get("url", "")})
    for blk in re.split(r'data-marker="item"', t)[1:]:
        g = lambda rx: (re.search(rx, blk, re.S) or [None, ""])[1]
        clean = lambda x: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()
        mt = re.search(r'data-marker="item-title"[^>]*href="([^"?]+)[^"]*"[^>]*>(.*?)</a>', blk, re.S)
        if not mt:
            continue
        price = g(r'itemprop="price"[^>]*content="(\d+)"') or g(r'content="(\d+)"[^>]*itemprop="price"')
        loc = g(r'data-marker="item-location"(.*?)(?:data-marker="rating-row"|</p>)')
        addr = clean(loc).split("·")[0].lstrip("> ").strip()
        city = "Йошкар-Ола" if "/yoshkar-ola/" in mt.group(1) else ""
        imgs = [img_pair(t_, path) for t_ in pick_imgs(blk, clean(mt.group(2)), addr, itemprop=True)]
        local, remote = imgs[0] if imgs else ("", "")
        if price and addr:
            rows.append({"images": imgs, "name": clean(mt.group(2)), "price": price,
                         "address": (city + ", " + addr) if city else addr,
                         "url": mt.group(1), "image_local": local, "image_remote": remote,
                         "source": "Авито", "item_id": g(r'data-item-id="(\d+)"') or "",
                         "market": page_market or ("new" if new_rx.search(blk) else "secondary")})
    # мобильная вёрстка Авито (m.avito.ru / веб-архив из Safari): data-marker="item/link"
    for blk in re.split(r'data-marker="item/link"', t)[1:]:
        g = lambda rx: (re.search(rx, blk, re.S) or [None, ""])[1]
        clean = lambda x: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()
        href = g(r'^[^>]*?href="(/[^"?]+)')
        title = clean(g(r'data-marker="titleLabelRich"[^>]*>(.*?)</div>'))
        price = re.sub(r"\D", "", clean(g(r'data-marker="priceLabelRich"[^>]*><span[^>]*>(.*?)</span>')))
        place = clean(g(r'data-marker="geoReferenceLeftLabel"[^>]*>(.*?)</div>'))
        dev = clean(g(r'data-marker="developmentViewLink"[^>]*><a[^>]*>(.*?)</a>'))
        street = clean(g(r'data-marker="addressLabel"[^>]*>(.*?)</div>')) or dev
        complex_ = dev if re.match(r"(ЖК|Премьер|Квартал|Микрорайон|Дом)", dev) else ""
        if not (href and price and title):
            continue
        imgs = [img_pair(t_, path) for t_ in pick_imgs(blk, title, ", ".join(x for x in (place, street) if x))]
        local, remote = imgs[0] if imgs else ("", "")
        rows.append({"images": imgs, "name": title, "price": price, "address": ", ".join(x for x in (place, street) if x),
                     "url": "https://www.avito.ru" + href, "image_local": local, "image_remote": remote, "complex": complex_,
                     "source": "Авито", "item_id": (re.search(r"_(\d+)$", href) or [None, ""])[1],
                     "market": page_market or ("new" if new_rx.search(blk) else "secondary")})
    for r in rows:
        if not (r.get("image_local") or r.get("image_remote")) and ld_img.get(r.get("item_id")):
            r["image_remote"] = ld_img[r["item_id"]]
            r["images"] = [("", ld_img[r["item_id"]])]
    return rows


def parse_title(title):
    """«2-к. квартира, 54 м², 3/9 эт.» -> (комнаты, площадь)."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*м", title or "")
    r = re.search(r"(\d+)-к|студия", (title or "").lower())
    return (r.group(0) if r else None), (m.group(1) if m else None)


def fetch_ads_api():
    user, token = os.environ.get("ADS_API_USER"), os.environ.get("ADS_API_TOKEN")
    if not (user and token):
        return []
    rows = []
    for city in ["Йошкар-Ола", "Медведево", "Семёновка", "Руэм"]:
        q = urllib.parse.urlencode({"user": user, "token": token, "category_id": 2,
                                    "city": "Марий Эл " + city, "nedvigimost_type": 1, "limit": 500})
        try:
            data = json.loads(urllib.request.urlopen(urllib.request.Request(
                "https://ads-api.ru/main/api?" + q, headers={"User-Agent": UA}), timeout=60).read())
        except Exception as e:
            log("ads-api:", city, e)
            time.sleep(5)
            continue
        for a in (data.get("data") if isinstance(data, dict) else data) or []:
            if a.get("nedvigimost_type_id") not in (None, 1):
                continue
            rooms, area = parse_title(a.get("title"))
            c = a.get("coords") or {}
            rows.append({"name": a.get("title"), "address": a.get("address") or city,
                         "price": a.get("price"), "rooms": rooms, "area": area,
                         "url": a.get("url"), "source": a.get("source"),
                         "lat": c.get("lat"), "lng": c.get("lng")})
        time.sleep(5)  # лимит API: 1 запрос / 5 с
    log(f"ads-api.ru: {len(rows)} строк")
    return rows


def nearest_locality(lat, lng):
    best = min(PLACES, key=lambda n: (lat - PLACES[n][1][0]) ** 2 + (lng - PLACES[n][1][1]) ** 2)
    c, tol = PLACES[best][1], PLACES[best][2]
    return best if abs(lat - c[0]) <= tol and abs(lng - c[1]) <= tol * 1.7 else None


def locality(address):
    for name in ("Семёновка", "Руэм", "Медведево", "Йошкар-Ола"):  # посёлки раньше города
        if re.search(PLACES[name][0], address, re.I):
            return name
    return None


def load_cache():
    try:
        return {k: v for k, v in json.loads(CACHE.read_text(encoding="utf-8")).items() if v}
    except Exception:
        return {}


_last = [0.0]


def query_variants(address):
    q = re.sub(r"\s+,", ",", address)
    q = re.sub(r"(?i)ул\.?\s", "улица ", q)
    q = re.sub(r"(?i)пер\.?\s", "переулок ", q)
    q = re.sub(r"(?i)(пос|мкр|с|п)\.\s*", "", q)
    q = re.sub(r"(?i)(,\s*)?(д|стр|поз)\.\s*", ", ", q)
    q = re.sub(r"(?i),\s*жилой дом", "", q)
    q = re.sub(r"(?i)тракт\s+(\w+?)ий", r"ий тракт", q)
    village = re.search(r"(?i)(сем[её]новк\w*|руэм|медведев\w*)", q)
    if village:  # на Авито посёлки идут с префиксом «Йошкар-Ола» — иначе найдётся одноимённая улица в городе
        name = ("Семёновка" if re.match(r"(?i)сем", village.group(1)) else
                "Руэм" if re.match(r"(?i)руэм", village.group(1)) else "Медведево")
        street = [x.strip() for x in q.split(",") if re.search(r"(?i)улица|ул\.|переулок|пер\.|проспект|ул", x)]
        st = re.sub(r"(?i)(улица|ул\.?)", "", street[0]).strip() if street else ""
        if st:
            yield f"улица {st}, {name}"
        return
    yield q
    parts = [x.strip() for x in q.split(",") if x.strip()]
    if len(parts) > 2:  # без номера дома: «город, улица»
        yield ", ".join(parts[:1] + parts[-2:-1]) if len(parts) > 3 else ", ".join(parts[:-1])


def geocode(address, cache):
    if address in cache:
        return cache[address]
    for q in query_variants(address):
        wait = 1.1 - (time.time() - _last[0])  # политика Nominatim: <= 1 запрос/с
        if wait > 0:
            time.sleep(wait)
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
            {"q": q, "format": "jsonv2", "limit": 1, "viewbox": VIEWBOX, "bounded": 1, "countrycodes": "ru"})
        try:
            res = json.loads(urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept-Language": "ru"}), timeout=30).read())
        except Exception as e:
            log("геокодер недоступен:", e)
            return None  # не кешируем сбой
        _last[0] = time.time()
        if res:
            cache[address] = [float(res[0]["lat"]), float(res[0]["lon"])]
            return cache[address]
    cache[address] = None
    return None


def download_photo(url, key):
    fn = re.sub(r"\W", "", str(key))[:40] + ".jpg"
    dst = PHOTOS / fn
    if not dst.exists():
        try:
            data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read()
            if len(data) < 1500:
                return None
            PHOTOS.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            time.sleep(0.3)
        except Exception as e:
            log("фото не скачалось:", url[:60], e)
            return None
    return "assets/photos/" + fn


def housekeeping_photos(items):
    """Уменьшенные копии для списка (t/…, 240 px) и удаление фото, на которые больше нет ссылок."""
    used = {Path(p).name for it in items for p in (it.get("photos") or []) + [it.get("photo") or ""] if p}
    thumbs = PHOTOS / "t"
    try:
        from PIL import Image
    except ImportError:
        Image = None
        log("Pillow не установлен — уменьшенные копии не создаются (pip install pillow)")
    if Image:
        thumbs.mkdir(parents=True, exist_ok=True)
        for name in used:
            src, dst = PHOTOS / name, thumbs / name
            if src.is_file() and (not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime):
                try:
                    with Image.open(src) as im:
                        im = im.convert("RGB")
                        im.thumbnail((240, 240))
                        im.save(dst, "JPEG", quality=80, optimize=True, progressive=True)
                except Exception as e:
                    log("миниатюра не создана:", name, e)
    for folder in (PHOTOS, thumbs):  # лишние файлы, которых нет в базе
        if folder.is_dir():
            for f in folder.iterdir():
                if f.is_file() and f.name not in used:
                    f.unlink()


def normalize_market(v):
    s = str(v or "").strip().lower()
    return "new" if re.search(r"нов|new|застройщик", s) else "secondary"


def rooms_label(v):
    s = str(v or "").lower()
    if "студ" in s:
        return "Студия"
    m = re.search(r"\d+", s)
    return f"{m.group()}-комн." if m else "—"


def main():
    rows = []
    for p in sorted(INBOX.glob("*")):
        if p.suffix.lower() in (".csv", ".json", ".html", ".htm"):
            try:
                r = read_html(p) if p.suffix.lower() in (".html", ".htm") else read_file(p)
                log(f"{p.name}: {len(r)} строк")
                rows += [(x, p.stem) for x in r]
            except Exception as e:
                log("ошибка чтения", p.name, e)
    rows += [(x, "ads-api.ru") for x in fetch_ads_api()]
    new_urls = {str(x.get("url", "")).split("?")[0] for x, st in rows if st.startswith("avito-new") and x.get("url")}
    if new_urls:  # есть страницы новостроек: прежние новостройки удаляем, остальные дубли берём из «чистой» выдачи
        before = len(rows)
        rows = [(x, st) for x, st in rows if st.startswith("avito-new") or not st.startswith("avito")
                or (normalize_market(x.get("market")) != "new" and str(x.get("url", "")).split("?")[0] not in new_urls)]
        log(f"новостройки заменены: убрано {before - len(rows) + sum(1 for _, st in rows if st.startswith('avito-new'))} старых строк")
    if CFG.exists():
        for feed in json.loads(CFG.read_text(encoding="utf-8")).get("feeds", []):
            try:
                r = fetch_feed(feed["url"])
                log(f"{feed.get('name', feed['url'])}: {len(r)} строк")
                rows += [(x, feed.get("name", "feed")) for x in r]
            except Exception as e:
                log("ошибка фида", feed.get("url"), e)

    cache, seen, items, skipped = load_cache(), set(), [], 0
    seen_urls = set()
    for raw, src in rows:
        r = normalize(raw)
        r["images"] = raw.get("images") if isinstance(raw, dict) else None
        addr, price, area = str(r.get("address", "")).strip(), num(r.get("price")), num(r.get("area"))
        if not area:  # площадь/комнаты могут быть только в заголовке
            rm, ar = parse_title(r.get("name"))
            area, r["rooms"] = num(ar), r.get("rooms") or rm
        approx = False
        lat, lng = num(r.get("lat")), num(r.get("lng"))
        loc = locality(addr) or (nearest_locality(lat, lng) if lat and lng else None)
        if price and area and not (300_000 <= price and 20_000 <= price / area <= 500_000):
            skipped += 1  # нереальная цена (аренда, опечатка, «цена за м²» вместо цены) — не берём
            continue
        if not (price and area and loc and (addr or (lat and lng))):
            skipped += 1
            continue
        if not addr:
            addr = f"{loc} (по координатам)"
        ukey = str(r.get("url") or "").split("?")[0]
        if ukey and ukey in seen_urls:  # то же объявление с мобильной и обычной версии сайта (адрес отличается пробелом)
            continue
        if ukey:
            seen_urls.add(ukey)
        key = (addr.lower(), area, price, lat, lng)
        if key in seen:
            continue
        seen.add(key)
        if not (lat and lng):
            pt = geocode(addr, cache)
            if not pt and loc != "Йошкар-Ола":  # посёлок: улицы нет в OSM — ставим в центр с разбросом
                h = zlib.crc32(addr.encode()) % 10000
                c0 = PLACES[loc][1]
                pt = [c0[0] + ((h % 100) - 50) * 0.00005, c0[1] + ((h // 100) - 50) * 0.0001]
                approx = True
            if not pt:
                skipped += 1
                continue
            lat, lng = pt
        c, tol = PLACES[loc][1], PLACES[loc][2]
        if abs(lat - c[0]) > tol or abs(lng - c[1]) > tol * 1.7:
            skipped += 1  # геокодер промахнулся мимо нас. пункта
            continue
        rent = num(r.get("rent"))
        pics, seen_p = [], set()
        for lp, rm in (r.get("images") or [(r.get("image_local"), r.get("image_remote"))]):
            got = None
            if rm and rm.startswith("https://avatars.mds.yandex.net/"):  # Яндекс: не скачиваем, показываем по ссылке
                got = rm
            elif rm and rm.startswith("http") and "img.avito.st" in rm:  # крупная версия
                got = download_photo(rm, (r.get("item_id") or "x") + "_" + format(zlib.crc32(rm.encode()), "x"))
            if not got and lp and Path(lp).is_file():  # запасной вариант — файл из сохранённой страницы
                PHOTOS.mkdir(parents=True, exist_ok=True)
                fn = (r.get("item_id") or "x") + "_" + format(zlib.crc32(Path(lp).name.encode()), "x") + ".jpg"
                shutil.copyfile(lp, PHOTOS / fn)
                got = "assets/photos/" + fn
            if got and got not in seen_p:
                seen_p.add(got); pics.append(got)
            if len(pics) >= 8:
                break
        photo = pics[0] if pics else ""
        items.append({
            "name": r.get("name") or addr, "address": addr, "locality": loc,
            "area": area, "rooms": rooms_label(r.get("rooms")) if r.get("rooms") not in (-1, "-1") else "Студия", "price": int(price),
            "rent": int(rent) if rent else int(price * 0.0065),
            "rentEstimated": not rent, "approx": approx, "complex": str(r.get("complex") or ""), "market": normalize_market(r.get("market")), "lat": round(lat, 6), "lng": round(lng, 6),
            "url": r.get("url") or "", "photo": photo, "photos": pics, "source": r.get("source") or src,
        })
    # дубли между сайтами: тот же дом, площадь и цена в пределах 3%
    def addr_key(a):
        a = re.sub(r"\b(ул|улица|д|стр|поз|пос|с|пгт|мкр|микрорайон|бульвар|б-р|проспект|пр|переулок|пер|тракт)\b\.?", " ", a.lower().replace("ё", "е"))
        return re.sub(r"[^а-я0-9/]+", " ", a).strip()
    kept, idx = [], {}
    for it in items:
        k = addr_key(it["address"])
        dup = any(abs(o["area"] - it["area"]) < 0.3 and abs(o["price"] - it["price"]) <= 0.03 * o["price"] for o in idx.get(k, []))
        if dup:
            continue
        idx.setdefault(k, []).append(it); kept.append(it)
    if len(kept) != len(items):
        log(f"дублей между сайтами убрано: {len(items) - len(kept)}")
    items = kept
    # у кого нет своего фото — берём фото другой квартиры из того же ЖК или того же дома (помечаем photoShared)
    def group_key(it):
        if it.get("complex"):
            return "c:" + it["complex"].lower()
        m = re.search(r"([а-яё.\- ]+?)[, ]+(?:д\.?\s*)?(\d+[а-яa-z/]*)\s*$", it["address"].lower())
        return "a:" + (it["address"].lower() if not m else it["address"].lower())
    donors = {}
    for it in items:
        if it["photo"] and not it.get("photoShared"):
            donors.setdefault(group_key(it), it["photo"])
    for it in items:
        if not it["photo"] and group_key(it) in donors:
            it["photo"], it["photoShared"] = donors[group_key(it)], True
            it["photos"] = [it["photo"]]
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    if not items:
        log(f"нет валидных объявлений (пропущено {skipped}) — listings.json не тронут")
        return 1
    housekeeping_photos(items)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "count": len(items), "listings": items}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(OUT)
    log(f"записано {len(items)} объявлений, пропущено {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
