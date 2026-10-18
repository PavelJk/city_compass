#!/usr/bin/env python3
"""Загрузка таблиц «Городского компаса» из CSV в базу SQLite.

Лежит рядом с папкой «Таблицы» и файлом schema.sql. Нужен только Python 3.8+ (стандартная библиотека).

    python load_tables.py                      # создаст realty_new.db рядом со скриптом
    python load_tables.py --db путь/к/базе.db  # или загрузит в указанную базу
    python load_tables.py --check              # только проверить CSV и связи, ничего не создавая

Если таблица с таким именем в базе уже есть, она пересоздаётся (остальные таблицы базы не трогаются).
Готовый файл realty.db с теми же таблицами лежит рядом — этот скрипт нужен, чтобы загрузить данные в свою базу.
"""
import argparse, csv, re, sqlite3, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TABLES = HERE / "Таблицы"
SCHEMA = HERE / "schema.sql"


def read_schema():
    """schema.sql -> {имя таблицы: текст CREATE TABLE}, в порядке следования."""
    text = SCHEMA.read_text(encoding="utf-8")
    return {m.group(1): m.group(0) for m in re.finditer(r"CREATE TABLE (\w+) \(.*?\n\);", text, flags=re.S)}


def read_csv(name):
    with open(TABLES / f"{name}.csv", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    return rows[0], rows[1:]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(HERE / "realty_new.db"), help="файл базы SQLite (по умолчанию realty_new.db)")
    ap.add_argument("--check", action="store_true", help="только проверить, ничего не создавать")
    a = ap.parse_args()

    if not SCHEMA.exists() or not TABLES.exists():
        sys.exit("Рядом со скриптом должны лежать schema.sql и папка «Таблицы».")
    schema = read_schema()
    db = sqlite3.connect(":memory:" if a.check else a.db)
    if not a.check:
        for name in reversed(list(schema)):
            db.execute(f"DROP TABLE IF EXISTS {name}")
    for sql in schema.values():
        db.execute(sql)

    print(f"{'таблица':<18}{'строк':>9}")
    for name in schema:
        header, rows = read_csv(name)
        cols = [r[1] for r in db.execute(f"PRAGMA table_info({name})")]
        if header != cols:
            sys.exit(f"{name}.csv: колонки {header} не совпадают со схемой {cols}")
        data = [tuple(None if v == "" else v for v in r) for r in rows]
        db.executemany(f"INSERT INTO {name} VALUES ({','.join('?' * len(cols))})", data)
        print(f"{name:<18}{len(data):>9}")

    bad = db.execute("PRAGMA foreign_key_check").fetchall()
    print("\nПроверка связей:", "ошибок нет" if not bad else f"{len(bad)} строк без пары, например {bad[:3]}")
    if not a.check:
        db.commit()
        print("База готова:", a.db)

    print("\nПример: 5 самых дорогих за м² новостроек")
    q = """SELECT f.address, f.rooms, f.area, f.price, ROUND(f.price / f.area) AS rub_m2
           FROM flat f WHERE f.market = 'new' ORDER BY rub_m2 DESC LIMIT 5"""
    for r in db.execute(q):
        print("  ", " | ".join(str(x) for x in r))
    db.close()


if __name__ == "__main__":
    main()
