#!/usr/bin/env python3
"""Точные координаты и контуры домов: data/osm/mari_el.pbf + dist/data/listings.json -> dist/data/buildings.json.
1. Адрес объявления (улица + номер дома) ищется среди адресов домов OpenStreetMap — так квартира встаёт ровно в свой дом,
   даже если геокодер Nominatim ошибся. Исправленные координаты пишутся в listings.json и data/geocode-cache.json.
2. Если точного адреса нет, дом берётся по близости: точка внутри контура или не дальше 25 м.
Новостройки: дом часто ещё строится и в OSM его нет (или стоит старый дом рядом), поэтому для них рисуется участок —
стройплощадка из OSM (landuse=construction; ищется по названию ЖК, потом по близости), а если её нет — условный прямоугольник.
Готовый дом из OSM берётся, только если он свежий (правка не раньше 2024 года) и адрес совпал точно.
Объявления без номера дома («жилой дом») к дому не привязываются. Запускать после sync_listings.py.
Нужны: pip install osmium shapely"""
import json, math, re, sys
from collections import defaultdict
from pathlib import Path

import osmium
from shapely import wkb
from shapely.geometry import Point
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
PBF, LST, OUT, CACHE = ROOT / "data/osm/mari_el.pbf", ROOT / "dist/data/listings.json", ROOT / "dist/data/buildings.json", ROOT / "data/geocode-cache.json"
MAXD = 25 / 111320  # градусы
FALLBACK = 60 / 111320  # для адресов без номера дома / не найденных точно: ближайший дом в 60 м
M = 111320.0
PLACES = {"Йошкар-Ола": (56.6388, 47.8908, .12), "Медведево": (56.6350, 47.8170, .06), "Семёновка": (56.6552, 47.9771, .05), "Руэм": (56.6310, 47.7560, .05)}

TYPES = r"\b(ул|улица|пер|переулок|тракт|проспект|пр|б-р|бульвар|мкр|микрорайон|наб|набережная|проезд|шоссе|с|п|пос|пгт|им|имени|ой|ий|ая|ое|ый)\b"


def nstreet(s):
    s = re.sub(r"[.,]", " ", s.lower().replace("ё", "е"))
    return " ".join(sorted(re.sub(TYPES, " ", s).split()))


def nhouse(h):
    return re.sub(r"(литера|лит|\s)", "", h.lower().replace("ё", "е"))


def parse(addr):
    parts = [p.strip() for p in addr.split(",") if p.strip()]
    house = None
    if len(parts) > 2 and re.search(r"\d", parts[-1]):
        house = re.sub(r"(?i)^(д|стр|поз)\.\s*", "", parts[-1])
        if not re.fullmatch(r"\d+\s*[а-яА-Яa-zA-Z]?(\s*/\s*\d+)?", house): house = None
    street = next((p for p in parts[1:-1] if re.search(r"(?i)ул|тракт|пер|проспект|бульвар|б-р|проезд|шоссе", p)
                   or (re.search(r"[а-яА-Я]{4,}", p) and not re.match(r"(?i)(с|п|пгт|мкр|пос)\.", p) and not re.search(r"\d", p))), None)
    if house is None and len(parts) >= 2 and re.search(r"\d", parts[-1]):  # «улица, 14» без префикса
        m = re.fullmatch(r"(?:д\.|стр\.|поз\.)?\s*(\d+\s*[а-яА-Яa-zA-Z]?(?:\s*/\s*\d+)?)", parts[-1])
        if m: house = m.group(1)
    return street, house


def place_of(addr, lat, lng):
    for name, rx in (("Семёновка", r"сем[её]новк"), ("Руэм", r"руэм"), ("Медведево", r"медведев")):
        if re.search(rx, addr, re.I): return name
    return "Йошкар-Ола"


flats = json.loads(LST.read_text(encoding="utf-8"))
L = flats["listings"]
ids = [l.get("url") or f"{l['address']}|{l['area']}|{l['price']}" for l in L]
S, W, N, E = (min(l["lat"] for l in L) - .02, min(l["lng"] for l in L) - .02, max(l["lat"] for l in L) + .02, max(l["lng"] for l in L) + .02)

fab = osmium.geom.WKBFactory()
geoms, gaddr, gyear, nodes = [], [], [], []  # контуры зданий; (улица, дом) контура; год последней правки; адресные точки
plots = []  # стройплощадки: (контур, название ЖК из OSM)


class H(osmium.SimpleHandler):
    def node(self, n):
        t = n.tags
        if "addr:housenumber" in t and n.location.valid() and S < n.location.lat < N and W < n.location.lon < E:
            nodes.append(((t.get("addr:street") or t.get("addr:place") or ""), t["addr:housenumber"], n.location.lat, n.location.lon))

    def area(self, a):
        t = a.tags
        site = t.get("landuse") == "construction"
        if "building" not in t and not site: return
        try: g = wkb.loads(fab.create_multipolygon(a), hex=True)
        except Exception: return
        x0, y0, x1, y1 = g.bounds
        if x1 < W or x0 > E or y1 < S or y0 > N: return
        if site:
            plots.append((g, (t.get("name", "") + " " + t.get("construction", "")).strip()))
            return
        geoms.append(g); gaddr.append(((t.get("addr:street") or t.get("addr:place") or ""), t.get("addr:housenumber", ""))); gyear.append(a.timestamp.year)


H().apply_file(str(PBF), locations=True)
tree = STRtree(geoms)

byaddr = defaultdict(list)  # (улица, дом) -> [("b", индекс контура) | ("n", lat, lng)]
for j, (st, h) in enumerate(gaddr):
    if st and h: byaddr[(nstreet(st), nhouse(h))].append(("b", j))
for st, h, la, lo in nodes:
    if st and h: byaddr[(nstreet(st), nhouse(h))].append(("n", la, lo))


def cen(c):
    if c[0] == "b":
        p = geoms[c[1]].representative_point(); return p.y, p.x
    return c[1], c[2]


def nearest_building(lat, lng, maxd=MAXD):
    p = Point(lng, lat); best, bd = None, maxd
    for j in tree.query(p.buffer(MAXD)):
        d = geoms[j].distance(p)
        if d < bd or d == 0: best, bd = j, d
        if d == 0: break
    return best


def zhk_key(name):
    s = (name or "").lower().replace("ё", "е")
    s = re.sub(r"[«»\"“”\u200e\u200f]|жк\b|жилой комплекс|премьер-дом", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def pick_plot(l):
    """Стройплощадка новостройки: по названию ЖК, иначе та, где лежит точка, иначе ближайшая в 150 м."""
    pt = Point(l["lng"], l["lat"]); key = zhk_key(l.get("complex"))
    named = [(g.distance(pt), k) for k, (g, nm) in enumerate(plots) if key and len(key) > 4 and (key in zhk_key(nm) or zhk_key(nm) in key and zhk_key(nm))]
    named = [x for x in named if x[0] * M < 1500]
    if named: return min(named)[1], True
    inside = [(plots[k][0].area, k) for k in range(len(plots)) if plots[k][0].distance(pt) == 0]
    if inside: return min(inside)[1], False
    near = [(plots[k][0].distance(pt), k) for k in range(len(plots)) if plots[k][0].distance(pt) * M < 150]
    return (min(near)[1], False) if near else (None, False)


def snap(l, la, lo, note):
    """Квартира встаёт в точку своего дома или участка, чтобы ячейка и контур совпадали."""
    d = math.hypot((la - l["lat"]) * M, (lo - l["lng"]) * M * math.cos(math.radians(la)))
    if d > 5:
        moved.append((round(d), l["address"] + note)); l["lat"], l["lng"] = round(la, 7), round(lo, 7); cache[l["address"]] = [la, lo]


cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
moved, hit, synth, phit, nsynth = [], defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
for i, l in enumerate(L):
    st, h = parse(l["address"])
    j = None
    if st and h:
        loc = place_of(l["address"], l["lat"], l["lng"]); cy, cx, r = PLACES[loc]
        cand = [c for c in byaddr.get((nstreet(st), nhouse(h)), []) if abs(cen(c)[0] - cy) <= r and abs(cen(c)[1] - cx) <= r * 1.7]
        if cand:  # из нескольких одноимённых улиц берём ближайшую к уже найденной точке
            c = min(cand, key=lambda c: (cen(c)[0] - l["lat"]) ** 2 + (cen(c)[1] - l["lng"]) ** 2)
            la, lo = cen(c)
            d = math.hypot((la - l["lat"]) * M, (lo - l["lng"]) * M * math.cos(math.radians(la)))
            if d > 3000 or (d > 1500 and len(cand) > 1):  # слишком далеко от найденного геокодером — вероятно, другой посёлок/улица, не рискуем
                print(f"  пропуск ({len(cand)} кандидатов, {round(d)} м): {l['address']}")
            elif d > 15:
                moved.append((round(d), l["address"])); l["lat"], l["lng"] = round(la, 7), round(lo, 7); l.pop("approx", None)
                cache[l["address"]] = [la, lo]
            j = c[1] if c[0] == "b" else nearest_building(la, lo)
            if d > 3000 or (d > 1500 and len(cand) > 1): j = nearest_building(l['lat'], l['lng'])
        else:
            j = nearest_building(l["lat"], l["lng"]) if not l.get("approx") else None
    if l["market"] == "new" and not (j is not None and gyear[j] >= 2024 and not l.get("approx")):
        # новостройка: свежего дома в OSM нет — показываем участок, а не соседний старый дом
        k, by_name = pick_plot(l)
        if k is not None:
            g = plots[k][0]; rp = g.representative_point()
            snap(l, rp.y, rp.x, " (участок)")
            phit[k].append(ids[i])
        else:
            nsynth[(round(l["lat"], 4), round(l["lng"], 4))].append(ids[i])
        if not h: l["approx"] = True
        continue
    if j is None:  # точного дома нет: ближайший в 60 м, иначе условный контур 28 x 16 м вокруг точки
        j = nearest_building(l["lat"], l["lng"], FALLBACK)
        if j is None: synth[(round(l["lat"], 4), round(l["lng"], 4))].append(ids[i])
    if j is not None:
        rp = geoms[j].representative_point(); snap(l, rp.y, rp.x, " (дом)")
        hit[j].append(ids[i])
    if not h: l["approx"] = True  # адрес без номера дома — точка условная

LST.write_text(json.dumps(flats, ensure_ascii=False, indent=1), encoding="utf-8")
CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
out = []
for j, fl in hit.items():
    g = geoms[j]
    for poly in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
        out.append({"r": [[round(y, 6), round(x, 6)] for x, y in poly.exterior.coords], "f": fl})
for k, fl in phit.items():  # участки новостроек: p = 1
    g = plots[k][0]
    for poly in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
        out.append({"r": [[round(y, 6), round(x, 6)] for x, y in poly.exterior.coords], "f": fl, "p": 1})
for (la, lo), fl in nsynth.items():  # участок неизвестен: условный прямоугольник 60 x 40 м
    dy, dx = 20 / M, 30 / (M * math.cos(math.radians(la)))
    out.append({"r": [[round(la - dy, 6), round(lo - dx, 6)], [round(la - dy, 6), round(lo + dx, 6)], [round(la + dy, 6), round(lo + dx, 6)], [round(la + dy, 6), round(lo - dx, 6)], [round(la - dy, 6), round(lo - dx, 6)]], "f": fl, "p": 1, "s": 1})
for (la, lo), fl in synth.items():  # условные контуры: s = 1
    dy, dx = 8 / M, 14 / (M * math.cos(math.radians(la)))
    out.append({"r": [[round(la - dy, 6), round(lo - dx, 6)], [round(la - dy, 6), round(lo + dx, 6)], [round(la + dy, 6), round(lo + dx, 6)], [round(la + dy, 6), round(lo - dx, 6)], [round(la - dy, 6), round(lo - dx, 6)]], "f": fl, "s": 1})
OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"контуров {len(out)} (участков новостроек {len(phit)}, условных {len(synth) + len(nsynth)}), квартир привязано {sum(len(v) for g in (hit, phit, synth, nsynth) for v in g.values())} из {len(L)}; координаты исправлены у {len(moved)} адресов")
for d, a in sorted(moved, reverse=True): print(f"  {d:5d} м  {a}")
