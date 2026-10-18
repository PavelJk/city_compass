// категории мест: группа, радиус влияния R (м), оптимальная дистанция opt (м)
export const GROUPS = {
  transport: { label: 'Транспорт', w: 20 }, education: { label: 'Школы и сады', w: 15 },
  health: { label: 'Медицина', w: 10 }, shops: { label: 'Магазины и услуги', w: 10 },
  green: { label: 'Парки и зелень', w: 15 }, leisure: { label: 'Спорт и культура', w: 10 },
  public: { label: 'Общественные сервисы', w: 10 },
};
// kind: pos | neg, sev — насколько сильный минус
export const CATS = {
  transport: { label: 'Остановка', group: 'transport', kind: 'pos', R: 600, opt: 80, icon: 'fa-bus-simple' },
  tram: { label: 'Трамвайная остановка', group: 'transport', kind: 'pos', R: 600, opt: 80, icon: 'fa-train-tram' },
  rail_station: { label: 'Ж/д станция', group: 'transport', kind: 'pos', R: 1500, opt: 500, icon: 'fa-train' },
  bus_station: { label: 'Автовокзал', group: 'transport', kind: 'pos', R: 1500, opt: 250, icon: 'fa-bus' },
  bike_rent: { label: 'Прокат велосипедов и самокатов', group: 'transport', kind: 'pos', R: 600, opt: 0, icon: 'fa-bicycle' },
  cycleway: { label: 'Велодорожка', group: 'transport', kind: 'pos', R: 400, opt: 0, icon: 'fa-person-biking' },
  parking: { label: 'Парковка', group: 'transport', kind: 'pos', R: 500, opt: 0, icon: 'fa-square-parking' },
  school: { label: 'Школа', group: 'education', kind: 'pos', R: 1100, opt: 300, icon: 'fa-school' },
  kindergarten: { label: 'Детский сад', group: 'education', kind: 'pos', R: 900, opt: 200, icon: 'fa-child-reaching' },
  extra_edu: { label: 'Допобразование', group: 'education', kind: 'pos', R: 1800, opt: 0, icon: 'fa-book-open-reader' },
  college: { label: 'Вуз / колледж', group: 'education', kind: 'pos', R: 3000, opt: 300, icon: 'fa-graduation-cap' },
  clinic: { label: 'Поликлиника / медцентр', group: 'health', kind: 'pos', R: 1500, opt: 300, icon: 'fa-stethoscope' },
  hospital: { label: 'Больница', group: 'health', kind: 'pos', R: 2000, opt: 500, icon: 'fa-hospital' },
  dentist: { label: 'Стоматология', group: 'health', kind: 'pos', R: 1000, opt: 0, icon: 'fa-tooth' },
  pharmacy: { label: 'Аптека', group: 'health', kind: 'pos', R: 700, opt: 0, icon: 'fa-prescription-bottle-medical' },
  grocery: { label: 'Продукты', group: 'shops', kind: 'pos', R: 500, opt: 0, icon: 'fa-basket-shopping' },
  supermarket: { label: 'Супермаркет', group: 'shops', kind: 'pos', R: 1000, opt: 0, icon: 'fa-cart-shopping' },
  bakery: { label: 'Пекарня', group: 'shops', kind: 'pos', R: 700, opt: 0, icon: 'fa-bread-slice' },
  clothes: { label: 'Одежда и обувь', group: 'shops', kind: 'pos', R: 1500, opt: 0, icon: 'fa-shirt' },
  electronics: { label: 'Электроника', group: 'shops', kind: 'pos', R: 1500, opt: 0, icon: 'fa-laptop' },
  furniture: { label: 'Мебель и дом', group: 'shops', kind: 'pos', R: 1800, opt: 0, icon: 'fa-couch' },
  diy: { label: 'Стройматериалы', group: 'shops', kind: 'pos', R: 2000, opt: 0, icon: 'fa-hammer' },
  shop_other: { label: 'Другие магазины', group: 'shops', kind: 'pos', R: 800, opt: 0, icon: 'fa-store' },
  mall: { label: 'Торговый центр', group: 'shops', kind: 'pos', R: 3000, opt: 500, icon: 'fa-bag-shopping' },
  market: { label: 'Рынок', group: 'shops', kind: 'pos', R: 1500, opt: 400, icon: 'fa-shop' },
  cafe: { label: 'Кафе и рестораны', group: 'shops', kind: 'pos', R: 1000, opt: 0, icon: 'fa-mug-hot' },
  services: { label: 'Бытовые услуги', group: 'shops', kind: 'pos', R: 800, opt: 0, icon: 'fa-scissors' },
  pvz: { label: 'Пункт выдачи заказов', group: 'shops', kind: 'pos', R: 700, opt: 0, icon: 'fa-box' },
  park: { label: 'Парк', group: 'green', kind: 'pos', R: 800, opt: 100, icon: 'fa-tree' },
  square: { label: 'Сквер', group: 'green', kind: 'pos', R: 500, opt: 0, icon: 'fa-leaf' },
  playground: { label: 'Детская площадка', group: 'green', kind: 'pos', R: 300, opt: 0, icon: 'fa-baby-carriage' },
  forest: { label: 'Лес', group: 'green', kind: 'pos', R: 1000, opt: 0, icon: 'fa-seedling' },
  water: { label: 'Река / озеро', group: 'green', kind: 'pos', R: 1000, opt: 50, icon: 'fa-water' },
  beach: { label: 'Пляж', group: 'green', kind: 'pos', R: 1200, opt: 0, icon: 'fa-umbrella-beach' },
  promenade: { label: 'Набережная', group: 'green', kind: 'pos', R: 1000, opt: 0, icon: 'fa-person-walking' },
  sport: { label: 'Фитнес и спорткомплекс', group: 'leisure', kind: 'pos', R: 1500, opt: 150, icon: 'fa-dumbbell' },
  pitch: { label: 'Спортивная площадка', group: 'leisure', kind: 'pos', R: 800, opt: 0, icon: 'fa-futbol' },
  culture: { label: 'Театр, кино, библиотека', group: 'leisure', kind: 'pos', R: 2000, opt: 0, icon: 'fa-masks-theater' },
  museum: { label: 'Музей', group: 'leisure', kind: 'pos', R: 2000, opt: 0, icon: 'fa-landmark' },
  attraction: { label: 'Достопримечательность', group: 'leisure', kind: 'pos', R: 1500, opt: 0, icon: 'fa-camera' },
  fun: { label: 'Досуг и развлечения', group: 'leisure', kind: 'pos', R: 1500, opt: 0, icon: 'fa-gamepad' },
  bank: { label: 'Банк / банкомат', group: 'public', kind: 'pos', R: 800, opt: 0, icon: 'fa-building-columns' },
  post: { label: 'Почта', group: 'public', kind: 'pos', R: 1000, opt: 0, icon: 'fa-envelope' },
  mfc: { label: 'МФЦ', group: 'public', kind: 'pos', R: 3000, opt: 0, icon: 'fa-file-signature' },
  public: { label: 'Госучреждение', group: 'public', kind: 'pos', R: 1800, opt: 0, icon: 'fa-landmark-flag' },
  office: { label: 'Офисы и работодатели', group: 'public', kind: 'pos', R: 1500, opt: 0, icon: 'fa-briefcase' },
  bar: { label: 'Бар / паб', kind: 'neg', R: 350, sev: 3, icon: 'fa-beer-mug-empty' },
  nightclub: { label: 'Ночной клуб', kind: 'neg', R: 500, sev: 4, icon: 'fa-music' },
  casino: { label: 'Казино / ставки', kind: 'neg', R: 250, sev: 1.5, icon: 'fa-dice' },
  alcohol: { label: 'Алкомаркет', kind: 'neg', R: 250, sev: 2, icon: 'fa-wine-bottle' },
  industrial: { label: 'Промзона / завод', kind: 'neg', R: 900, sev: 6, icon: 'fa-industry' },
  warehouse: { label: 'Склады', kind: 'neg', R: 250, sev: 1.5, icon: 'fa-warehouse' },
  airport: { label: 'Аэропорт', kind: 'neg', R: 3000, sev: 6, icon: 'fa-plane' },
  railway: { label: 'Железная дорога', kind: 'neg', R: 350, sev: 3, icon: 'fa-train-subway' },
  highway: { label: 'Магистраль', kind: 'neg', R: 250, sev: 4, icon: 'fa-road' },
  waste: { label: 'Мусор / полигон', kind: 'neg', R: 1500, sev: 6, icon: 'fa-dumpster' },
  sewage: { label: 'Очистные', kind: 'neg', R: 1200, sev: 6, icon: 'fa-faucet-drip' },
  fuel: { label: 'АЗС', kind: 'neg', R: 200, sev: 2, icon: 'fa-gas-pump' },
  fuel_depot: { label: 'Нефтебаза / ГСМ', kind: 'neg', R: 700, sev: 4, icon: 'fa-oil-can' },
  powerline: { label: 'ЛЭП', kind: 'neg', R: 150, sev: 2, icon: 'fa-bolt' },
  substation: { label: 'Подстанция', kind: 'neg', R: 300, sev: 3, icon: 'fa-plug' },
  powerplant: { label: 'ТЭЦ / электростанция', kind: 'neg', R: 1000, sev: 5, icon: 'fa-fire-flame-simple' },
  construction: { label: 'Стройка', kind: 'neg', R: 300, sev: 2, icon: 'fa-trowel-bricks' },
  cemetery: { label: 'Кладбище', kind: 'neg', R: 300, sev: 1.5, icon: 'fa-cross' },
  stadium: { label: 'Стадион', kind: 'neg', R: 500, sev: 2, icon: 'fa-futbol' },
  fire: { label: 'Пожарная часть', kind: 'neg', R: 250, sev: 1.5, icon: 'fa-fire-extinguisher' },
  ambulance: { label: 'Скорая помощь', kind: 'neg', R: 250, sev: 2, icon: 'fa-truck-medical' },
  prison: { label: 'СИЗО / колония', kind: 'neg', R: 800, sev: 3, icon: 'fa-lock' },
  wetland: { label: 'Болото / подтопление', kind: 'neg', R: 300, sev: 1.5, icon: 'fa-droplet' },
};
export const ROUTE_MAX = 2200; // дальше считаем по прямой
export const MAP_CENTER = [56.6385, 47.8660];
const GROUP_W = Object.fromEntries(Object.entries(GROUPS).map(([k, g]) => [k, g.w]));
export const LOCALITIES = ['Йошкар-Ола', 'Медведево', 'Семёновка', 'Руэм'];
export const DEFAULT_ASSUMPTIONS = {
  // аренда
  // типичная аренда по комнатности, ₽/мес (ориентир — объявления в Йошкар-Оле, ~23,5 тыс. в среднем)
  rentBase: { studio: 20000, r1: 23500, r2: 27000, r3: 32000 },
  rentMin: 20000, rentMax: 35000,
  nbEffect: 0.35,       // как сильно цены соседей влияют на аренду (степень)
  envEffect: 12,        // ±% к аренде при крайних значениях индекса среды
  localityK: { 'Йошкар-Ола': 1, 'Медведево': 0.85, 'Семёновка': 0.8, 'Руэм': 0.75 }, // множитель аренды по населённому пункту
  marketK: { new: 1.08, secondary: 1 },  // новостройки сдаются дороже
  edgeFloorK: 0.95,     // первый и последний этаж: аренда × коэффициент
  // расходы и налоги
  vacancyMonths: 1, maintPct: 5, mgmtPct: 0, taxMode: 'ndfl13', propTaxPct: 0.1, repairPerM2: 8000, buyCostPct: 1,
  // ипотека
  mortgageOn: false, down: 20, rate: 14, years: 20,
  // цель и перепродажа
  goal: 'rent',          // rent / resale / mix
  horizon: 5,            // срок владения до продажи, лет
  priceGrowth: 5,        // рост цен, % в год
  growthEnv: 1.5,        // ±п.п. к росту при индексе среды 100 / 0
  growthNew: 1,          // новостройка: + п.п. в год
  growthLoc: { 'Йошкар-Ола': 0, 'Медведево': -0.5, 'Семёновка': -1, 'Руэм': -1.5 }, // п.п. к росту по населённому пункту
  catchUp: 0.5,          // какая часть отличия от цены соседей исчезнет к продаже
  sellCostPct: 1.5,      // расходы на продажу, % цены
  saleTax: 'auto',       // auto — 13% с прибыли при владении меньше 5 лет, none — не считать
  retRange: { resale: [0, 10], mix: [3, 12] }, // доходность в год, %: 0 баллов → максимум
  // индекс выгодности
  scoreW: { yield: 70, env: 15, price: 15 },
  yieldMin: 2, yieldMax: 6,                  // чистая доходность, %: 0 баллов → максимум
  // сетка и анимация карты
  gridSide: 700,        // сторона ячейки в проекции (в реальных метрах примерно в 0,55 раза меньше)
  wave: true, waveCells: 3, waveLift: 10, // волна: радиус в ячейках, высота в px
  // индекс среды
  walkRoute: true,      // пешком по улицам, а не по прямой
  groupW: { ...GROUP_W },
};
export const PRESETS = {
  conservative: { label: 'Консервативно', note: 'Больше простоя и расходов, аренда на 8% ниже', set: { vacancyMonths: 2, maintPct: 8, rentScale: 0.92 } },
  base: { label: 'Базово', note: 'Сбалансированные допущения по умолчанию', set: {} },
  optimistic: { label: 'Оптимистично', note: 'Мало простоя, самозанятость 4%, аренда на 8% выше', set: { vacancyMonths: 0.5, maintPct: 3, taxMode: 'self4', rentScale: 1.08 } },
};
