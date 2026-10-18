#!/usr/bin/env python3
"""Пешеходный граф улиц из data/osm/mari_el.pbf -> dist/data/walk.bin.
Берутся дороги и тропы, по которым можно ходить пешком (без магистралей и закрытых проездов); граф ненаправленный.
Формат (little-endian): 'WLK1', N, E2, затем lat[N], lng[N] (float32), off[N+1], adj[E2] (int32), w[E2] (float32, метры).
Нужна библиотека: pip install osmium"""
import math, struct, sys, time
from array import array
from pathlib import Path

import osmium

ROOT = Path(__file__).resolve().parent.parent
PBF = ROOT / "data" / "osm" / "mari_el.pbf"
OUT = ROOT / "dist" / "data" / "walk.bin"
S, W, N, E = 56.54, 47.70, 56.73, 48.03  # чуть шире области анализа
FOOT = {"footway", "path", "pedestrian", "steps", "living_street", "residential", "service", "unclassified", "tertiary",
        "secondary", "primary", "track", "cycleway", "road", "corridor", "tertiary_link", "secondary_link", "primary_link"}
MIN_COMPONENT = 150  # отбрасываем мелкие изолированные куски
K = 111320.0


def usable(t):
    if t.get("highway") not in FOOT:
        return False
    if t.get("foot") == "no":
        return False
    if t.get("access") in ("private", "no") and t.get("foot") not in ("yes", "permissive", "designated"):
        return False
    return True


def main():
    t0 = time.time()
    coords, segs = {}, []
    for o in osmium.FileProcessor(str(PBF)).with_locations().with_filter(osmium.filter.KeyFilter("highway")):
        if not o.is_way() or not usable(o.tags):
            continue
        cur = []
        for n in o.nodes:
            ok = n.location.valid() and S <= n.lat <= N and W <= n.lon <= E
            if ok:
                coords[n.ref] = (n.lat, n.lon); cur.append(n.ref)
            elif len(cur) > 1:
                segs.append(cur); cur = []
            else:
                cur = []
        if len(cur) > 1:
            segs.append(cur)
    ids = {r: i for i, r in enumerate(coords)}
    n = len(ids)
    edges = []
    for seg in segs:
        for a, b in zip(seg, seg[1:]):
            if a == b:
                continue
            la, lo = coords[a]; lb, lob = coords[b]
            d = math.hypot((la - lb) * K, (lo - lob) * K * math.cos(math.radians((la + lb) / 2)))
            edges.append((ids[a], ids[b], d))
    # компоненты связности (union-find)
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b, _ in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    size = {}
    for i in range(n):
        r = find(i); size[r] = size.get(r, 0) + 1
    keep = [i for i in range(n) if size[find(i)] >= MIN_COMPONENT]
    new = {old: k for k, old in enumerate(keep)}
    refs = list(coords)
    lat = array("f", [coords[refs[i]][0] for i in keep]); lng = array("f", [coords[refs[i]][1] for i in keep])
    adj = [[] for _ in keep]
    for a, b, d in edges:
        if a in new and b in new:
            adj[new[a]].append((new[b], d)); adj[new[b]].append((new[a], d))
    off = array("i", [0]); to = array("i"); w = array("f")
    for lst in adj:
        for v, d in lst:
            to.append(v); w.append(d)
        off.append(len(to))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(b"WLK1" + struct.pack("<II", len(keep), len(to)))
        for arr in (lat, lng, off, to, w):
            f.write(arr.tobytes())
    print(f"узлов {len(keep)}, рёбер {len(to) // 2}, файл {OUT.stat().st_size / 1e6:.1f} МБ, {time.time() - t0:.0f} с")
    return 0


if __name__ == "__main__":
    sys.exit(main())
