#!/usr/bin/env python3
"""Все места из локальной выгрузки OpenStreetMap (data/osm/mari_el.pbf) -> dist/data/poi.json.
Без Overpass и лимитов. Правила категорий общие с scripts/fetch_poi.py.
Площадные объекты (парки, леса, водоёмы, промзоны...) разбиваются на точки-«пробы» каждые ~350 м внутри контура,
чтобы расстояние до большого парка считалось до его края, а не до центра. Линии прореживаются до ~250 м.
Нужна библиотека: pip install osmium"""
import json, math, sys, time
from pathlib import Path

import osmium

sys.path.insert(0, str(Path(__file__).resolve().parent))
from poi_rules import VOLATILE, classify, is_closed, is_fresh, thin  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PBF = ROOT / "data" / "osm" / "mari_el.pbf"
OUT = ROOT / "dist" / "data" / "poi.json"
S, W, N, E = 56.55, 47.71, 56.72, 48.02  # область анализа
STEP = 350  # м между пробами внутри больших площадей
MAX_PER_AREA = 250


def inside_bbox(lat, lon):
    return S <= lat <= N and W <= lon <= E


def line_cat(t):
    h, r = t.get("highway"), t.get("railway")
    if h in ("motorway", "trunk", "primary", "motorway_link", "trunk_link"): return "highway"
    if r == "rail": return "railway"
    if t.get("power") == "line": return "powerline"
    if t.get("aeroway") == "runway": return "airport"
    if h == "cycleway": return "cycleway"
    if t.get("waterway") in ("river", "canal"): return "water"
    if h == "pedestrian" and "абережн" in (t.get("name") or "").lower(): return "promenade"
    return None


def pip(x, y, ring):
    c = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def area_points(rings):
    """Центр малого объекта или сетка проб внутри контура большого."""
    pts = [(lat, lon) for ring in rings for lon, lat in ring]
    if not pts:
        return []
    la0, la1 = min(p[0] for p in pts), max(p[0] for p in pts)
    lo0, lo1 = min(p[1] for p in pts), max(p[1] for p in pts)
    h, w = (la1 - la0) * 111320, (lo1 - lo0) * 111320 * math.cos(math.radians((la0 + la1) / 2))
    if max(h, w) < 2 * STEP:
        return [((la0 + la1) / 2, (lo0 + lo1) / 2)]
    out, dlat, dlon = [], STEP / 111320, STEP / (111320 * math.cos(math.radians((la0 + la1) / 2)))
    lat = la0 + dlat / 2
    while lat < la1 and len(out) < MAX_PER_AREA:
        lon = lo0 + dlon / 2
        while lon < lo1 and len(out) < MAX_PER_AREA:
            if any(pip(lon, lat, r) for r in rings):
                out.append((lat, lon))
            lon += dlon
        lat += dlat
    return out or [((la0 + la1) / 2, (lo0 + lo1) / 2)]


def alive(tags, year, cats):
    """Убираем закрытые объекты и давно не правленные магазины, кафе, офисы и т. п."""
    if is_closed(tags):
        return set()
    if is_fresh(tags, year):
        return cats
    return {c for c in cats if c not in VOLATILE}


def main():
    if not PBF.exists():
        print("нет", PBF); return 1
    pts, t0 = [], time.time()
    fp = osmium.FileProcessor(str(PBF)).with_locations().with_areas()
    counts = {}
    for o in fp:
        tags = o.tags
        if not len(tags):
            continue
        name = tags.get("name") or ""
        if o.is_node():
            if not inside_bbox(o.location.lat, o.location.lon):
                continue
            for cat in alive(tags, o.timestamp.year, classify(tags)):
                pts.append([cat, round(o.location.lat, 5), round(o.location.lon, 5), name])
        elif o.is_area():
            cats = alive(tags, o.timestamp.year, classify(tags))
            if not cats:
                continue
            rings = []
            try:
                for ring in o.outer_rings():
                    rings.append([(n.lon, n.lat) for n in ring])
            except Exception:
                continue
            if not rings or not any(inside_bbox(la, lo) or True for lo, la in rings[0][:1]):
                continue
            for lat, lon in area_points(rings):
                if inside_bbox(lat, lon):
                    for cat in cats:
                        pts.append([cat, round(lat, 5), round(lon, 5), name])
        elif o.is_way() and not o.is_closed() or (o.is_way() and line_cat(tags) in ("highway", "railway", "powerline", "cycleway", "water", "promenade", "airport")):
            cat = line_cat(tags)
            if not cat:
                continue
            try:
                coords = [(n.lat, n.lon) for n in o.nodes if n.location.valid()]
            except Exception:
                continue
            for lat, lon in thin([c for c in coords if inside_bbox(*c)]):
                pts.append([cat, round(lat, 5), round(lon, 5), name])
    seen, uniq = set(), []
    for p in pts:
        k = (p[0], p[1], p[2])
        if k not in seen:
            seen.add(k); uniq.append(p); counts[p[0]] = counts.get(p[0], 0) + 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"updatedAt": time.strftime("%Y-%m-%d") + " (OSM)", "points": uniq}, ensure_ascii=False), encoding="utf-8")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"{k:14}{v}")
    print("точек:", len(uniq), f"за {time.time() - t0:.0f} с")
    return 0


if __name__ == "__main__":
    sys.exit(main())
