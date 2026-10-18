#!/usr/bin/env python3
"""Сжатые выгрузки с Яндекс Недвижимости (data/inbox/ya_chunk*.txt) -> data/inbox/yandex.json для sync_listings.py.
Строка выгрузки: рынок(n|s) | адрес | юнит;юнит;..., юнит: id,площадь,комнат(0 — студия),этаж,этажей,цена,картинка."""
import json, re
from pathlib import Path

INBOX = Path(__file__).resolve().parent.parent / "data" / "inbox"
IMG = "https://avatars.mds.yandex.net/get-realty-offers/%s/app_snippet_large"


def clean_address(a):
    a = re.sub(r"Республика Марий Эл,\s*", "", a)
    a = re.sub(r"Медведевский район,\s*[^,]*сельское поселение,\s*", "", a)
    a = re.sub(r"посёлок городского типа Медведево", "пгт. Медведево", a)
    a = a.replace("село Семёновка", "с. Семёновка").replace("посёлок Руэм", "пос. Руэм")
    if not re.search(r"Йошкар|Медведево|Семёновка|Руэм", a):
        a = "Йошкар-Ола, " + a
    elif a.startswith(("с. Семёновка", "пгт. Медведево", "пос. Руэм")):
        pass
    return a


def complex_name(a):
    m = re.search(r"(?:жилой комплекс|ЖК)\s+([^,]+)", a)
    return "ЖК «%s»" % m.group(1).strip() if m else ""


rows = []
for f in sorted(INBOX.glob("ya_chunk*.txt")):
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        market, addr, units = line.split("|", 2)
        addr_c = clean_address(addr)
        for u in units.split(";"):
            p = u.split(",")
            if len(p) < 6:
                continue
            uid, area, rooms, floor, floors, price = p[:6]
            img = p[6] if len(p) > 6 else ""
            r = int(rooms) if rooms.isdigit() else 1
            label = "студия" if r == 0 else f"{r}-к. квартира"
            rows.append({
                "address": addr_c, "area": float(area), "rooms": -1 if r == 0 else r, "price": int(price),
                "url": f"https://realty.yandex.ru/offer/{uid}/", "item_id": "ya" + uid[-10:], "source": "Яндекс Недвижимость",
                "market": "new" if market == "n" else "secondary", "complex": complex_name(addr),
                "name": f"{label}, {area} м²" + (f", {floor}/{floors} эт." if floor and floors else ""),
                "image_remote": IMG % img if img else "",
            })
(INBOX / "yandex.json").write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
print("объявлений:", len(rows), "адресов:", len({r["address"] for r in rows}))
