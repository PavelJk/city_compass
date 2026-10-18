"""Правила разбора тегов OpenStreetMap по категориям мест (используются scripts/build_poi_from_pbf.py)."""
import math, re

# (категория, ключ тега, значения через пробел)
RULES = [
 # транспорт
 ("transport", "highway", "bus_stop"), ("transport", "public_transport", "platform stop_position"),
 ("tram", "railway", "tram_stop"), ("rail_station", "railway", "station halt"), ("rail_station", "public_transport", "station"),
 ("bus_station", "amenity", "bus_station"), ("bike_rent", "amenity", "bicycle_rental kick-scooter_rental"),
 ("parking", "amenity", "parking parking_space parking_entrance"),
 # образование
 ("school", "amenity", "school"), ("kindergarten", "amenity", "kindergarten childcare"),
 ("college", "amenity", "college university"), ("extra_edu", "amenity", "music_school language_school training driving_school"),
 # медицина
 ("hospital", "amenity", "hospital"), ("clinic", "amenity", "clinic doctors"), ("dentist", "amenity", "dentist"),
 ("pharmacy", "amenity", "pharmacy"),
 # торговля и сервисы
 ("cafe", "amenity", "cafe restaurant fast_food food_court ice_cream pub_food"), ("market", "amenity", "marketplace"),
 ("services", "amenity", "veterinary"), ("services", "office", "tax_advisor lawyer insurance estate_agent"),
 ("bank", "amenity", "bank atm"), ("post", "amenity", "post_office post_box"),
 ("pvz", "amenity", "parcel_locker"), ("pvz", "shop", "outpost"),
 ("public", "amenity", "townhall police courthouse community_centre social_facility"),
 ("office", "office", "government company it financial coworking research"), ("office", "building", "office commercial"),
 # зелень и вода
 ("park", "leisure", "park nature_reserve"), ("square", "leisure", "garden"), ("square", "place", "square"),
 ("playground", "leisure", "playground"), ("forest", "landuse", "forest"), ("forest", "natural", "wood"),
 ("water", "natural", "water"), ("water", "water", "lake pond reservoir river"), ("beach", "natural", "beach"),
 ("beach", "leisure", "beach_resort swimming_area"),
 # спорт, культура, досуг
 ("sport", "leisure", "fitness_centre sports_centre swimming_pool ice_rink"), ("pitch", "leisure", "pitch track"),
 ("culture", "amenity", "theatre cinema library arts_centre concert_hall"), ("museum", "tourism", "museum gallery"),
 ("attraction", "tourism", "attraction viewpoint artwork"), ("attraction", "historic", "monument memorial castle"),
 ("fun", "leisure", "amusement_arcade bowling_alley escape_game adult_gaming_centre miniature_golf"),
 ("fun", "amenity", "events_venue"),
 # негатив
 ("bar", "amenity", "bar pub biergarten"), ("nightclub", "amenity", "nightclub stripclub"), ("casino", "amenity", "casino gambling"),
 ("casino", "shop", "bookmaker lottery"), ("alcohol", "shop", "alcohol beverages wine"),
 ("industrial", "landuse", "industrial quarry brownfield"), ("industrial", "man_made", "works chimney"),
 ("warehouse", "building", "warehouse industrial"), ("warehouse", "landuse", "depot"),
 ("airport", "aeroway", "aerodrome terminal heliport"), ("waste", "landuse", "landfill"),
 ("waste", "amenity", "waste_transfer_station waste_disposal recycling"), ("sewage", "man_made", "wastewater_plant water_works"),
 ("fuel", "amenity", "fuel"), ("fuel_depot", "man_made", "storage_tank petroleum_well"), ("fuel_depot", "industrial", "oil"),
 ("substation", "power", "substation transformer"), ("powerplant", "power", "plant generator"),
 ("construction", "landuse", "construction"), ("cemetery", "landuse", "cemetery"), ("cemetery", "amenity", "grave_yard crematorium"),
 ("stadium", "leisure", "stadium"), ("fire", "amenity", "fire_station"), ("ambulance", "emergency", "ambulance_station"),
 ("ambulance", "amenity", "ambulance_station"), ("prison", "amenity", "prison"), ("prison", "barrier", "prison"),
 ("wetland", "natural", "wetland"),
]
# магазины: значение тега shop -> категория (остальное — «Другие магазины»)
SHOP = {
    "grocery": "convenience greengrocer butcher dairy general kiosk variety_store seafood farm deli frozen_food health_food "
               "spices nuts tea coffee water ice_cream food",
    "supermarket": "supermarket wholesale", "bakery": "bakery pastry confectionery chocolate",
    "mall": "mall department_store", "clothes": "clothes shoes fashion boutique bag fabric tailor jewelry watches fashion_accessories",
    "electronics": "electronics computer mobile_phone appliance hifi telecommunication",
    "furniture": "furniture interior_decoration kitchen bed carpet curtain lighting houseware",
    "diy": "doityourself hardware paint trade tiles glaziery building_materials garden_centre",
    "pharmacy": "chemist medical_supply optician hearing_aids",
    "services": "hairdresser beauty cosmetics laundry dry_cleaning copyshop travel_agency massage tattoo mobile_phone_repair photo",
}
SHOP_CAT = {v: k for k, vs in SHOP.items() for v in vs.split()}
SKIP_SHOP = set("alcohol beverages wine bookmaker lottery outpost".split())
PVZ_RX = "Ozon|Озон|Wildberries|Вайлдберриз|Яндекс Маркет|СДЭК|CDEK|Boxberry|5Post|ПВЗ|Пункт выдачи"
MFC_RX = "МФЦ|Мои документы|Госуслуги"


# Места, которые часто закрываются: если их в OSM давно не правили, считаем устаревшими
VOLATILE = set("grocery shop_other bakery clothes electronics furniture diy pharmacy cafe bank services pvz fun bar nightclub casino "
               "alcohol dentist extra_edu office".split())
FRESH_FROM = 2021          # правка не раньше этого года
CHECKED_FROM = "2023"      # или отметка проверки (check_date / survey:date) не раньше этого года
LIFECYCLE = ("disused:", "abandoned:", "was:", "razed:", "demolished:", "removed:")


def is_closed(tags):
    """Объект помечен как закрытый, заброшенный или снесённый."""
    if tags.get("disused") == "yes" or tags.get("abandoned") == "yes" or tags.get("opening_hours") == "off":
        return True
    return any(t.k.startswith(LIFECYCLE) for t in tags)


def is_fresh(tags, year):
    """Правка в OSM свежая или есть недавняя отметка проверки."""
    if year >= FRESH_FROM:
        return True
    checked = tags.get("check_date") or tags.get("survey:date") or tags.get("check_date:opening_hours") or ""
    return checked[:4] >= CHECKED_FROM


def thin(coords, step=250):
    out, last = [], None
    for lat, lng in coords:
        if last is None or math.hypot((lat - last[0]) * 111000, (lng - last[1]) * 61000) >= step:
            out.append((lat, lng)); last = (lat, lng)
    return out


def classify(tags):
    cats = set()
    for cat, key, vals in RULES:
        if tags.get(key) in vals.split():
            cats.add(cat)
    shop = tags.get("shop")
    if shop and shop not in SKIP_SHOP:
        cats.add(SHOP_CAT.get(shop, "shop_other"))
    blob = " ".join(tags.get(k, "") for k in ("name", "brand", "operator"))
    if re.search(PVZ_RX, blob, re.I):
        cats.add("pvz")
    if re.search(MFC_RX, blob) and tags.get("amenity") != "parking":
        cats.add("mfc")
    if "parking" in cats and tags.get("access") in ("private", "no", "customers"):
        cats.discard("parking")
    return cats
