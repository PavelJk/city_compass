ГОРОДСКОЙ КОМПАС — таблицы данных проекта

Папка «Таблицы» — каждая таблица отдельным CSV (UTF-8, разделитель «;»).
realty.db — те же таблицы одним файлом SQLite, schema.sql — описание.
load_tables.py — загрузка CSV в свою базу SQLite: python load_tables.py [--db файл.db] [--check]

Таблица               Строк   Описание
locality                  4   Населённые пункты
source                    2   Источники объявлений
flat                   1039   Объявления о продаже квартир
flat_photo             1106   Фотографии объявлений
building                535   Контуры домов и участков на карте
building_vertex        6534   Вершины контуров
building_flat          1043   Какие объявления относятся к контуру (дому)
poi_group                 7   Группы мест для индекса среды
poi_category             69   Категории мест
poi                    9182   Места на карте (OpenStreetMap)
rent_offer               23   Объявления об аренде (для расчёта аренды по дому)
walk_node             67315   Узлы пешеходного графа улиц
walk_edge             78416   Рёбра пешеходного графа (ненаправленные, каждое один раз)
geocode_cache           750   Кэш определения координат по адресу
model_param              50   Допущения расчёта по умолчанию
app_user                  0   Пользователи сайта — ТОЛЬКО СТРУКТУРА, данных нет
app_session               0   Сессии входа — ТОЛЬКО СТРУКТУРА, данных нет

Колонки:

locality — Населённые пункты
  id            INTEGER PRIMARY KEY               код
  name          TEXT NOT NULL                     название

source — Источники объявлений
  id            INTEGER PRIMARY KEY               код
  name          TEXT NOT NULL                     название сайта

flat — Объявления о продаже квартир
  id            INTEGER PRIMARY KEY               код
  url           TEXT                              ссылка на объявление
  name          TEXT                              заголовок
  address       TEXT                              адрес
  locality_id   INTEGER REFERENCES locality(id)   населённый пункт
  complex       TEXT                              жилой комплекс
  market        TEXT                              new — новостройка, secondary — вторичка
  rooms         TEXT                              комнатность
  area          REAL                              площадь, м²
  price         INTEGER                           цена, ₽
  rent          INTEGER                           аренда, ₽/мес (оценка или из объявлений)
  rent_estimatedINTEGER                           1 — аренда оценена расчётом
  approx        INTEGER                           1 — координаты приблизительные (центр улицы)
  lat           REAL                              широта
  lng           REAL                              долгота
  source_id     INTEGER REFERENCES source(id)     источник
  photo_shared  INTEGER                           1 — фото взято из другого объявления в этом доме

flat_photo — Фотографии объявлений
  flat_id       INTEGER REFERENCES flat(id)       объявление
  position      INTEGER                           порядок
  path          TEXT                              файл фото

building — Контуры домов и участков на карте
  id            INTEGER PRIMARY KEY               код
  kind          TEXT                              outline — контур дома из OSM, plot — участок стройки, synthetic — прямоугольник по адресу

building_vertex — Вершины контуров
  building_id   INTEGER REFERENCES building(id)   контур
  seq           INTEGER                           порядок вершины
  lat           REAL                              широта
  lng           REAL                              долгота

building_flat — Какие объявления относятся к контуру (дому)
  building_id   INTEGER REFERENCES building(id)   контур
  flat_id       INTEGER REFERENCES flat(id)       объявление

poi_group — Группы мест для индекса среды
  code          TEXT PRIMARY KEY                  код
  label         TEXT                              название
  weight        INTEGER                           вес группы в индексе среды, %

poi_category — Категории мест
  code          TEXT PRIMARY KEY                  код
  label         TEXT                              название
  group_code    TEXT REFERENCES poi_group(code)   группа
  kind          TEXT                              pos — плюс, neg — минус для жизни рядом
  radius_m      INTEGER                           радиус учёта, м
  optimum_m     INTEGER                           расстояние, до которого место считается идеальным, м
  severity      INTEGER                           сила минуса (для neg)

poi — Места на карте (OpenStreetMap)
  id            INTEGER PRIMARY KEY               код
  category      TEXT REFERENCES poi_category(code)категория
  lat           REAL                              широта
  lng           REAL                              долгота
  name          TEXT                              название

rent_offer — Объявления об аренде (для расчёта аренды по дому)
  id            INTEGER PRIMARY KEY               код
  address       TEXT                              адрес
  area          REAL                              площадь, м²
  rooms         INTEGER                           комнат
  floor         INTEGER                           этаж
  floors        INTEGER                           этажей в доме
  rent          INTEGER                           аренда, ₽/мес

walk_node — Узлы пешеходного графа улиц
  id            INTEGER PRIMARY KEY               код узла
  lat           REAL                              широта
  lng           REAL                              долгота

walk_edge — Рёбра пешеходного графа (ненаправленные, каждое один раз)
  node_a        INTEGER REFERENCES walk_node(id)  узел
  node_b        INTEGER REFERENCES walk_node(id)  узел
  length_m      REAL                              длина, м

geocode_cache — Кэш определения координат по адресу
  address       TEXT PRIMARY KEY                  адрес
  lat           REAL                              широта
  lng           REAL                              долгота

model_param — Допущения расчёта по умолчанию
  param         TEXT PRIMARY KEY                  параметр (вложенные через точку)
  value         TEXT                              значение

app_user — Пользователи сайта — ТОЛЬКО СТРУКТУРА, данных нет
  id            INTEGER PRIMARY KEY               код
  email         TEXT                              почта
  name          TEXT                              имя
  color         TEXT                              цвет аватара
  created       REAL                              время регистрации
  settings      TEXT                              сохранённые настройки (JSON)

app_session — Сессии входа — ТОЛЬКО СТРУКТУРА, данных нет
  user_id       INTEGER REFERENCES app_user(id)   пользователь
  created       REAL                              создана
  expires       REAL                              действует до

Связи: flat → locality, source; flat_photo → flat; building_vertex, building_flat → building, flat;
poi → poi_category → poi_group; walk_edge → walk_node.
Расчёты (аренда, доходность, индекс среды, оценка) считаются на сайте по этим таблицам и в них не хранятся.
