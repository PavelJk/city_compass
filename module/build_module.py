#!/usr/bin/env python3
"""Собирает единый файл модуля realty_module.py: шаблон + категории мест (из dist/js/config.js) + встроенные данные
(объявления из dist/data/listings.json и места из dist/data/poi.json). Запуск: python module/build_module.py"""
import base64, json, re, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "realty_module.py"


def parse_cats():
    src = (ROOT / "dist" / "js" / "config.js").read_text(encoding="utf-8")
    block = src[src.index("export const CATS = {"):]
    block = block[:block.index("\n};")]
    cats = {}
    for m in re.finditer(r"^\s{2}(\w+):\s*\{(.*?)\},?\s*$", block, re.M):
        body = m.group(2)
        get = lambda k: (re.search(rf"\b{k}:\s*'?([^',}}]+)'?", body) or [None, None])[1]
        c = {"label": re.search(r"label:\s*'([^']*)'", body).group(1), "kind": get("kind"), "R": int(get("R")), "opt": int(get("opt") or 0)}
        if c["kind"] == "pos":
            c["group"] = get("group")
        else:
            c["sev"] = float(get("sev")); c["group"] = None; c["opt"] = 0
        cats[m.group(1)] = c
    return cats


def main():
    listings = json.loads((ROOT / "dist" / "data" / "listings.json").read_text(encoding="utf-8"))["listings"]
    poi = json.loads((ROOT / "dist" / "data" / "poi.json").read_text(encoding="utf-8"))["points"]
    flats = []
    for l in listings:
        m = re.search(r"(\d+)\s*/\s*(\d+)\s*эт", l.get("name", ""))
        flats.append({"id": l.get("url") or f'{l["address"]}|{l["area"]}|{l["price"]}', "address": l["address"], "locality": l["locality"],
                      "market": l.get("market", "secondary"), "rooms": l["rooms"], "area": l["area"],
                      "floor": int(m.group(1)) if m else None, "floors": int(m.group(2)) if m else None, "price": l["price"],
                      "rent": None if l.get("rentEstimated", True) else l["rent"], "lat": l["lat"], "lon": l["lng"],
                      "url": l.get("url", ""), "source": l.get("source", "")})
    seed = base64.b64encode(zlib.compress(json.dumps({"flats": flats, "poi": poi}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)).decode()
    chunks = [seed[i:i + 100] for i in range(0, len(seed), 100)]
    seed_py = "(\n" + "".join(f'    "{c}",\n' for c in chunks) + ")"
    tpl = (Path(__file__).resolve().parent / "realty_module.template.py").read_text(encoding="utf-8")
    cats = parse_cats()
    out = tpl.replace("__CATS__", json.dumps(cats, ensure_ascii=False, indent=4).replace("null", "None")).replace("__SEED__", seed_py)
    OUT.write_text(out, encoding="utf-8")
    print(f"категорий {len(cats)}, объявлений {len(flats)}, мест {len(poi)}, файл {OUT.stat().st_size / 1024:.0f} КБ")


if __name__ == "__main__":
    main()
