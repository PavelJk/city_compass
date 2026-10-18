"""
Модуль «Инвестиционная привлекательность жилья» для «Цифрового двойника инфраструктуры».
Тема: геоинформационная система оценки инвестиционной привлекательности жилой недвижимости
на основе цен продажи и аренды (Йошкар-Ола, Медведево, Семёновка, Руэм).

Что делает модуль
  * берёт из базы проекта дорожный граф (nodes/edges), здания (buildings), светофоры, переходы и остановки;
  * привязывает объявления о продаже квартир к зданиям проекта;
  * считает пешую доступность инфраструктуры (магазины, школы, сады, парки, транспорт, минусы: промзоны,
    магистрали, бары…) по дорожному графу проекта, затем индекс среды 0–100;
  * считает экономику аренды: оценку аренды, чистую доходность, окупаемость и итоговый индекс выгодности;
  * выводит карту (здания проекта, раскрашенные по выгодности) и рейтинг квартир;
  * записывает результаты в общие таблицы проекта characteristics/data (для зданий), чтобы их видели другие модули.

Установка: положить файл в modules/, «Модули → Управление модулями» → активировать, перезапустить приложение.
Модуль один файл, свои таблицы начинаются с realty_, настройки — в таблице settings с ключом realty_*.
Данные (объявления и ~9,6 тыс. мест из OpenStreetMap) встроены в файл и при первом запуске загружаются в базу.
"""
import base64
import heapq
import json
import math
import sqlite3
import threading
import time
import traceback
import zlib

MODULE_INFO = {
    'name': 'realty_module',
    'description': 'Инвестиционная привлекательность жилья: цены продажи и аренды, индекс среды по дорожному графу',
    'version': '1.0',
}

MENU = {'url': '/modules/realty', 'title': 'Инвестиционная привлекательность жилья'}

K = 111320.0           # метров в градусе широты
ROUTE_MAX = 2200       # дальше этого радиуса места считаются по прямой
NEAR_R = 1500          # радиус «соседей» для сравнения цены за м²

# категории мест: label, group, kind, R (радиус влияния, м), opt (оптимальная дистанция, м), sev (тяжесть минуса)
CATS = __CATS__
GROUPS = {
    'transport': ('Транспорт', 20), 'education': ('Школы и сады', 15), 'health': ('Медицина', 10),
    'shops': ('Магазины и услуги', 10), 'green': ('Парки и зелень', 15), 'leisure': ('Спорт и культура', 10),
    'public': ('Общественные сервисы', 10),
}

DEFAULTS = {
    'rentBase': {'studio': 20000, 'r1': 23500, 'r2': 27000, 'r3': 32000},   # типичная аренда по комнатности, ₽/мес
    'rentMin': 20000, 'rentMax': 35000, 'nbEffect': 0.35,
    'envEffect': 12,
    'localityK': {'Йошкар-Ола': 1.0, 'Медведево': 0.85, 'Семёновка': 0.8, 'Руэм': 0.75},
    'marketK': {'new': 1.08, 'secondary': 1.0},
    'edgeFloorK': 0.95,
    'vacancyMonths': 1, 'maintPct': 5, 'mgmtPct': 0, 'taxMode': 'ndfl13', 'propTaxPct': 0.1,
    'repairPerM2': 8000, 'buyCostPct': 1,
    'scoreW': {'yield': 70, 'env': 15, 'price': 15}, 'yieldMin': 2, 'yieldMax': 6,
    # цель и перепродажа: rent — сдавать, resale — перепродать, mix — сдавать, а потом продать
    'goal': 'rent', 'horizon': 5, 'priceGrowth': 5, 'growthEnv': 1.5, 'growthNew': 1,
    'growthLoc': {'Йошкар-Ола': 0, 'Медведево': -0.5, 'Семёновка': -1, 'Руэм': -1.5},
    'catchUp': 0.5, 'sellCostPct': 1.5, 'saleTax': 'auto',
    'retRange': {'resale': [0, 10], 'mix': [3, 12]},     # годовая доходность, %: 0 баллов -> максимум баллов
    'walkMode': 'graph',                       # graph — по дорожному графу проекта, straight — по прямой
}

CHAR_NAMES = {   # характеристики, которые модуль создаёт в общей таблице characteristics (для зданий)
    'env': 'Индекс среды (0–100)', 'ppm': 'Цена, ₽/м²', 'yield': 'Чистая доходность, %', 'score': 'Индекс выгодности (0–100)',
}

# ---------------------------------------------------------------------------
#  Встроенные данные (zlib + base64): объявления и места OpenStreetMap
# ---------------------------------------------------------------------------
_SEED = __SEED__

_JOB = {'running': False, 'progress': 0, 'total': 0, 'message': '', 'error': None, 'finished_at': None, 'log': []}
_LOCK = threading.Lock()
_GRAPH_CACHE = {}


def _log(msg):
    with _LOCK:
        _JOB['log'].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        _JOB['log'] = _JOB['log'][-300:]
    try:
        print(f'[realty] {msg}', flush=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  База данных
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS realty_flat (
    id TEXT PRIMARY KEY, address TEXT, locality TEXT, market TEXT, rooms TEXT, area REAL, floor INTEGER, floors INTEGER,
    price REAL, rent REAL, lat REAL, lon REAL, url TEXT, source TEXT, building_id INTEGER
);
CREATE TABLE IF NOT EXISTS realty_poi (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cat TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, name TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS realty_result (
    flat_id TEXT PRIMARY KEY, building_id INTEGER, env INTEGER, rent REAL, rent_kind TEXT, gross REAL, net_yield REAL,
    payback REAL, ppm REAL, disc REAL, score INTEGER, verdict TEXT, walk15 INTEGER, stops_800 INTEGER,
    crossings_300 INTEGER, lights_300 INTEGER, reasons TEXT, updated TEXT, near TEXT, parts TEXT, resale TEXT
);
"""


def _ensure(db):
    db.executescript(SCHEMA)
    have = {r[1] for r in db.execute('PRAGMA table_info(realty_result)')}
    for col in ('near', 'parts', 'resale'):          # база, созданная прошлой версией модуля
        if col not in have:
            db.execute(f'ALTER TABLE realty_result ADD COLUMN {col} TEXT')
    if db.execute('SELECT COUNT(*) FROM realty_flat').fetchone()[0] == 0:
        _seed(db)
    db.commit()


def _seed(db):
    data = json.loads(zlib.decompress(base64.b64decode(''.join(_SEED))).decode('utf-8'))
    _load_flats(db, data['flats'])
    db.execute('DELETE FROM realty_poi')
    db.executemany('INSERT INTO realty_poi(cat,lat,lon,name) VALUES(?,?,?,?)', data['poi'])
    db.commit()


def _load_flats(db, flats):
    db.execute('DELETE FROM realty_flat')
    db.execute('DELETE FROM realty_result')
    rows = []
    for f in flats:
        try:
            rows.append((str(f.get('id') or f.get('url') or f'{f["address"]}|{f["area"]}|{f["price"]}'), f.get('address', ''),
                         f.get('locality', 'Йошкар-Ола'), 'new' if f.get('market') == 'new' else 'secondary', str(f.get('rooms', '')),
                         float(f['area']), f.get('floor'), f.get('floors'), float(f['price']), f.get('rent') or None,
                         float(f['lat']), float(f['lon'] if 'lon' in f else f['lng']), f.get('url', ''), f.get('source', ''), None))
        except (KeyError, TypeError, ValueError):
            continue
    db.executemany('INSERT OR REPLACE INTO realty_flat VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
    return len(rows)


def _settings(db, get_setting):
    raw = get_setting(db, 'realty_settings', '')
    out = json.loads(json.dumps(DEFAULTS))
    try:
        saved = json.loads(raw) if raw else {}
    except ValueError:
        saved = {}
    for k, v in saved.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        elif k in out:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
#  Дорожный граф проекта (таблицы nodes / edges)
# ---------------------------------------------------------------------------
class Graph:
    def __init__(self, db):
        rows = db.execute('SELECT id, lat, lon, type_id FROM nodes').fetchall()
        self.idx = {r[0]: i for i, r in enumerate(rows)}
        self.lat = [r[1] for r in rows]
        self.lon = [r[2] for r in rows]
        self.type = [r[3] for r in rows]
        self.adj = [[] for _ in rows]
        kx = K * math.cos(math.radians(56.64))
        for a, b in db.execute('SELECT from_node, to_node FROM edges'):
            i, j = self.idx.get(a), self.idx.get(b)
            if i is None or j is None or i == j:
                continue
            d = math.hypot((self.lat[i] - self.lat[j]) * K, (self.lon[i] - self.lon[j]) * kx)
            self.adj[i].append((j, d)); self.adj[j].append((i, d))
        self.cell = 150.0
        self.grid = {}
        for i in range(len(rows)):
            if self.adj[i]:
                self.grid.setdefault(self._key(self.lat[i], self.lon[i]), []).append(i)

    def _key(self, lat, lon):
        return (int((lat - 56.0) * K / self.cell), int((lon - 47.0) * K * 0.55 / self.cell))

    def nearest(self, lat, lon, limit=600):
        gx, gy = self._key(lat, lon)
        best, bd = None, 1e18
        kx = K * math.cos(math.radians(lat))
        for r in range(0, int(limit / self.cell) + 2):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    for i in self.grid.get((gx + dx, gy + dy), ()):
                        d = (self.lat[i] - lat) ** 2 * K * K + (self.lon[i] - lon) ** 2 * kx * kx
                        if d < bd:
                            bd, best = d, i
            if best is not None and math.sqrt(bd) <= r * self.cell:
                break
        return (best, math.sqrt(bd)) if best is not None and math.sqrt(bd) <= limit else (None, 0)

    def dijkstra(self, src, cutoff):
        dist = {src: 0.0}
        heap = [(0.0, src)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist.get(u, 1e18):
                continue
            for v, w in self.adj[u]:
                nd = d + w
                if nd <= cutoff and nd < dist.get(v, 1e18):
                    dist[v] = nd
                    heapq.heappush(heap, (nd, v))
        return dist


def _get_graph(db):
    n = db.execute('SELECT COUNT(*) FROM edges').fetchone()[0]
    key = (n, db.execute('SELECT COUNT(*) FROM nodes').fetchone()[0])
    if _GRAPH_CACHE.get('key') != key:
        _log(f'строю граф: {key[1]} узлов, {key[0]} рёбер')
        _GRAPH_CACHE['g'] = Graph(db)
        _GRAPH_CACHE['key'] = key
    return _GRAPH_CACHE['g']


# ---------------------------------------------------------------------------
#  Индекс среды
# ---------------------------------------------------------------------------
W_POS = [1, 0.5, 0.3, 0.2]
W_NEG = [1, 0.4, 0.2]


def _pos_factor(d, R, opt):
    if d > R:
        return 0.0
    if opt and d < opt:
        return 0.55 + 0.45 * d / opt
    t = (d - opt) / (R - opt)
    return (1 - t) ** 1.5


def evaluate(lat, lon, pois, walk):
    """pois: [(cat, lat, lon, name)]; walk: {cat: [расстояния по графу…]}, {cat: имя ближайшего} или None."""
    pos, neg, near = {}, {}, {}
    any_ = False
    kx = K * math.cos(math.radians(lat))
    routed = set(walk[0]) if walk else set()
    for cat, la, lo, name in pois:
        c = CATS.get(cat)
        if c is None or (c['kind'] == 'pos' and c['R'] <= ROUTE_MAX and walk is not None):
            continue
        dy = (lat - la) * K
        if dy > c['R'] or dy < -c['R']:
            continue
        d = math.hypot(dy, (lon - lo) * kx)
        if d > c['R']:
            continue
        any_ = True
        f = _pos_factor(d, c['R'], c['opt']) if c['kind'] == 'pos' else (1 - d / c['R']) ** 2
        (pos.setdefault(c['group'], []) if c['kind'] == 'pos' else neg.setdefault(cat, [])).append(f)
        if cat not in near or d < near[cat][0]:
            near[cat] = (d, name)
    if walk:
        for cat in routed:
            c = CATS[cat]
            for d in walk[0][cat]:
                any_ = True
                pos.setdefault(c['group'], []).append(_pos_factor(d, c['R'], c['opt']))
            near[cat] = (walk[0][cat][0], walk[1].get(cat, ''))
    if not any_:
        return None, near
    wsum = sum(w for _, w in GROUPS.values())
    pos_total = 0.0
    for g, (_, w) in GROUPS.items():
        a = sorted(pos.get(g, []), reverse=True)[:4]
        s = sum(f * W_POS[i] for i, f in enumerate(a))
        pos_total += w * 100 / wsum * (1 - math.exp(-1.2 * s))
    neg_total = 0.0
    for cat, fs in neg.items():
        a = sorted(fs, reverse=True)[:3]
        neg_total += CATS[cat]['sev'] * sum(f * W_NEG[i] for i, f in enumerate(a))
    score = max(5, min(95, 40 + 0.65 * pos_total - min(55, 2.5 * neg_total)))
    return int(round(score)), near


WALK15 = [
    ('Магазин', ('grocery', 'supermarket', 'shop_other', 'bakery')), ('Остановка', ('transport', 'tram')), ('Школа', ('school',)),
    ('Детский сад', ('kindergarten',)), ('Аптека или поликлиника', ('pharmacy', 'clinic')),
    ('Парк или сквер', ('park', 'square', 'forest')), ('Кафе', ('cafe',)), ('Спорт и площадки', ('sport', 'pitch', 'playground')),
]


# ---------------------------------------------------------------------------
#  Экономика аренды
# ---------------------------------------------------------------------------
def _rooms_key(r):
    r = (r or '').lower()
    return 'studio' if 'студ' in r else 'r1' if r.startswith('1') else 'r2' if r.startswith('2') else 'r3'


def economics(f, env, A):
    edge = f['floor'] and f['floors'] and f['floors'] > 2 and f['floor'] in (1, f['floors'])
    if f['rent']:
        rent, kind = float(f['rent']), 'из данных'
    else:
        key = _rooms_key(f['rooms'])
        size_k = _clamp(math.sqrt(f['area'] / {'studio': 25, 'r1': 38, 'r2': 55, 'r3': 75}[key]), 0.85, 1.2)
        k = size_k * f.get('nbk', 1.0) * (1 + A['envEffect'] / 100 * (((env if env is not None else 50) - 50) / 50)) \
            * A['localityK'].get(f['locality'], 1) * A['marketK'].get(f['market'], 1) * (A['edgeFloorK'] if edge else 1)
        rent, kind = round(_clamp(A['rentBase'][key] * k, A['rentMin'], A['rentMax']) / 500) * 500, 'оценка модели'
    invest = f['price'] + A['repairPerM2'] * f['area'] + f['price'] * A['buyCostPct'] / 100
    revenue = rent * max(0, 12 - A['vacancyMonths'])
    mgmt, maint = revenue * A['mgmtPct'] / 100, revenue * A['maintPct'] / 100
    base = revenue - mgmt
    tax = base * 0.13 if A['taxMode'] == 'ndfl13' else base * 0.04 if A['taxMode'] == 'self4' else 0
    net = revenue - mgmt - maint - tax - f['price'] * A['propTaxPct'] / 100
    return {'rent': rent, 'kind': kind, 'invest': invest, 'net': net, 'gross': rent * 12 / f['price'], 'net_yield': net / invest,
            'payback': invest / net if net > 0 else None, 'ppm': f['price'] / f['area']}


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def resale(f, env, disc, A, e):
    """Перепродажа: цена через horizon лет = цена x (1 + сближение с соседями) x (1 + рост)^лет; рост зависит от среды, рынка, пункта."""
    n = max(1, int(A['horizon']))
    catch = _clamp(disc or 0, -0.15, 0.15) * A['catchUp']
    g = (A['priceGrowth'] + A['growthEnv'] * (((env if env is not None else 50) - 50) / 50) + (A['growthNew'] if f['market'] == 'new' else 0)
         + A['growthLoc'].get(f['locality'], 0)) / 100
    exit_ = f['price'] * (1 + catch) * (1 + g) ** n
    sell = exit_ * A['sellCostPct'] / 100
    free = A['saleTax'] == 'none' or (A['saleTax'] == 'auto' and n >= 5)
    tax = 0 if free else max(0, exit_ - max(f['price'], 1e6)) * 0.13
    proceeds = exit_ - sell - tax
    inv = f['price'] * (1 + A['buyCostPct'] / 100)
    cagr = (proceeds / inv) ** (1 / n) - 1 if proceeds > 0 else -1
    flows = [-e['invest']] + [e['net'] + (proceeds if i == n else 0) for i in range(1, n + 1)]
    lo, hi = -0.5, 1.0
    for _ in range(40):
        m = (lo + hi) / 2
        if sum(c / (1 + m) ** t for t, c in enumerate(flows)) > 0:
            lo = m
        else:
            hi = m
    return {'years': n, 'g': g, 'catch': catch, 'exit': exit_, 'growth': exit_ / f['price'] - 1, 'sell': sell, 'tax': tax, 'free': free,
            'proceeds': proceeds, 'profit': proceeds - inv, 'cagr': cagr, 'rent_total': e['net'] * n,
            'total': proceeds + e['net'] * n - e['invest'], 'irr': (lo + hi) / 2}


def _ret_and_range(e, A, rs):
    goal = A['goal'] if rs else 'rent'
    if goal == 'resale':
        return rs['cagr'], A['retRange']['resale'][0] / 100, A['retRange']['resale'][1] / 100
    if goal == 'mix':
        return rs['irr'], A['retRange']['mix'][0] / 100, A['retRange']['mix'][1] / 100
    return e['net_yield'], A['yieldMin'] / 100, A['yieldMax'] / 100


def profit_score(e, env, disc, A, rs=None):
    W = A['scoreW']
    k = 100.0 / ((W['yield'] + W['env'] + W['price']) or 100)
    ret, lo, hi = _ret_and_range(e, A, rs)
    y = _clamp((ret - lo) / (hi - lo))
    c = 0.5 if env is None else _clamp((env - 20) / 70)
    d = _clamp(0.5 + (disc or 0) * 2.5)
    return int(round(W['yield'] * k * y + W['env'] * k * c + W['price'] * k * d))


def score_parts(e, env, disc, A, rs=None):
    """Баллы трёх частей оценки и их максимумы (для карточки)."""
    W = A['scoreW']
    k = 100.0 / ((W['yield'] + W['env'] + W['price']) or 100)
    ret, lo, hi = _ret_and_range(e, A, rs)
    y = _clamp((ret - lo) / (hi - lo))
    c = 0.5 if env is None else _clamp((env - 20) / 70)
    d = _clamp(0.5 + (disc or 0) * 2.5)
    return [[round(W['yield'] * k * y, 1), round(W['yield'] * k, 1)], [round(W['env'] * k * c, 1), round(W['env'] * k, 1)],
            [round(W['price'] * k * d, 1), round(W['price'] * k, 1)]]


def near_list(near):
    """Ближайшие места для карточки: до 10 «плюсов» и до 6 «минусов» [название категории, метры, имя места, pos|neg]."""
    items = [[CATS[c]['label'], int(round(v[0])), v[1] or '', CATS[c]['kind']] for c, v in near.items() if c in CATS]
    pos = sorted((i for i in items if i[3] == 'pos'), key=lambda i: i[1])[:10]
    neg = sorted((i for i in items if i[3] == 'neg'), key=lambda i: i[1])[:6]
    return pos + neg


def verdict(s):
    return 'Сильный вариант' if s >= 65 else 'Хороший вариант' if s >= 45 else 'Средний вариант' if s >= 30 else 'Слабый вариант'


# ---------------------------------------------------------------------------
#  Привязка квартир к зданиям проекта
# ---------------------------------------------------------------------------
def _match_building(lat, lon, bgrid):
    """Здание проекта, внутри прямоугольника которого лежит точка; иначе ближайшее в радиусе 60 м."""
    kx = K * math.cos(math.radians(lat))
    best, bd = None, 1e18
    cx, cy = int(lat * K / 100), int(lon * kx / 100)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for b in bgrid.get((cx + dx, cy + dy), ()):
                bid, blat, blon, w, h, rot = b
                x, y = (lon - blon) * kx, (lat - blat) * K
                r = math.radians(rot or 0)
                u, v = x * math.cos(r) + y * math.sin(r), -x * math.sin(r) + y * math.cos(r)
                inside = abs(u) <= w / 2 and abs(v) <= h / 2
                d = math.hypot(x, y)
                if inside:
                    return bid
                if d < bd:
                    bd, best = d, bid
    return best if bd <= 60 else None


# ---------------------------------------------------------------------------
#  Пересчёт
# ---------------------------------------------------------------------------
def _recalc(db_path, get_setting_fn):
    try:
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        A = _settings(db, get_setting_fn)
        flats = [dict(r) for r in db.execute('SELECT * FROM realty_flat')]
        pois = [(r[0], r[1], r[2], r[3]) for r in db.execute('SELECT cat, lat, lon, name FROM realty_poi')]
        # остановки проекта (тип «Остановка») — тоже места
        pois += [('transport', r[0], r[1], r[2] or 'Остановка') for r in db.execute('SELECT lat, lon, name FROM nodes WHERE type_id=2')]
        with _LOCK:
            _JOB.update(running=True, progress=0, total=len(flats), message='Готовлю данные…', error=None)
        graph = _get_graph(db) if A['walkMode'] == 'graph' else None
        # здания проекта в сетке 100 м
        bgrid = {}
        for r in db.execute('SELECT id, lat, lon, w, h, rotation FROM buildings'):
            bgrid.setdefault((int(r[1] * K / 100), int(r[2] * K * math.cos(math.radians(r[1])) / 100)), []).append(tuple(r))
        poi_at, poi_sn = {}, {}
        if graph:
            _log('привязываю места к графу')
            for i, (cat, la, lo, name) in enumerate(pois):
                c = CATS.get(cat)
                if c and c['kind'] == 'pos' and c['R'] <= ROUTE_MAX:
                    n, off = graph.nearest(la, lo, 350)
                    if n is not None:
                        poi_at.setdefault(n, []).append((i, off))
        # светофоры и переходы проекта рядом с квартирой
        special = [(r[0], r[1], r[2]) for r in db.execute('SELECT lat, lon, type_id FROM nodes WHERE type_id IN (2,3,4)')]
        results = []
        # уровень цен соседних квартир (до 1,5 км) относительно города — влияет на оценку аренды
        ppms = sorted(f['price'] / f['area'] for f in flats)
        city_ppm = ppms[len(ppms) // 2] if ppms else 1
        for f in flats:
            kx0 = K * math.cos(math.radians(f['lat']))
            loc = sorted(g['price'] / g['area'] for g in flats if g is not f and abs((g['lat'] - f['lat']) * K) < NEAR_R and math.hypot((g['lat'] - f['lat']) * K, (g['lon'] - f['lon']) * kx0) <= NEAR_R)
            local = loc[len(loc) // 2] if len(loc) >= 3 else city_ppm
            f['nbk'] = max(0.9, min(1.12, (local / city_ppm) ** A['nbEffect']))
        for n_done, f in enumerate(flats, 1):
            walk = None
            if graph:
                src, off0 = graph.nearest(f['lat'], f['lon'], 600)
                if src is not None:
                    dist = graph.dijkstra(src, ROUTE_MAX - off0)
                    ds, names = {}, {}
                    for node, d in dist.items():
                        for i, off in poi_at.get(node, ()):
                            cat = pois[i][0]
                            tot = off0 + d + off
                            if tot > CATS[cat]['R']:
                                continue
                            a = ds.setdefault(cat, [])
                            a.append(tot)
                            if len(a) == 1 or tot < min(a[:-1]):
                                names[cat] = pois[i][3]
                    walk = ({c: sorted(v)[:6] for c, v in ds.items()}, names)
            env, near = evaluate(f['lat'], f['lon'], pois, walk)
            f['env'], f['near'] = env, near
            f['e'] = economics(f, env, A)
            kx = K * math.cos(math.radians(f['lat']))
            f['crossings'] = sum(1 for la, lo, t in special if t == 3 and abs((la - f['lat']) * K) < 300 and math.hypot((la - f['lat']) * K, (lo - f['lon']) * kx) < 300)
            f['lights'] = sum(1 for la, lo, t in special if t == 4 and abs((la - f['lat']) * K) < 300 and math.hypot((la - f['lat']) * K, (lo - f['lon']) * kx) < 300)
            f['stops'] = sum(1 for cat, la, lo, _ in pois if cat in ('transport', 'tram') and abs((la - f['lat']) * K) < 800 and math.hypot((la - f['lat']) * K, (lo - f['lon']) * kx) < 800)
            f['building_id'] = _match_building(f['lat'], f['lon'], bgrid)
            with _LOCK:
                _JOB.update(progress=n_done, message=f'Считаю квартиры: {n_done} из {len(flats)}')
        # сравнение цены за м² с соседями (тот же рынок, радиус 1,5 км)
        for f in flats:
            kx = K * math.cos(math.radians(f['lat']))
            near_f = [g for g in flats if g is not f and abs((g['lat'] - f['lat']) * K) < NEAR_R and math.hypot((g['lat'] - f['lat']) * K, (g['lon'] - f['lon']) * kx) <= NEAR_R]
            same = [g for g in near_f if g['market'] == f['market']]
            vals = sorted(g['e']['ppm'] for g in (same if len(same) >= 3 else near_f))
            med = vals[len(vals) // 2] if vals else None
            f['disc'] = (med - f['e']['ppm']) / med if med else None
            f['rs'] = resale(f, f['env'], f['disc'], A, f['e'])
            f['score'] = profit_score(f['e'], f['env'], f['disc'], A, f['rs'])
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        out = []
        for f in flats:
            e = f['e']
            reasons = []
            pay = '' if e['payback'] is None else ', окупаемость %.1f лет' % e['payback']
            reasons.append('Аренда %d ₽/мес (%s), чистая доходность %.1f%%%s.' % (int(e['rent']), e['kind'], e['net_yield'] * 100, pay))
            if f['disc'] is not None:
                reasons.append(f"Цена за м² {'ниже' if f['disc'] >= 0 else 'выше'} соседей на {abs(f['disc']) * 100:.0f}%.")
            rs = f['rs']
            reasons.append('Перепродажа: через %d лет около %s ₽ (%+.0f%%), после расходов%s остаётся %s ₽; с арендой вместе %.1f%% в год.'
                           % (rs['years'], format(int(round(rs['exit'], -4)), ',').replace(',', ' '), rs['growth'] * 100, '' if rs['free'] else ' и налога',
                              format(int(round(rs['proceeds'], -4)), ',').replace(',', ' '), rs['irr'] * 100))
            reasons.append('Индекс среды ' + ('не посчитан: рядом нет мест.' if f['env'] is None else f"{f['env']} из 100."))
            w15 = sum(1 for _, cats in WALK15 if any(c in f['near'] and f['near'][c][0] <= 1200 for c in cats))
            out.append((f['id'], f['building_id'], f['env'], e['rent'], e['kind'], e['gross'], e['net_yield'], e['payback'], e['ppm'],
                        f['disc'], f['score'], verdict(f['score']), w15, f['stops'], f['crossings'], f['lights'], json.dumps(reasons, ensure_ascii=False), now,
                        json.dumps(near_list(f['near']), ensure_ascii=False), json.dumps(score_parts(e, f['env'], f['disc'], A, f['rs'])),
                        json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in f['rs'].items()})))
        db.execute('DELETE FROM realty_result')
        db.executemany('INSERT INTO realty_result VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', out)
        db.executemany('UPDATE realty_flat SET building_id=? WHERE id=?', [(f['building_id'], f['id']) for f in flats])
        _write_characteristics(db, flats)
        db.commit()
        db.close()
        with _LOCK:
            _JOB.update(message=f'Готово: {len(flats)} квартир, {sum(1 for f in flats if f["building_id"])} привязано к зданиям проекта')
        _log(_JOB['message'])
    except Exception as e:
        with _LOCK:
            _JOB['error'] = f'{type(e).__name__}: {e}'
        _log('ОШИБКА: ' + _JOB['error'])
        _log(traceback.format_exc())
    finally:
        with _LOCK:
            _JOB.update(running=False, finished_at=time.strftime('%Y-%m-%d %H:%M:%S'))


def _write_characteristics(db, flats):
    """Результаты — в общие таблицы проекта: характеристики зданий (по лучшей квартире в здании), статично (день 0, час 0)."""
    ids = {}
    for key, name in CHAR_NAMES.items():
        row = db.execute('SELECT id FROM characteristics WHERE name=?', (name,)).fetchone()
        if row is None:
            cur = db.execute("INSERT INTO characteristics(name, applies_to) VALUES(?, 'building')", (name,))
            ids[key] = cur.lastrowid
        else:
            ids[key] = row[0]
        db.execute("DELETE FROM data WHERE type='building' AND characteristic_id=?", (ids[key],))
    best = {}
    for f in flats:
        b = f['building_id']
        if b and (b not in best or f['score'] > best[b]['score']):
            best[b] = f
    rows = []
    for b, f in best.items():
        vals = {'env': f['env'], 'ppm': f['e']['ppm'], 'yield': round(f['e']['net_yield'] * 100, 2), 'score': f['score']}
        for key, v in vals.items():
            if v is not None:
                rows.append((b, 'building', ids[key], 0, 0, float(v)))
    db.executemany('INSERT INTO data(target_id, type, characteristic_id, weekday, hour, value) VALUES(?,?,?,?,?,?)', rows)


# ---------------------------------------------------------------------------
#  Страница
# ---------------------------------------------------------------------------
PAGE = r"""{% extends "base.html" %}
{% block title %}Инвестиционная привлекательность жилья{% endblock %}
{% block head %}
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
 .rl-grid{display:grid;grid-template-columns:minmax(0,1fr) 440px;gap:14px;height:calc(100vh - 150px);min-height:520px}
 #rl-map{border-radius:8px;border:1px solid #cfd8dc}
 .rl-side{overflow:auto;background:#fff;border:1px solid #cfd8dc;border-radius:8px;padding:12px}
 .rl-tabs{display:flex;gap:6px;margin-bottom:10px}
 .rl-tabs button.on{background:#2c3e50;color:#fff}
 .rl-tbl{width:100%;border-collapse:collapse;font-size:13px}
 .rl-tbl th,.rl-tbl td{padding:6px 8px;border-bottom:1px solid #eceff1;text-align:left}
 .rl-tbl tr{cursor:pointer}.rl-tbl tr:hover td,.rl-tbl tr.sel td{background:#eaf2f8}
 .rl-badge{display:inline-block;min-width:30px;text-align:center;border-radius:10px;padding:1px 8px;color:#fff;font-weight:600}
 .rl-kpis{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}
 .rl-kpi{border:1px solid #eceff1;border-radius:6px;padding:8px}.rl-kpi small{display:block;color:#78909c}.rl-kpi b{font-size:18px}
 .rl-form{display:grid;grid-template-columns:1fr 1fr;gap:8px 12px}.rl-form label{display:flex;flex-direction:column;font-size:12px;color:#546e7a}
 .rl-form input,.rl-form select{padding:5px 6px;border:1px solid #cfd8dc;border-radius:4px}
 .rl-bar{height:8px;background:#eceff1;border-radius:4px;overflow:hidden;margin:6px 0}.rl-bar i{display:block;height:100%;background:#27ae60}
 .rl-chips{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}.rl-chips span{background:#eceff1;border-radius:12px;padding:2px 10px;font-size:12px}
 .rl-legend{display:flex;align-items:center;gap:8px;font-size:12px;color:#546e7a;margin-top:6px}
 .rl-legend i{display:inline-block;width:160px;height:8px;border-radius:4px;background:linear-gradient(90deg,#e74c3c,#f39c12,#9bd35a,#27ae60)}
 .rl-reason{font-size:13px;margin:4px 0;color:#37474f}
 .pp-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;border-bottom:2px solid #2c3e50;padding-bottom:8px}
 .pp-addr{font-weight:600;font-size:15px;color:#2c3e50}.pp-sub{font-size:12px;color:#78909c;margin-top:2px}
 .pp-score{flex:none;text-align:center;border:3px solid #27ae60;border-radius:50%;width:62px;height:62px;display:flex;flex-direction:column;justify-content:center}
 .pp-score b{font-size:22px;line-height:1}.pp-score small{font-size:10px;color:#78909c}
 .pp-meter{position:relative;height:8px;border-radius:4px;background:linear-gradient(90deg,#e74c3c,#f39c12,#9bd35a,#27ae60);margin:12px 0 4px}
 .pp-meter i{position:absolute;top:-4px;width:4px;height:16px;background:#2c3e50;border-radius:2px;transform:translateX(-2px)}
 .pp-verdict{font-size:13px;color:#37474f}
 .pp h4{margin:16px 0 6px;font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:#546e7a;border-left:3px solid #2c3e50;padding-left:7px}
 .pp-t{width:100%;border-collapse:collapse;font-size:13px}.pp-t td{padding:4px 6px;border-bottom:1px solid #eceff1}.pp-t td:first-child{color:#607d8b;width:46%}
 .pp-t td:last-child{text-align:right;color:#263238}.pp-t td small{color:#90a4ae}.pp-t .neg td:last-child{color:#c0392b}
 .pp-parts div{display:grid;grid-template-columns:130px 1fr 54px;gap:8px;align-items:center;font-size:12px;margin:4px 0;color:#546e7a}
 .pp-parts em{font-style:normal;text-align:right;color:#263238}
 .pp-link{display:inline-block;margin-top:12px}
 @media(max-width:1000px){.rl-grid{grid-template-columns:1fr;height:auto}#rl-map{height:55vh}}
</style>
{% endblock %}
{% block content %}
<h2>Инвестиционная привлекательность жилья</h2>
<p class="muted">Цены продажи и оценка аренды, пешая доступность инфраструктуры по дорожному графу проекта. Здания проекта с объявлениями окрашены по индексу выгодности.</p>
<div class="rl-grid">
  <div id="rl-map"></div>
  <div class="rl-side">
    <div class="rl-tabs"><button class="on" data-t="rank">Рейтинг</button><button data-t="set">Настройки</button><button data-t="data">Данные</button></div>
    <div id="rl-rank"></div><div id="rl-set" hidden></div><div id="rl-data" hidden></div>
  </div>
</div>
{% endblock %}
{% block scripts %}
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
{% raw %}
<script>
(function(){
const B='/modules/realty';
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=t=>String(t??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>Math.round(n).toLocaleString('ru-RU'), pct=x=>(x*100).toFixed(1).replace('.',',')+'%';
const col=s=>s>=65?'#27ae60':s>=45?'#9bd35a':s>=30?'#f39c12':'#e74c3c';
const map=L.map('rl-map').setView([56.6328,47.8908],13);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(map);
const layerB=L.layerGroup().addTo(map), layerF=L.layerGroup().addTo(map), layerD=L.layerGroup();
function zoomSync(){ if(map.getZoom()<17){ map.addLayer(layerD); map.removeLayer(layerB);} else { map.removeLayer(layerD); map.addLayer(layerB);} }
map.on('zoomend',zoomSync);
let flats=[], blds=[], sel=null;
const api=async(u,o)=>{const r=await fetch(B+u,o); return r.json();};
function corners(b){const rot=(b.rotation||0)*Math.PI/180,c=Math.cos(rot),s=Math.sin(rot),hw=b.w/2,hh=b.h/2;
  return [[-hw,-hh],[hw,-hh],[hw,hh],[-hw,hh]].map(([x,y])=>{const rx=x*c-y*s,ry=x*s+y*c;return [b.lat+ry/111320,b.lon+rx/(111320*Math.cos(b.lat*Math.PI/180))];});}
async function load(){
  [flats,blds]=await Promise.all([api('/api/flats'),api('/api/buildings')]);
  try{GOAL=(await api('/api/settings')).goal||'rent';}catch(e){}
  layerB.clearLayers(); layerF.clearLayers(); layerD.clearLayers();
  blds.forEach(b=>{L.circleMarker([b.lat,b.lon],{radius:7,color:'#fff',weight:2,fillColor:col(b.best),fillOpacity:1}).bindTooltip(`${b.flats} кв. · лучшая оценка ${b.best}`,{direction:'top'}).on('click',()=>{const f=flats.find(x=>x.building_id===b.id); if(f) pick(f.id);}).addTo(layerD);
    const p=L.polygon(corners(b),{color:'#34495e',weight:1.5,fillColor:col(b.best),fillOpacity:.85});
    p.bindTooltip(`${b.flats} кв. · лучшая оценка ${b.best}`,{direction:'top'}); p.on('click',()=>{const f=flats.find(x=>x.building_id===b.id); if(f) pick(f.id);}); p.addTo(layerB);});
  flats.filter(f=>!f.building_id).forEach(f=>{L.circleMarker([f.lat,f.lon],{radius:6,color:'#fff',weight:2,fillColor:col(f.score),fillOpacity:1}).on('click',()=>pick(f.id)).bindTooltip('вне зданий проекта').addTo(layerF);});
  renderRank();
  const core=flats.filter(f=>f.locality==='Йошкар-Ола'); const pts=(core.length?core:flats).map(f=>[f.lat,f.lon]);
  if(pts.length) map.fitBounds(L.latLngBounds(pts).pad(.1)); zoomSync();
}
function renderRank(){
  const box=$('#rl-rank');
  if(!flats.length){box.innerHTML='<p class="muted">Нет данных. Откройте вкладку «Данные» и загрузите объявления, затем нажмите «Пересчитать».</p>';return;}
  const rows=[...flats].sort((a,b)=>b.score-a.score);
  box.innerHTML=`<div id="rl-card"></div><div class="rl-legend">слабо <i></i> сильно</div>
  <table class="rl-tbl"><thead><tr><th>№</th><th>Квартира</th><th>Цена</th><th>Доход.</th><th>Оценка</th></tr></thead><tbody>${rows.map((f,i)=>`<tr data-id="${esc(f.id)}" class="${sel===f.id?'sel':''}"><td>${i+1}</td><td>${esc(f.rooms)} · ${f.area} м²<br><small class="muted">${esc(f.address)}</small></td><td>${(f.price/1e6).toFixed(2).replace('.',',')} млн</td><td>${pct(f.net_yield)}</td><td><span class="rl-badge" style="background:${col(f.score)}">${f.score}</span></td></tr>`).join('')}</tbody></table>`;
  $$('#rl-rank tbody tr').forEach(tr=>tr.onclick=()=>pick(tr.dataset.id));
}
function pick(id){
  sel=id; const f=flats.find(x=>x.id===id); if(!f) return;
  $$('#rl-rank tbody tr').forEach(tr=>tr.classList.toggle('sel',tr.dataset.id===id));
  map.setView([f.lat,f.lon],Math.max(map.getZoom(),17));
  const reasons=JSON.parse(f.reasons||'[]'), near=JSON.parse(f.near||'[]'), parts=JSON.parse(f.parts||'[]');
  const names=[{rent:'Доходность аренды',resale:'Рост цены',mix:'Общая доходность'}[GOAL],'Индекс среды','Цена к соседям'];
  const rs=JSON.parse(f.resale||'{}'), m10=x=>fmt(Math.round(x/1e4)*1e4), sg=x=>(x>=0?'+':'−')+Math.abs(x*100).toFixed(0)+'%';
  const row=(k,v)=>`<tr><td>${k}</td><td>${v}</td></tr>`;
  const mins=m=>Math.max(1,Math.round(m/80));
  $('#rl-card').innerHTML=`<div class="pp">
   <div class="pp-head"><div><div class="pp-addr">${esc(f.address)}</div><div class="pp-sub">${f.market==='new'?'Новостройка':'Вторичное жильё'} · ${esc(f.rooms)} · ${f.area} м²</div></div>
     <div class="pp-score" style="border-color:${col(f.score)}"><b>${f.score}</b><small>из 100</small></div></div>
   <div class="pp-meter"><i style="left:${f.score}%"></i></div><div class="pp-verdict">${esc(f.verdict)}</div>
   <h4>Параметры объекта</h4><table class="pp-t">${row('Цена',fmt(f.price)+' ₽')}${row('Цена за м²',fmt(f.ppm)+' ₽')}${row('Населённый пункт',esc(f.locality))}
     ${row('Здание проекта',f.building_id?'№ '+f.building_id:'не определено')}${row('В 15 минутах пешком',f.walk15+' из 8 категорий')}</table>
   <h4>Доходность аренды</h4><table class="pp-t">${row('Аренда в месяц',fmt(f.rent)+' ₽ <small>('+esc(f.rent_kind)+')</small>')}${row('Валовая доходность',pct(f.gross))}
     ${row('Чистая доходность',pct(f.net_yield))}${row('Окупаемость',f.payback?f.payback.toFixed(1).replace('.',',')+' лет':'не окупается')}</table>
   <h4>Перепродажа</h4><table class="pp-t">${row('Цена через '+rs.years+' лет','≈ '+m10(rs.exit)+' ₽ <small>('+sg(rs.growth)+')</small>')}${row('Рост цен в год',pct(rs.g))}
     ${row('После расходов и налога',m10(rs.proceeds)+' ₽')}${row('Прибыль с продажи',(rs.profit<0?'−':'')+m10(Math.abs(rs.profit))+' ₽')}
     ${row('Аренда за '+rs.years+' лет',m10(rs.rent_total)+' ₽')}${row('Всего с арендой и продажей',(rs.total<0?'−':'')+m10(Math.abs(rs.total))+' ₽')}${row('Доходность в год (аренда + продажа)',pct(rs.irr))}</table>
   <h4>Из чего складывается оценка</h4><div class="pp-parts">${parts.map((p,i)=>`<div><span>${names[i]}</span><span class="rl-bar"><i style="width:${p[1]?100*p[0]/p[1]:0}%"></i></span><em>${p[0].toFixed(0)} / ${p[1].toFixed(0)}</em></div>`).join('')}</div>
   <h4>Инфраструктура и окружение</h4><table class="pp-t">${near.map(n=>`<tr class="${n[3]==='neg'?'neg':''}"><td>${esc(n[0])}${n[2]?' <small>· '+esc(n[2])+'</small>':''}</td><td>${n[1]} м${n[3]==='pos'?' <small>('+mins(n[1])+' мин)</small>':''}</td></tr>`).join('')||row('Нет данных','')}
     ${row('Остановок в 800 м',f.stops_800)}${row('Пешеходных переходов в 300 м',f.crossings_300)}${row('Светофоров в 300 м',f.lights_300)}</table>
   <h4>Выводы</h4>${reasons.map(r=>`<div class="rl-reason">• ${esc(r)}</div>`).join('')}
   ${f.url?`<a class="pp-link" href="${esc(f.url)}" target="_blank" rel="noopener">Открыть объявление →</a>`:''}</div><hr>`;
  $('.rl-side').scrollTo({top:0,behavior:'smooth'});
}
// ----- настройки -----
let GOAL='rent';
const F=[['rentBase.studio','Аренда студии, ₽/мес'],['rentBase.r1','Аренда 1-комн., ₽/мес'],['rentBase.r2','Аренда 2-комн., ₽/мес'],['rentBase.r3','Аренда 3+ комн., ₽/мес'],['rentMin','Аренда не ниже, ₽'],['rentMax','Аренда не выше, ₽'],['nbEffect','Влияние цен соседей, степень'],['envEffect','Влияние среды на аренду, ±%'],['edgeFloorK','Крайний этаж, ×'],
 ['marketK.new','Новостройка, ×'],['marketK.secondary','Вторичка, ×'],['vacancyMonths','Простой, мес./год'],['maintPct','Ремонт и расходы, % аренды'],['mgmtPct','Управляющий, % аренды'],['propTaxPct','Налог на имущество, % цены'],
 ['repairPerM2','Подготовка к сдаче, ₽/м²'],['buyCostPct','Расходы на сделку, %'],['scoreW.yield','Вес: доходность'],['scoreW.env','Вес: среда'],['scoreW.price','Вес: цена к соседям'],['yieldMin','Доходность на 0 баллов, %'],['yieldMax','Доходность на максимум, %'],
 ['horizon','Срок до продажи, лет'],['priceGrowth','Рост цен в год, %'],['sellCostPct','Расходы на продажу, %']];
const get=(o,p)=>p.split('.').reduce((x,k)=>x?.[k],o);
async function renderSet(){
  const A=await api('/api/settings');
  $('#rl-set').innerHTML=`<div class="rl-form">${F.map(([p,l])=>`<label>${l}<input type="number" step="any" data-k="${p}" value="${get(A,p)}"></label>`).join('')}
  <label>Цель<select data-k="goal"><option value="rent">Сдавать в аренду</option><option value="resale">Перепродать</option><option value="mix">Аренда, потом продажа</option></select></label>
  <label>Налог с продажи<select data-k="saleTax"><option value="auto">13% с прибыли, если владели &lt; 5 лет</option><option value="none">Не учитывать</option></select></label>
  <label>Налог<select data-k="taxMode"><option value="ndfl13">НДФЛ 13%</option><option value="self4">Самозанятый 4%</option><option value="none">Не учитывать</option></select></label>
  <label>Расстояния до мест<select data-k="walkMode"><option value="graph">По дорожному графу проекта</option><option value="straight">По прямой</option></select></label></div>
  <p><button class="primary" id="rl-save">Сохранить и пересчитать</button></p><div id="rl-prog"></div>`;
  $('[data-k=taxMode]').value=A.taxMode; $('[data-k=goal]').value=A.goal; $('[data-k=saleTax]').value=A.saleTax; GOAL=A.goal; $('[data-k=walkMode]').value=A.walkMode;
  $('#rl-save').onclick=async()=>{const o={};$$('#rl-set [data-k]').forEach(el=>{const ks=el.dataset.k.split('.');let t=o;ks.slice(0,-1).forEach(k=>t=t[k]=t[k]||{});t[ks.at(-1)]=el.tagName==='SELECT'?el.value:+el.value;});
    await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o)}); recalc();};
}
async function recalc(){
  await api('/api/recalc',{method:'POST'});
  const prog=$('#rl-prog')||$('#rl-dprog'); const t=setInterval(async()=>{const s=await api('/api/status');
    if(prog) prog.innerHTML=`<div class="rl-bar"><i style="width:${s.total?100*s.progress/s.total:0}%"></i></div><small class="muted">${esc(s.error||s.message)}</small>`;
    if(!s.running){clearInterval(t); await load(); renderData();}},700);
}
async function renderData(){
  const s=await api('/api/summary');
  $('#rl-data').innerHTML=`<div class="rl-kpis"><div class="rl-kpi"><small>Объявлений</small><b>${s.flats}</b></div><div class="rl-kpi"><small>Мест (POI)</small><b>${s.poi}</b></div>
  <div class="rl-kpi"><small>Зданий проекта</small><b>${s.buildings}</b></div><div class="rl-kpi"><small>Привязано к зданиям</small><b>${s.matched}</b></div>
  <div class="rl-kpi"><small>Узлов графа</small><b>${s.nodes}</b></div><div class="rl-kpi"><small>Рёбер графа</small><b>${s.edges}</b></div></div>
  <p class="muted">Результаты записаны в характеристики зданий проекта: ${esc(s.chars.join(', '))}.</p>
  <p><button class="primary" id="rl-re">Пересчитать</button> <button id="rl-seed">Загрузить встроенные данные</button></p><div id="rl-dprog"></div>
  <hr><p>Импорт объявлений (JSON: список объектов <code>address, locality, market, rooms, area, floor, floors, price, rent, lat, lng, url</code>):</p>
  <input type="file" id="rl-file" accept=".json"> <button id="rl-imp">Импортировать</button><p class="muted" id="rl-imsg"></p>`;
  $('#rl-re').onclick=recalc;
  $('#rl-seed').onclick=async()=>{await api('/api/reseed',{method:'POST'}); recalc();};
  $('#rl-imp').onclick=async()=>{const f=$('#rl-file').files[0]; if(!f) return; const fd=new FormData(); fd.append('file',f);
    const r=await (await fetch(B+'/api/import',{method:'POST',body:fd})).json(); $('#rl-imsg').textContent=r.error||`Загружено объявлений: ${r.count}. Нажмите «Пересчитать».`;};
}
$$('.rl-tabs button').forEach(b=>b.onclick=()=>{$$('.rl-tabs button').forEach(x=>x.classList.toggle('on',x===b));
  ['rank','set','data'].forEach(t=>$('#rl-'+t).hidden=t!==b.dataset.t); if(b.dataset.t==='set') renderSet(); if(b.dataset.t==='data') renderData();});
load();
})();
</script>
{% endraw %}
{% endblock %}
"""


# ---------------------------------------------------------------------------
#  register()
# ---------------------------------------------------------------------------
def register(app, loader):
    from flask import jsonify, render_template_string, request
    from db import get_db, get_setting, set_setting
    import db as dbmod

    # таблицы и встроенные данные — при первом запуске
    con = sqlite3.connect(dbmod.DB_PATH)
    try:
        _ensure(con)
    finally:
        con.close()

    @app.route('/modules/realty')
    def realty_page():
        return render_template_string(PAGE, info=MODULE_INFO, active='modules')

    @app.route('/modules/realty/api/flats')
    def realty_flats():
        db = get_db()
        rows = db.execute("""SELECT f.id, f.address, f.locality, f.market, f.rooms, f.area, f.price, f.lat, f.lon, f.url, f.building_id,
                                    r.env, r.rent, r.rent_kind, r.gross, r.net_yield, r.payback, r.ppm, r.disc, r.score, r.verdict,
                                    r.walk15, r.stops_800, r.crossings_300, r.lights_300, r.reasons, r.near, r.parts, r.resale
                             FROM realty_flat f JOIN realty_result r ON r.flat_id = f.id""").fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route('/modules/realty/api/buildings')
    def realty_buildings():
        db = get_db()
        rows = db.execute("""SELECT b.id, b.lat, b.lon, b.w, b.h, b.rotation, COUNT(*) AS flats, MAX(r.score) AS best
                             FROM realty_flat f JOIN realty_result r ON r.flat_id = f.id JOIN buildings b ON b.id = f.building_id
                             GROUP BY b.id""").fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route('/modules/realty/api/summary')
    def realty_summary():
        db = get_db()
        one = lambda q: db.execute(q).fetchone()[0]
        return jsonify({'flats': one('SELECT COUNT(*) FROM realty_flat'), 'poi': one('SELECT COUNT(*) FROM realty_poi'),
                        'buildings': one('SELECT COUNT(*) FROM buildings'), 'matched': one('SELECT COUNT(*) FROM realty_flat WHERE building_id IS NOT NULL'),
                        'nodes': one('SELECT COUNT(*) FROM nodes'), 'edges': one('SELECT COUNT(*) FROM edges'), 'chars': list(CHAR_NAMES.values())})

    @app.route('/modules/realty/api/settings', methods=['GET', 'POST'])
    def realty_settings():
        db = get_db()
        if request.method == 'GET':
            return jsonify(_settings(db, get_setting))
        incoming = request.get_json(silent=True) or {}
        cur = _settings(db, get_setting)
        for k, v in incoming.items():
            if k in cur:
                if isinstance(v, dict) and isinstance(cur[k], dict):
                    cur[k].update({kk: vv for kk, vv in v.items() if kk in cur[k]})
                elif not isinstance(cur[k], dict):
                    cur[k] = v
        set_setting(db, 'realty_settings', json.dumps(cur, ensure_ascii=False))
        db.commit()
        return jsonify({'ok': True})

    @app.route('/modules/realty/api/recalc', methods=['POST'])
    def realty_recalc():
        with _LOCK:
            if _JOB['running']:
                return jsonify({'error': 'Расчёт уже идёт'}), 409
            _JOB.update(running=True, progress=0, total=0, message='Запуск…', error=None)
        threading.Thread(target=_recalc, args=(dbmod.DB_PATH, get_setting), daemon=True).start()
        return jsonify({'ok': True})

    @app.route('/modules/realty/api/status')
    def realty_status():
        with _LOCK:
            return jsonify({k: v for k, v in _JOB.items() if k != 'log'})

    @app.route('/modules/realty/api/reseed', methods=['POST'])
    def realty_reseed():
        db = get_db()
        _seed(db)
        return jsonify({'ok': True})

    @app.route('/modules/realty/api/import', methods=['POST'])
    def realty_import():
        f = request.files.get('file')
        if not f:
            return jsonify({'error': 'Файл не передан'}), 400
        try:
            data = json.loads(f.read().decode('utf-8-sig'))
            flats = data.get('listings', data) if isinstance(data, dict) else data
            db = get_db()
            n = _load_flats(db, flats)
            db.commit()
        except (ValueError, AttributeError, TypeError) as e:
            return jsonify({'error': f'Не удалось прочитать JSON: {e}'}), 400
        return jsonify({'ok': True, 'count': n})
