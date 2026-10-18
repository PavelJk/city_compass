#!/usr/bin/env python3
"""Сборка папки «Для преподавателя»: все таблицы данных проекта «Городской компас».

    python scripts/export_tables.py              # только выгрузка таблиц из готовых данных сайта
    python scripts/export_tables.py --collect    # сначала обновить данные (объявления, контуры домов), потом выгрузка
    python scripts/export_tables.py --collect --full   # ещё и места из OSM и пешеходный граф (долго, нужен osmium)

Результат:
    Для преподавателя/
        Таблицы/*.csv        — каждая таблица в CSV (UTF-8 с BOM, разделитель «;», открывается в Excel)
        realty.db            — те же таблицы одним файлом SQLite
        schema.sql           — описание таблиц
        load_tables.py       — загрузка CSV в свою базу SQLite (для преподавателя)
        README.txt           — что в какой таблице

Источники: dist/data/*.json, dist/data/walk.bin, data/geocode-cache.json, dist/js/config.js, data/users.db (только структура).
Пользователи и сессии в выгрузку НЕ попадают (пароли, почта) — только пустые таблицы со структурой.
Нужен только стандартный Python 3.8+.
"""
import argparse, csv, json, re, shutil, sqlite3, struct, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "dist" / "data"
OUT = ROOT / "Для преподавателя"
TABLES_DIR = OUT / "Таблицы"

# ---------- описание таблиц: имя -> (описание, [(колонка, тип SQL, пояснение)]) ----------
SCHEMA = {
    "locality": ("Населённые пункты", [("id", "INTEGER PRIMARY KEY", "код"), ("name", "TEXT NOT NULL", "название")]),
    "source": ("Источники объявлений", [("id", "INTEGER PRIMARY KEY", "код"), ("name", "TEXT NOT NULL", "название сайта")]),
    "flat": ("Объявления о продаже квартир", [
        ("id", "INTEGER PRIMARY KEY", "код"), ("url", "TEXT", "ссылка на объявление"), ("name", "TEXT", "заголовок"),
        ("address", "TEXT", "адрес"), ("locality_id", "INTEGER REFERENCES locality(id)", "населённый пункт"),
        ("complex", "TEXT", "жилой комплекс"), ("market", "TEXT", "new — новостройка, secondary — вторичка"),
        ("rooms", "TEXT", "комнатность"), ("area", "REAL", "площадь, м²"), ("price", "INTEGER", "цена, ₽"),
        ("rent", "INTEGER", "аренда, ₽/мес (оценка или из объявлений)"), ("rent_estimated", "INTEGER", "1 — аренда оценена расчётом"),
        ("approx", "INTEGER", "1 — координаты приблизительные (центр улицы)"), ("lat", "REAL", "широта"), ("lng", "REAL", "долгота"),
        ("source_id", "INTEGER REFERENCES source(id)", "источник"), ("photo_shared", "INTEGER", "1 — фото взято из другого объявления в этом доме")]),
    "flat_photo": ("Фотографии объявлений", [
        ("flat_id", "INTEGER REFERENCES flat(id)", "объявление"), ("position", "INTEGER", "порядок"), ("path", "TEXT", "файл фото")]),
    "building": ("Контуры домов и участков на карте", [
        ("id", "INTEGER PRIMARY KEY", "код"),
        ("kind", "TEXT", "outline — контур дома из OSM, plot — участок стройки, synthetic — прямоугольник по адресу")]),
    "building_vertex": ("Вершины контуров", [
        ("building_id", "INTEGER REFERENCES building(id)", "контур"), ("seq", "INTEGER", "порядок вершины"),
        ("lat", "REAL", "широта"), ("lng", "REAL", "долгота")]),
    "building_flat": ("Какие объявления относятся к контуру (дому)", [
        ("building_id", "INTEGER REFERENCES building(id)", "контур"), ("flat_id", "INTEGER REFERENCES flat(id)", "объявление")]),
    "poi_group": ("Группы мест для индекса среды", [
        ("code", "TEXT PRIMARY KEY", "код"), ("label", "TEXT", "название"), ("weight", "INTEGER", "вес группы в индексе среды, %")]),
    "poi_category": ("Категории мест", [
        ("code", "TEXT PRIMARY KEY", "код"), ("label", "TEXT", "название"), ("group_code", "TEXT REFERENCES poi_group(code)", "группа"),
        ("kind", "TEXT", "pos — плюс, neg — минус для жизни рядом"), ("radius_m", "INTEGER", "радиус учёта, м"),
        ("optimum_m", "INTEGER", "расстояние, до которого место считается идеальным, м"), ("severity", "INTEGER", "сила минуса (для neg)")]),
    "poi": ("Места на карте (OpenStreetMap)", [
        ("id", "INTEGER PRIMARY KEY", "код"), ("category", "TEXT REFERENCES poi_category(code)", "категория"),
        ("lat", "REAL", "широта"), ("lng", "REAL", "долгота"), ("name", "TEXT", "название")]),
    "rent_offer": ("Объявления об аренде (для расчёта аренды по дому)", [
        ("id", "INTEGER PRIMARY KEY", "код"), ("address", "TEXT", "адрес"), ("area", "REAL", "площадь, м²"), ("rooms", "INTEGER", "комнат"),
        ("floor", "INTEGER", "этаж"), ("floors", "INTEGER", "этажей в доме"), ("rent", "INTEGER", "аренда, ₽/мес")]),
    "walk_node": ("Узлы пешеходного графа улиц", [
        ("id", "INTEGER PRIMARY KEY", "код узла"), ("lat", "REAL", "широта"), ("lng", "REAL", "долгота")]),
    "walk_edge": ("Рёбра пешеходного графа (ненаправленные, каждое один раз)", [
        ("node_a", "INTEGER REFERENCES walk_node(id)", "узел"), ("node_b", "INTEGER REFERENCES walk_node(id)", "узел"),
        ("length_m", "REAL", "длина, м")]),
    "geocode_cache": ("Кэш определения координат по адресу", [
        ("address", "TEXT PRIMARY KEY", "адрес"), ("lat", "REAL", "широта"), ("lng", "REAL", "долгота")]),
    "model_param": ("Допущения расчёта по умолчанию", [
        ("param", "TEXT PRIMARY KEY", "параметр (вложенные через точку)"), ("value", "TEXT", "значение")]),
    "app_user": ("Пользователи сайта — ТОЛЬКО СТРУКТУРА, данных нет", [
        ("id", "INTEGER PRIMARY KEY", "код"), ("email", "TEXT", "почта"), ("name", "TEXT", "имя"), ("color", "TEXT", "цвет аватара"),
        ("created", "REAL", "время регистрации"), ("settings", "TEXT", "сохранённые настройки (JSON)")]),
    "app_session": ("Сессии входа — ТОЛЬКО СТРУКТУРА, данных нет", [
        ("user_id", "INTEGER REFERENCES app_user(id)", "пользователь"), ("created", "REAL", "создана"), ("expires", "REAL", "действует до")]),
}


def read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def parse_config():
    """Группы и категории мест и допущения из dist/js/config.js (без Node — по тексту)."""
    src = (ROOT / "dist" / "js" / "config.js").read_text(encoding="utf-8")
    src = re.sub(r"//[^\n]*", "", src)

    def block(name):
        m = re.search(r"export const " + name + r"\s*=\s*\{", src)
        if not m:
            return ""
        i, depth = m.end(), 1
        while i < len(src) and depth:
            depth += {"{": 1, "}": -1}.get(src[i], 0)
            i += 1
        return src[m.end():i - 1]

    def fields(s):
        return {k: v.strip().strip("'\"") for k, v in re.findall(r"(\w+):\s*('[^']*'|\"[^\"]*\"|[-\d.]+)", s)}

    groups, cats = [], []
    for code, body in re.findall(r"(\w+):\s*\{([^{}]*)\}", block("GROUPS")):
        f = fields(body)
        groups.append((code, f.get("label", ""), int(float(f.get("w", 0)))))
    for code, body in re.findall(r"(\w+):\s*\{([^{}]*)\}", block("CATS")):
        f = fields(body)
        cats.append((code, f.get("label", ""), f.get("group"), f.get("kind"), f.get("R"), f.get("opt"), f.get("sev")))

    params = []
    a = block("DEFAULT_ASSUMPTIONS").replace("{ ...GROUP_W }", "{}")
    try:
        js = re.sub(r"([{,]\s*)([A-Za-z_]\w*)\s*:", r'\1"\2":', "{" + a)
        js = re.sub(r"'([^']*)'", lambda m: json.dumps(m.group(1), ensure_ascii=False), js)
        js = re.sub(r",\s*([}\]])", r"\1", js + "}")
        obj = json.loads(js)

        def walk(o, pre=""):
            for k, v in o.items():
                key = pre + k
                if isinstance(v, dict):
                    walk(v, key + ".")
                else:
                    params.append((key, json.dumps(v, ensure_ascii=False)))
        walk(obj)
    except Exception as e:  # допущения — вспомогательная таблица, не роняем выгрузку
        print("  допущения не разобраны:", e)
    return groups, cats, params


def build_rows():
    T = {k: [] for k in SCHEMA}
    L = (read_json(DATA / "listings.json", {}) or {}).get("listings", [])
    loc, src = {}, {}
    url_id = {}
    for i, f in enumerate(L, 1):
        lid = loc.setdefault(f.get("locality") or "", len(loc) + 1)
        sid = src.setdefault(f.get("source") or "", len(src) + 1)
        url_id[f.get("url")] = i
        T["flat"].append((i, f.get("url"), f.get("name"), f.get("address"), lid, f.get("complex"), f.get("market"), f.get("rooms"),
                          f.get("area"), f.get("price"), f.get("rent"), int(bool(f.get("rentEstimated"))), int(bool(f.get("approx"))),
                          f.get("lat"), f.get("lng"), sid, int(bool(f.get("photoShared")))))
        for k, p in enumerate(f.get("photos") or ([f["photo"]] if f.get("photo") else []), 1):
            T["flat_photo"].append((i, k, p))
    T["locality"] = [(i, n) for n, i in loc.items()]
    T["source"] = [(i, n) for n, i in src.items()]

    for bi, b in enumerate(read_json(DATA / "buildings.json", []) or [], 1):
        T["building"].append((bi, "synthetic" if b.get("s") else "plot" if b.get("p") else "outline"))
        for k, (la, lo) in enumerate(b.get("r", []), 1):
            T["building_vertex"].append((bi, k, la, lo))
        for u in b.get("f", []):
            if u in url_id:
                T["building_flat"].append((bi, url_id[u]))

    groups, cats, params = parse_config()
    T["poi_group"], T["poi_category"], T["model_param"] = groups, cats, params
    pts = (read_json(DATA / "poi.json", {}) or {}).get("points", [])
    T["poi"] = [(i, p[0], p[1], p[2], p[3] if len(p) > 3 else "") for i, p in enumerate(pts, 1)]

    rents = (read_json(DATA / "rents.json", {}) or {}).get("rents", [])
    T["rent_offer"] = [(i, *r[:6]) for i, r in enumerate(rents, 1)]

    walk = DATA / "walk.bin"
    if walk.exists():
        raw = walk.read_bytes()
        if raw[:4] == b"WLK1":
            n, e2 = struct.unpack_from("<ii", raw, 4)
            o = 12
            lat = struct.unpack_from(f"<{n}f", raw, o); o += 4 * n
            lng = struct.unpack_from(f"<{n}f", raw, o); o += 4 * n
            off = struct.unpack_from(f"<{n + 1}i", raw, o); o += 4 * (n + 1)
            adj = struct.unpack_from(f"<{e2}i", raw, o); o += 4 * e2
            w = struct.unpack_from(f"<{e2}f", raw, o)
            T["walk_node"] = [(i, round(lat[i], 6), round(lng[i], 6)) for i in range(n)]
            for a in range(n):
                for k in range(off[a], off[a + 1]):
                    if a < adj[k]:
                        T["walk_edge"].append((a, adj[k], round(w[k], 1)))

    gc = read_json(ROOT / "data" / "geocode-cache.json", {}) or {}
    T["geocode_cache"] = [(a, v[0], v[1]) for a, v in gc.items() if isinstance(v, list) and len(v) >= 2 and v[0] is not None]
    return T


def write_all(T):
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    for old in TABLES_DIR.glob("*.csv"):
        old.unlink()
    db_path = OUT / "realty.db"
    if db_path.exists():
        db_path.unlink()
    db = sqlite3.connect(db_path)
    ddl = []
    for name, (_, cols) in SCHEMA.items():
        sql = f"CREATE TABLE {name} (\n  " + ",\n  ".join(f"{c} {t}" for c, t, _ in cols) + "\n);"
        db.execute(sql)
        ddl.append("-- " + SCHEMA[name][0] + "\n" + sql)
    for name, (_, cols) in SCHEMA.items():
        rows = T[name]
        names = [c for c, _, _ in cols]
        if rows:
            db.executemany(f"INSERT INTO {name} VALUES ({','.join('?' * len(names))})", rows)
        with open(TABLES_DIR / f"{name}.csv", "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(names)
            w.writerows(rows)
    db.commit()
    db.close()
    (OUT / "schema.sql").write_text("\n\n".join(ddl) + "\n", encoding="utf-8")
    shutil.copyfile(ROOT / "scripts" / "teacher_import.py", OUT / "load_tables.py")

    lines = ["ГОРОДСКОЙ КОМПАС — таблицы данных проекта", "",
             "Папка «Таблицы» — каждая таблица отдельным CSV (UTF-8, разделитель «;»).",
             "realty.db — те же таблицы одним файлом SQLite, schema.sql — описание.",
             "load_tables.py — загрузка CSV в свою базу SQLite: python load_tables.py [--db файл.db] [--check]", "",
             f"{'Таблица':<18}{'Строк':>9}   Описание"]
    for name, (desc, cols) in SCHEMA.items():
        lines.append(f"{name:<18}{len(T[name]):>9}   {desc}")
    lines += ["", "Колонки:"]
    for name, (desc, cols) in SCHEMA.items():
        lines += ["", f"{name} — {desc}"] + [f"  {c:<14}{t:<34}{d}" for c, t, d in cols]
    lines += ["", "Связи: flat → locality, source; flat_photo → flat; building_vertex, building_flat → building, flat;",
              "poi → poi_category → poi_group; walk_edge → walk_node.",
              "Расчёты (аренда, доходность, индекс среды, оценка) считаются на сайте по этим таблицам и в них не хранятся."]
    (OUT / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {n: len(r) for n, r in T.items()}


def run(*args):
    print(">", " ".join(args))
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--collect", action="store_true", help="сначала обновить данные: объявления и контуры домов")
    ap.add_argument("--full", action="store_true", help="вместе с --collect: ещё и места из OSM и пешеходный граф (нужен osmium)")
    a = ap.parse_args()
    if a.collect:
        run("scripts/sync_listings.py")
        run("scripts/build_buildings.py")
        if a.full:
            run("scripts/build_poi_from_pbf.py")
            run("scripts/build_walk_graph.py")
    counts = write_all(build_rows())
    print("Готово:", OUT)
    for n, c in counts.items():
        print(f"  {n:<16}{c:>8}")


if __name__ == "__main__":
    main()
