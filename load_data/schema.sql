-- Населённые пункты
CREATE TABLE locality (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL
);

-- Источники объявлений
CREATE TABLE source (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL
);

-- Объявления о продаже квартир
CREATE TABLE flat (
  id INTEGER PRIMARY KEY,
  url TEXT,
  name TEXT,
  address TEXT,
  locality_id INTEGER REFERENCES locality(id),
  complex TEXT,
  market TEXT,
  rooms TEXT,
  area REAL,
  price INTEGER,
  rent INTEGER,
  rent_estimated INTEGER,
  approx INTEGER,
  lat REAL,
  lng REAL,
  source_id INTEGER REFERENCES source(id),
  photo_shared INTEGER
);

-- Фотографии объявлений
CREATE TABLE flat_photo (
  flat_id INTEGER REFERENCES flat(id),
  position INTEGER,
  path TEXT
);

-- Контуры домов и участков на карте
CREATE TABLE building (
  id INTEGER PRIMARY KEY,
  kind TEXT
);

-- Вершины контуров
CREATE TABLE building_vertex (
  building_id INTEGER REFERENCES building(id),
  seq INTEGER,
  lat REAL,
  lng REAL
);

-- Какие объявления относятся к контуру (дому)
CREATE TABLE building_flat (
  building_id INTEGER REFERENCES building(id),
  flat_id INTEGER REFERENCES flat(id)
);

-- Группы мест для индекса среды
CREATE TABLE poi_group (
  code TEXT PRIMARY KEY,
  label TEXT,
  weight INTEGER
);

-- Категории мест
CREATE TABLE poi_category (
  code TEXT PRIMARY KEY,
  label TEXT,
  group_code TEXT REFERENCES poi_group(code),
  kind TEXT,
  radius_m INTEGER,
  optimum_m INTEGER,
  severity INTEGER
);

-- Места на карте (OpenStreetMap)
CREATE TABLE poi (
  id INTEGER PRIMARY KEY,
  category TEXT REFERENCES poi_category(code),
  lat REAL,
  lng REAL,
  name TEXT
);

-- Объявления об аренде (для расчёта аренды по дому)
CREATE TABLE rent_offer (
  id INTEGER PRIMARY KEY,
  address TEXT,
  area REAL,
  rooms INTEGER,
  floor INTEGER,
  floors INTEGER,
  rent INTEGER
);

-- Узлы пешеходного графа улиц
CREATE TABLE walk_node (
  id INTEGER PRIMARY KEY,
  lat REAL,
  lng REAL
);

-- Рёбра пешеходного графа (ненаправленные, каждое один раз)
CREATE TABLE walk_edge (
  node_a INTEGER REFERENCES walk_node(id),
  node_b INTEGER REFERENCES walk_node(id),
  length_m REAL
);

-- Кэш определения координат по адресу
CREATE TABLE geocode_cache (
  address TEXT PRIMARY KEY,
  lat REAL,
  lng REAL
);

-- Допущения расчёта по умолчанию
CREATE TABLE model_param (
  param TEXT PRIMARY KEY,
  value TEXT
);

-- Пользователи сайта — ТОЛЬКО СТРУКТУРА, данных нет
CREATE TABLE app_user (
  id INTEGER PRIMARY KEY,
  email TEXT,
  name TEXT,
  color TEXT,
  created REAL,
  settings TEXT
);

-- Сессии входа — ТОЛЬКО СТРУКТУРА, данных нет
CREATE TABLE app_session (
  user_id INTEGER REFERENCES app_user(id),
  created REAL,
  expires REAL
);
