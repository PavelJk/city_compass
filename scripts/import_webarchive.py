#!/usr/bin/env python3
"""Safari .webarchive (Telegram/«Сохранить как веб-архив») -> HTML + папка с картинками в data/inbox/.
Использование: python scripts/import_webarchive.py <файл> <имя>   ->  data/inbox/<имя>.html и <имя>_files/"""
import plistlib, re, sys
from pathlib import Path
from urllib.parse import unquote, urlparse

INBOX = Path(__file__).resolve().parent.parent / "data" / "inbox"


def main(src, name):
    arc = plistlib.loads(Path(src).read_bytes())
    main_res = arc["WebMainResource"]
    html = main_res["WebResourceData"].decode(main_res.get("WebResourceTextEncodingName") or "utf-8", errors="ignore")
    files = INBOX / f"{name}_files"
    files.mkdir(parents=True, exist_ok=True)
    saved = 0
    for r in arc.get("WebSubresources", []):
        url = r.get("WebResourceURL", "")
        if not str(r.get("WebResourceMIMEType", "")).startswith("image/") or "img.avito.st" not in url:
            continue
        base = Path(unquote(urlparse(url).path)).name  # 1.xxxx.yyyy — как в «Сохранить страницу целиком»
        (files / base).write_bytes(r["WebResourceData"])
        # в src подставляем локальный путь, srcset с удалёнными адресами остаётся запасным вариантом
        html = html.replace(f'src="{url}"', f'src="./{name}_files/{base}"')
        saved += 1
    (INBOX / f"{name}.html").write_text(html, encoding="utf-8")
    print(f"{name}.html: {len(html) // 1024} КБ, картинок {saved}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
