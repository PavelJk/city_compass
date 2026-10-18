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
CATS = {
    "transport": {
        "label": "Остановка",
        "kind": "pos",
        "R": 600,
        "opt": 80,
        "group": "transport"
    },
    "tram": {
        "label": "Трамвайная остановка",
        "kind": "pos",
        "R": 600,
        "opt": 80,
        "group": "transport"
    },
    "rail_station": {
        "label": "Ж/д станция",
        "kind": "pos",
        "R": 1500,
        "opt": 500,
        "group": "transport"
    },
    "bus_station": {
        "label": "Автовокзал",
        "kind": "pos",
        "R": 1500,
        "opt": 250,
        "group": "transport"
    },
    "bike_rent": {
        "label": "Прокат велосипедов и самокатов",
        "kind": "pos",
        "R": 600,
        "opt": 0,
        "group": "transport"
    },
    "cycleway": {
        "label": "Велодорожка",
        "kind": "pos",
        "R": 400,
        "opt": 0,
        "group": "transport"
    },
    "parking": {
        "label": "Парковка",
        "kind": "pos",
        "R": 500,
        "opt": 0,
        "group": "transport"
    },
    "school": {
        "label": "Школа",
        "kind": "pos",
        "R": 1100,
        "opt": 300,
        "group": "education"
    },
    "kindergarten": {
        "label": "Детский сад",
        "kind": "pos",
        "R": 900,
        "opt": 200,
        "group": "education"
    },
    "extra_edu": {
        "label": "Допобразование",
        "kind": "pos",
        "R": 1800,
        "opt": 0,
        "group": "education"
    },
    "college": {
        "label": "Вуз / колледж",
        "kind": "pos",
        "R": 3000,
        "opt": 300,
        "group": "education"
    },
    "clinic": {
        "label": "Поликлиника / медцентр",
        "kind": "pos",
        "R": 1500,
        "opt": 300,
        "group": "health"
    },
    "hospital": {
        "label": "Больница",
        "kind": "pos",
        "R": 2000,
        "opt": 500,
        "group": "health"
    },
    "dentist": {
        "label": "Стоматология",
        "kind": "pos",
        "R": 1000,
        "opt": 0,
        "group": "health"
    },
    "pharmacy": {
        "label": "Аптека",
        "kind": "pos",
        "R": 700,
        "opt": 0,
        "group": "health"
    },
    "grocery": {
        "label": "Продукты",
        "kind": "pos",
        "R": 500,
        "opt": 0,
        "group": "shops"
    },
    "supermarket": {
        "label": "Супермаркет",
        "kind": "pos",
        "R": 1000,
        "opt": 0,
        "group": "shops"
    },
    "bakery": {
        "label": "Пекарня",
        "kind": "pos",
        "R": 700,
        "opt": 0,
        "group": "shops"
    },
    "clothes": {
        "label": "Одежда и обувь",
        "kind": "pos",
        "R": 1500,
        "opt": 0,
        "group": "shops"
    },
    "electronics": {
        "label": "Электроника",
        "kind": "pos",
        "R": 1500,
        "opt": 0,
        "group": "shops"
    },
    "furniture": {
        "label": "Мебель и дом",
        "kind": "pos",
        "R": 1800,
        "opt": 0,
        "group": "shops"
    },
    "diy": {
        "label": "Стройматериалы",
        "kind": "pos",
        "R": 2000,
        "opt": 0,
        "group": "shops"
    },
    "shop_other": {
        "label": "Другие магазины",
        "kind": "pos",
        "R": 800,
        "opt": 0,
        "group": "shops"
    },
    "mall": {
        "label": "Торговый центр",
        "kind": "pos",
        "R": 3000,
        "opt": 500,
        "group": "shops"
    },
    "market": {
        "label": "Рынок",
        "kind": "pos",
        "R": 1500,
        "opt": 400,
        "group": "shops"
    },
    "cafe": {
        "label": "Кафе и рестораны",
        "kind": "pos",
        "R": 1000,
        "opt": 0,
        "group": "shops"
    },
    "services": {
        "label": "Бытовые услуги",
        "kind": "pos",
        "R": 800,
        "opt": 0,
        "group": "shops"
    },
    "pvz": {
        "label": "Пункт выдачи заказов",
        "kind": "pos",
        "R": 700,
        "opt": 0,
        "group": "shops"
    },
    "park": {
        "label": "Парк",
        "kind": "pos",
        "R": 800,
        "opt": 100,
        "group": "green"
    },
    "square": {
        "label": "Сквер",
        "kind": "pos",
        "R": 500,
        "opt": 0,
        "group": "green"
    },
    "playground": {
        "label": "Детская площадка",
        "kind": "pos",
        "R": 300,
        "opt": 0,
        "group": "green"
    },
    "forest": {
        "label": "Лес",
        "kind": "pos",
        "R": 1000,
        "opt": 0,
        "group": "green"
    },
    "water": {
        "label": "Река / озеро",
        "kind": "pos",
        "R": 1000,
        "opt": 50,
        "group": "green"
    },
    "beach": {
        "label": "Пляж",
        "kind": "pos",
        "R": 1200,
        "opt": 0,
        "group": "green"
    },
    "promenade": {
        "label": "Набережная",
        "kind": "pos",
        "R": 1000,
        "opt": 0,
        "group": "green"
    },
    "sport": {
        "label": "Фитнес и спорткомплекс",
        "kind": "pos",
        "R": 1500,
        "opt": 150,
        "group": "leisure"
    },
    "pitch": {
        "label": "Спортивная площадка",
        "kind": "pos",
        "R": 800,
        "opt": 0,
        "group": "leisure"
    },
    "culture": {
        "label": "Театр, кино, библиотека",
        "kind": "pos",
        "R": 2000,
        "opt": 0,
        "group": "leisure"
    },
    "museum": {
        "label": "Музей",
        "kind": "pos",
        "R": 2000,
        "opt": 0,
        "group": "leisure"
    },
    "attraction": {
        "label": "Достопримечательность",
        "kind": "pos",
        "R": 1500,
        "opt": 0,
        "group": "leisure"
    },
    "fun": {
        "label": "Досуг и развлечения",
        "kind": "pos",
        "R": 1500,
        "opt": 0,
        "group": "leisure"
    },
    "bank": {
        "label": "Банк / банкомат",
        "kind": "pos",
        "R": 800,
        "opt": 0,
        "group": "public"
    },
    "post": {
        "label": "Почта",
        "kind": "pos",
        "R": 1000,
        "opt": 0,
        "group": "public"
    },
    "mfc": {
        "label": "МФЦ",
        "kind": "pos",
        "R": 3000,
        "opt": 0,
        "group": "public"
    },
    "public": {
        "label": "Госучреждение",
        "kind": "pos",
        "R": 1800,
        "opt": 0,
        "group": "public"
    },
    "office": {
        "label": "Офисы и работодатели",
        "kind": "pos",
        "R": 1500,
        "opt": 0,
        "group": "public"
    },
    "bar": {
        "label": "Бар / паб",
        "kind": "neg",
        "R": 350,
        "opt": 0,
        "sev": 3.0,
        "group": None
    },
    "nightclub": {
        "label": "Ночной клуб",
        "kind": "neg",
        "R": 500,
        "opt": 0,
        "sev": 4.0,
        "group": None
    },
    "casino": {
        "label": "Казино / ставки",
        "kind": "neg",
        "R": 250,
        "opt": 0,
        "sev": 1.5,
        "group": None
    },
    "alcohol": {
        "label": "Алкомаркет",
        "kind": "neg",
        "R": 250,
        "opt": 0,
        "sev": 2.0,
        "group": None
    },
    "industrial": {
        "label": "Промзона / завод",
        "kind": "neg",
        "R": 900,
        "opt": 0,
        "sev": 6.0,
        "group": None
    },
    "warehouse": {
        "label": "Склады",
        "kind": "neg",
        "R": 250,
        "opt": 0,
        "sev": 1.5,
        "group": None
    },
    "airport": {
        "label": "Аэропорт",
        "kind": "neg",
        "R": 3000,
        "opt": 0,
        "sev": 6.0,
        "group": None
    },
    "railway": {
        "label": "Железная дорога",
        "kind": "neg",
        "R": 350,
        "opt": 0,
        "sev": 3.0,
        "group": None
    },
    "highway": {
        "label": "Магистраль",
        "kind": "neg",
        "R": 250,
        "opt": 0,
        "sev": 4.0,
        "group": None
    },
    "waste": {
        "label": "Мусор / полигон",
        "kind": "neg",
        "R": 1500,
        "opt": 0,
        "sev": 6.0,
        "group": None
    },
    "sewage": {
        "label": "Очистные",
        "kind": "neg",
        "R": 1200,
        "opt": 0,
        "sev": 6.0,
        "group": None
    },
    "fuel": {
        "label": "АЗС",
        "kind": "neg",
        "R": 200,
        "opt": 0,
        "sev": 2.0,
        "group": None
    },
    "fuel_depot": {
        "label": "Нефтебаза / ГСМ",
        "kind": "neg",
        "R": 700,
        "opt": 0,
        "sev": 4.0,
        "group": None
    },
    "powerline": {
        "label": "ЛЭП",
        "kind": "neg",
        "R": 150,
        "opt": 0,
        "sev": 2.0,
        "group": None
    },
    "substation": {
        "label": "Подстанция",
        "kind": "neg",
        "R": 300,
        "opt": 0,
        "sev": 3.0,
        "group": None
    },
    "powerplant": {
        "label": "ТЭЦ / электростанция",
        "kind": "neg",
        "R": 1000,
        "opt": 0,
        "sev": 5.0,
        "group": None
    },
    "construction": {
        "label": "Стройка",
        "kind": "neg",
        "R": 300,
        "opt": 0,
        "sev": 2.0,
        "group": None
    },
    "cemetery": {
        "label": "Кладбище",
        "kind": "neg",
        "R": 300,
        "opt": 0,
        "sev": 1.5,
        "group": None
    },
    "stadium": {
        "label": "Стадион",
        "kind": "neg",
        "R": 500,
        "opt": 0,
        "sev": 2.0,
        "group": None
    },
    "fire": {
        "label": "Пожарная часть",
        "kind": "neg",
        "R": 250,
        "opt": 0,
        "sev": 1.5,
        "group": None
    },
    "ambulance": {
        "label": "Скорая помощь",
        "kind": "neg",
        "R": 250,
        "opt": 0,
        "sev": 2.0,
        "group": None
    },
    "prison": {
        "label": "СИЗО / колония",
        "kind": "neg",
        "R": 800,
        "opt": 0,
        "sev": 3.0,
        "group": None
    },
    "wetland": {
        "label": "Болото / подтопление",
        "kind": "neg",
        "R": 300,
        "opt": 0,
        "sev": 1.5,
        "group": None
    }
}
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
_SEED = (
    "eNrUveuSHceVHvoqO/Bjxo4goLxfdH7N2B5bDs94wtL5cWLoUEBkc4gQSDAagDQ6DkfgxssMKREgMJIGokgC4kiK45CEWxPNBroR",
    "4SfY/Qp+kpO5cq2srKrM2ruxuyDIsjQkUFW7Ki8r1/rWt771P068cfb0hfMnvvl3/+PEmddPfPPEmxcuvHP+m9/4xg9/+MNTp39w",
    "5sK5U9sXv/Gjc+ff/P7p7ZPnzp7+xvd/cHr7wpntH31DnPz+qe/iv53+rnb2u299V3Dz3a0Lp77ruOBcKC7tiVdOnH799e2t8+E3",
    "Tiz/ZXlw+MFyb3nv8NLJ5WfLJ8t7ryyWv1o+ObVYfr68t9w/vLbcDX96sHwAf/Po1IKr8ISz5147ffbMhR/VHxEueOv09ve3LoS/",
    "fnvrh+Fft8+deyv+njgZLjxYPl3un4rvsb11+sQ3tTtlXwlffe7c9olvCvyncDE3r5x4Z/vMa1snvmmNNIKx8Jytt8ND37549mx4",
    "h9PhH7U5ZQRXzov4Um+f+Kayp5xnwmj9yomL22fnGcDz5y5ux/c6sbweBmb38Mry4MT/fOXIE6Z6v+dV+j2Rfk8xI7V3Sq09YZ+E",
    "kX283F/uHF5e7oSpuwyXfRz+/iucxK/DDMbh32AGVWUGvWrMoMgzyKXQxjSnUErOeDmDzjF59Alce0BnmcCwPnz4Qc65Sr/IGPfO",
    "Or3Onrt7eCnst73DK4vlnTCDl8L8XT28BHO4G+btlcXh5cMrh5dOLeQxT15461M+zx7nxfSpbvq400o3p0+HDzWqmz+vjebCbDqB",
    "kwN6TFPIe7+ovIw/yIpNH/7jGfujWk1emTblT8lu1ljVbJqw5NX8ZnP9ITymOZP9bc7D7xna5cILJ8OXiZfLbMqa2eSnWJ5CUzeb",
    "wio9u9lcdzzn2XIq/Jwvd7gwXJqXxWRW954qJs5XDabhxrv57eW6QznLxnNWhN/TxUY32ljzx7WVtY3m7CmR50tXTaV3Wig7u6lc",
    "ewDn2Wo6OkQ2O0RCayGM4i+XqazuOF14mLZqKuN6Z3NbyrXHc575M/FoVR73t3LKMb7W9N05BTYyDGqYNthre/HPD6/CtH4a/iRO",
    "3qPDG2Ei99OUkvH0g6mEx4QL82OOOJOm8FtUN5O+M52a+3DeNCZSOWsLwxkGnzu/8UQ2B/aY5rEfWRoW1w1PP2eDaxTOA8PW8Vg+",
    "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",
    "TMZtzJTU/xBiebExTbI5hjOlC3ivSjUcq349Bd2fhSm6sXw8Iim4uXIFfBNFCq6EKI85E8mSm+cKWoM3G9HOicIUC6W5YUbz5yTa",
    "HYPYS51o5+oN29Yn2gUPr5wsHr70OIh2zdGbZ28Bry9nHqQzxkUVved2IuU8Skqy5EXWMzdmOkKLWGHpQyqvNvYhJ0ZvHh9S84I1",
    "K6W1gq8lnfqidUS0LkxhXcqR6RetI9IevVkmS8gSqg7hYDgijVPr7ywgJLzbZ7HOUykqZB3+KIzhdDhteqVqSsjNpQ7awzePdiNI",
    "YfgcDkaDHqLB9cHhn8GhdRVL548twVZVbmSy0b+LFQ2E9JTOgbCsTM44F4I2ubF0Y3sMZ8qIlrkgL4Nny45AEv9X0Cq7h+HwvWNx",
    "4Rv50BWZtGm/UEjTEzpwTrHNUy+tsZsn6AKwhZpuCM+l4p6t5cGHmBggix6Vbp5sSx+pqkoryWmyj+1zs8Ke2lzypTV08yRbIFxw",
    "eQtrZa3xRwAVV/CMOZuHaGzK2MtVLaKdlMWSwVKV/qEMHsfGyMbEaM5jEHkveHCxdnEti7i8HUXLgjWMtjBOYFQDH6df3Ey5ab4q",
    "FpuGFJUyzPVBKb954Nwcy3kaBaUWN/noFDI4UfIo+2639BP1LLvMNjQNyl22Iu8ibK8vQrBmG1NC2kM3k0RqPDkl6frLcBhrYY+S",
    "jY4Bc/jfdztPkc8lkVp1PDrscLo/dvC5e31jlPN+88LP1vDNlNWMfo7JEbqQXssjkQeOe1810pmyphNdZsjUC9hXa4/djPKAucZU",
    "MxGrtNhzSG8qPr8kYL1gcDKPKaLyW6+a6bmK39cdtXnOKVbq5joe/uP5bIJKeg5mo2Wr5IinDzEVtRxdr8haPlf36zVHdh4unC2Z",
    "dz4cmtbrY1BTUnMJqBq7qimTmZ614BaUiAfncmOKTnMQ5yF8AFky+zlKKSbsEeasglCpeRgfqj5VJVhvVjgePYc+4r+b6/E0h28e",
    "N1GXRTo8fIOUev2yT+J1fFyA9TMJ6etVJU5ay0nUI1LTyp3ljd9cibM5fvPx9UVWkeTO6uhSvfR9KkS1T8UKjulsfSqqAziTr1hq",
    "/nAvo445k8dBMZ1LPFUWVO6qUoialrvysqRNORfpAps7j61hnMcmQrOgLF8dlohnR+mP9Yvg/t0P/33U9RaZCbJn9Z6Cpfg3C5us",
    "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",
    "daUFj2Qo2Qm/DogJyNKXCTRoomtDRVmPKXTPKXhIqu9xvTwC+BkSGPFrskxYrlUfnfm5qlImCgMYvrgxnwCe/SlQhQ/gwY2wCEVS",
    "hABazs0KNF40XEmUz11MvvY0vVC/O7wJq5T2XJ6kQ63oF1MqPFDVMygWA6f42Un4vGeVLUO1zB6aAEMPpt6WGfTDQpzDaKwWHgpK",
    "XuqpEw1KyREzNaml6UDhe2S5WDq7rCnUbFZqV2uGLbM0YhfoQCcJLQDpgwNtF5Bk+AmEXF83oieBTYajJpfHnm5PB9Z8SK7Hxi2c",
    "a2w9H+zapSp3yGbSDoplJQmH/T9fflbfbZQ4Ax5UTxVtpZYUCW2G17I9NRuSjGxDtAwz5jpVfzQg2qLlBqa/WapvvQ1uQxSHudxo",
    "3EK1GZaj5vUHizHGP2qB6GxRaP5L8Gt2Uv3HAj7nCewkcKsW31h0mTYs+ENbSryf+/X8mcbqMMdFlXXi0fVl2qSapy9jMjOS35Fq",
    "B9AzBglIw3zjtQ1uLntCoQ4QSzKrn1KXp/hRH+YlV7QjsuTPdXT5YtoEVm95brJG+SmgLMQebrCvP0QRsd2MVZVhhEcBsXAC20ps",
    "jNK4XsBWGv016XkJn1tS9x6OyU4opKv8tUc1Ip1JBP27BT28crdiPjfI4LW/1pTQVHo8bpZTv9RI4Pr2O6e3T4L5u9ZIgQnCe23K",
    "jzYWfAFYeZKshq17C0+IqA/0MYg0hxl6N/7L8M3Qfw+nQGRv/+XW+QtgKEABnLzFvsCCp8otrWTnKS4mRdTp8Egsh7qYUIXTZEhT",
    "JHWCy5LK75z74dZ22Idv53RyOstsMOd8PPqS9DSS1FOxWiG+id9aqbZLSz2q0vXraIIlrE+a5rg8rRSpeCEd/nXt2hDLYK4i5uhr",
    "eXckExnPBBLzHpcF6YkytIMCvePmqqgsYQFUqDeXtCaNsOXGU4fs1CExxGEPFuG0+Wz5SeWgIPnwVKI9yFR+mjOVgxpJ5BEokIXr",
    "k6OGFTkOFbd54n/8Noz9x6AdNAKQSRGTd+XtJdanSSNANljVlfbLgqjYbp2jjFOkZ3nHKEjO2bB7jnYK9RAtFwm2uxmuvx05h1C1",
    "EOzBXr6tz6SkJpreatIY20u/kbz2D5pglmCk3g7GB9yAK5FoBgdIzNrWGOmiE57udDcHV1jSMfcdM7iiNyiy3nnE6/7DP7yzvXX+",
    "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",
    "hOVUUque3HLHpldeMvjgcyDix2PzfttZhmSObuEJmWclrSePV6By+4iCsdZKIlOYjprin/Th3GdHN09KXa6hdhw0fQJh6WH/S4LX",
    "z8KxWjLpGJ7rk6MPcQEZrNzyFYC90kGS5Ie7ly88v3NuG5eMX8aD1MEKlsVfpnrh6K04qolaVkbFDQH9kw6JP/eg1C4cySx5lolE",
    "KUWE+KYc2sR/x3r2PSKdEkxGViM2abkUGeymxoLq9H1Qr1ylcbEbkOlODMjRI+NasmO4R7rln7d82wKHn5jEXNe3NGxnWK63z24A",
    "bwJLknijLSFLB0tKWidWKRZvA9b76FaZHDD8TFdirSqyDTn2lTqO2UHkGag9udxI0ZwZ90LNaK3ZJ7wTanqbDS1+Yg/1XTozq4tl",
    "XxFv/XxT9XLQsIdBZ6kAuE6oVzL0G6341jePDzUSWJ/1Hmh9nv8eOs0vAj2C/wQqG3tE1Gh1oYANU1SzutBi5EUSi9/cZeSMOKeL",
    "Z6U0NN64CQpHb6WUy0CPQBO5xjXolBCRJMe9BvMBOqmPfw3PzyKOeQ3BJz8PFd5bT9+GzfMBcVIOMhOgaU+ZXj7gQP4A6oNXSMSr",
    "kUgTlLLwXgHYcwRDiKKzb/I5oD7xPSUto8GLHikL0BkHjhnVnp50twm1NLtnpJcz4KWR+5MczCcttpEHHTkruJaDqTbkhaasw/Py",
    "wdPXTpLl0JPp9QhQoAZRmCf9WeXNLNGYxKkVQ3WCi8Dev/+7sSgxFyX7fYhM58YnOMD0P0FcP5zU4tGTvFxYWyeXQjasOwxT/qN6",
    "yKEpbNGYfP09TtdVZgP4uOoAlA6AEpMCjyDQfZU2772nr1c/OgtkqplrnQksu+w1oZE3dnFdx6Z7Jo3JsedKtVv0S4duuNXO7GbY",
    "tk8LDBoAtwsCZtUowwh6BwYFdcsOufo7BVZRJB9E/q+AZAjkNX/bivQMH98ImxddIsBR9cEKhksy2X76z5XubD2LjPLGL+beG1T6",
    "CjiN/4SyjhDgvlG1wtWBTvZGb1ZQzkTlAzmxRK5iQ0pa8ICHbeC3uQ1tOfCTf6Xq0JqOCn0HK3LDvUth53i6CJotwazrMwiNd8RQ",
    "CYaQs3sQq4FJJi3kqXHSafYGTiy1xoN4lmZyMvEfqlKfaxulS0nOl0WZ79al1jbKJL0YzUFTvKo/2myTm6EFApaHTla0xSVLpkb7",
    "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",
    "WppBzYDoydf9WlIVXNoTaMakrgzYba2A0Mp6tWvM0qjJwo4rx4SSFAbzz2rb08R1rDWb609AscqxzihMqGYll2LN0omkTLKDAMDt",
    "RBwv2mVJzDmbdZLR53W5Tiid8RSdlAuxcS/dCTqpMCx82U4iZChfrpNsgO/xkp1cZmLJcXeJiY3KmHDZORmdXGJOJp28/Jz0Ti43",
    "J0R1cqnH6Z1c5nHI+3mpx0neX/5xeieXeBytQ770SEYnlxmJQw2TS40kNrvw2E5miH8yXPflG6hM/kK3J4sAATzZeLOdg11MTzwN",
    "VTz4Rhm7sIKGdNdDW6HOjVYhHt6IOIm0PdxfEyF82bJp1VG/hXYyKOod2goTSpIxRwyQxAIMJCYe2kqh5J9pGR+HtVIk1mP14d6Q",
    "chSgr+Hwu2uk4VlIkz60Eep0JmvUET/VtY4BrnFoq86YmA+f9nLKBiLDiUd4GiM6hhxAxA9tRfQtzh3hdg0UQfPqKKho9+Gja/hw",
    "iKnvEon6mN8zim6C+bhxZnKia3PU7wW8c1lwmB3cDrnAsjXIMnNgO4TBZvwCDh+noQ3bHvUaOgo0HYUQjhiUNKCLfXg7j6q2jWvh",
    "8HaGIl1AanR4O+T1LOMEp/ah7crJTuM86rU7uqdYwLcc0a4j/o56PtcRcy1R/uB2GdWJDQCMj5gXXGXHtAmE6YnmqN/yCrE81h/1",
    "e4Y4i49a0hZzdoqZfNQrt5Rfq0C0+vB2Bjm0FPC2Hd6OdjIF/tuD25GQWsr5KFC/CWS0x3TMvBhUpc9KHfX6jFV01ffHzAsl7qqk",
    "j3o8RYhF445pp4kCTUOm6+HtQhfWOeqg1YGQbSCudHg7TDqv+nr+qHaoAlvsS33c71F+/lEHtLa4S1h91OMRgsLko+wIlWIiGoFj",
    "VnXHYZl41NenLA3THTMrCjW/qvlx1ONpRwH9Yz4in/HaZ6NyxzTDBLViXfn9H9HC6Y0x+KGQN8FWJCqGTFTG1aqJbyJps1VeKUo2",
    "yzMnxT3Ko7d6qzxpxbqCHfnShf6pXOqfyvf1nwLHB1yusTZu9k/lUv+9nO2/Csc7MnPXhLLOEtq3ovr+6MZ3r9/kWRyEegvGZk/k",
    "8GlO1vfLKgvXxJOv7D4EVsIqel+jEf+lFDxv9EdVI7qxEjF9e8y3MhVicOrOM4kotKy4y0gfEI8FCH+/nORtwgTnXBnHNiVvF+2I",
    "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",
    "97gHc7jrGlj+0xu3n7txe9NzApNcK9D7Qen5a5cvc51Z3HAFBF98r7gGH083O+EkXy5/ILxdM5fcY7vGbK/8En/yxTt373/m1nnx",
    "/rhHQl/VJ/v0zdvFV+cniYZ73ICfb5ebrUQBLzXKjhenwg2ufzoHNyb7MtNv3ToXPgmFmV69nH/z7J071HLd39xL/70bf373BvtY",
    "cBTbTmd0/TnhuXxYP1ddW95lO8UtVsTNp85vFe/6HrdaDTbBtlr9aEJOVl/srK14D9uAPQKV9eobw0pXpvF/vP3s+e37d3Y/xery",
    "feb81hdu3L9PQ3vj7peKqz9a9oWpiV7++oW/u/h5WZpfnvjW2b4xzSvH2n++eev8Szfv32PfBrbMWpRSz0NfPitra10b61bFvb0+",
    "Meu6d3735m2+WzObv39450s3zv74xhef/9ytm8+yryXNOv2j3yrrw23hXeO8q6YarSeNeObBv2ZX0DzDpHyq3Cl7n3hX9Wz/b2/d",
    "vCdtDnCsVHPQf/DMxTfLT79fVrynjAsQEQWbRZeWe3H/Fuvm/u9v3bl78/zsP904vy3+vp4PUVkUH7VJ/ivCiXEXwCvI0+n7Jxdv",
    "73zdptHt/f75ra/ceK50c75dFPsO02DdbZ17p7OLzP2D7rfUqFiNQ5RhIrB23Yg/oo9H3IaNnX/OCBu8Uvc/biQdZlrdqs6/cPMW",
    "3Tz3Dudv5Q8+/SdTd+V8/Xw/qiXfV+a68NbtPHG/GvCrU5S9LP4/bM2+cH7r1sovm1aw8sW+OFUGS6tnmg/bEsxdBu0RLc4LVlEf",
    "iLjeO2V4nuCYdVc6cOzBr5MK9Bjlvfvnz918/gu9AeVaW5yt3Fk75da9jSlERNukWe1TZ6cVuPIm4YbHkAEPkRotaP2pB+3I9j7P",
    "6k/shJbl+AspQP6KY8jUgSpfrePo5nTWnZqYu7ozYBmFk8z9u+XrrRt1L2zBWUiLTRJOa/3tbZsA4tTLY7ZNMnRzrdgkrrnaNk1y",
    "V99NYpN+L/rQDxlz6G5N1w3a/g6Y5RZSL3+2KrTocsHVWyRBkAZ1eNzYxT48u/i74uB8rQVQXvhk2cM/pGn0uefv/cb6Wq77zvfF",
    "iI2tmq4H4gV76vuRk0i9A4ntpMGTvCl3xulEG1EBxRjyEYw1Yhv4ETqzJUkWSwsrxxsCZCGS4jmVI5FZ80RjJtKcVIEv3TKIJqrB",
    "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",
    "nCYqk8sXhfYgdxtA3u29oQrWKifkf33GeKtJAPFRA7e+0AhvpEmZsCvoJP407clxMDJt26CQxvL899pbMIXnKHaCsdVenAwopo6h",
    "rtwX32yw8Rcam+MLVcqJ2HU218G1j6OsbNs30N3GuZ1VE9PR2Z1W9E6z9nxWFLRE2cYdgInVEHcMXiCzgvCAsKpYBb60sRWu6bBw",
    "8uR/wkSwqYrAXeBUg6DPQMWItUEWizsg7TxWtyUUCrU/DUVz8fbly0Tq9qgCoNic7jHXLJm/MphJzB7IhtKvalOEU7nRKaWhScXs",
    "KdX+vjttND8uf/A369Ki2WWxcd9f9TLfUCNXviy0nP+Rl1XitXj1Z5tddpVnG5dVLrETrrrKiIzLThyRGpm4wmWElq9iI/6Uy3yO",
    "J1x2xdfWL7vaa8NlV3tt/aqrvTZcdsXXlrqiyZXGv192tfHHZVcc/37Z1cY/9aygPuWqq40/Lrva+GtSVrraOOKqqw1jv+pKo6ih",
    "nX3FW8RlV7zHCNHzev3VL7vaNB6XXenZjEKAJyV7wmVXe7Z+2dWebVx22rNd7b0ZinhfdUhw2THPtgjCQdTZj+KjJWMGJB4UZw8Z",
    "+m9ZcoGj0qDxTzGuvZtKyQEFubiDj3EgeZAcfUXA3+LrNVD6Lv3nxUeXr00Feg3D+c7EC0xu/oLwBFJ8mi2H7AjXGdZ/YYdSr9KJ",
    "o0MJABrNaPMWdCkqg9E+s3QqCtePkocVHwuVAs/CLXN7ALNuDlwEuQo8EFo0Js5ejoVEGsKF/wOpA6ScFf/4BNaLnktghqgJABmT",
    "YYcHyQOb2ZtX4AEfOois3WouQD2zh8iS1ZDOh9g/7FL/3c73X87RUOLTTGEg5qZQk6gdvVoTvBZO94EOvuUwJQUAnMIzevGMTexE",
    "eiLDfePy1Yt3L7/2zNnF6xcfXr7RahEXH98Pdj6+NZ4QcHuXWTHOSmqQsADxM9zjIMlDja3KnU3fzrgO/+y5G1+8c79rPVEOTyuB",
    "+J8i3d56jnrTEB5TzwDRMzPJZ5U31efxsiTIUujVDEgjx/BDwUAXG1GAWKkxVfi8OMmonU1F0E224r1apvFBDfFcfp0INxZ8mFAe",
    "Kad6rqbYdv3WxAyCIbmNrHNmZrMCrUo8yCWrVOjLxiEmVyICjo0ud9N0SxQEsKZAnWCIrLgSeQexugP6s0MgeVnYAK1xw6FWyvWA",
    "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",
    "oEAsSP/tf/0f3aaFxQ==",
)

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
