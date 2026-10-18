// Загрузка данных, расчёты, фильтры
import { GROUPS, MAP_CENTER } from './config.js';
import { evaluate, buildIndex, distM } from './score.js';
import { economics, profitScore, verdict, roomsKey, resale } from './finance.js';
import { buildGrid } from './hex.js';
import { state, D, getJson, median, NEAR_R } from './state.js';

let RAW = [], RAWB = [], RENTS = [];

export async function load() {
  const [L, P, B, RT] = await Promise.all([getJson('data/listings.json'), getJson('data/poi.json'), getJson('data/buildings.json'), getJson('data/rents.json')]);
  RAW = L?.listings || []; RAWB = B || []; RENTS = rentIndex(RT?.rents || []);
  D.meta = { listingsAt: L?.updatedAt, poiAt: P?.updatedAt };
  D.points = P?.points || [];
  D.index = buildIndex(D.points);
  rebuild();
}

const addrKey = f => String(f.address || '').trim();

// ключ адреса без городов, типов улиц и порядка слов: «ул. Кирова, д. 9» и «улица Кирова, 9» совпадут
const STOP = new Set('йошкар ола ул улица д дом жилой стр поз пос посёлок поселок с село пгт городского типа мкр микрорайон бульвар б-р проспект пр переулок пер тракт медведево семёновка семеновка руэм'.split(' '));
const tokens = a => String(a).toLowerCase().replace(/ё/g, 'е').split(/[^а-я0-9/]+/).filter(t => t && !STOP.has(t) && !STOP.has(t.replace(/е/g, 'ё')));
const houseKey = a => tokens(a).sort().join(' ');
const streetKey = a => tokens(a).filter(t => !/\d/.test(t)).sort().join(' ');

function rentIndex(rows) {
  const seen = new Set(), out = [];
  for (const [addr, area, rooms, floor, floors, rent] of rows) {
    const k = addr + area + rent; if (seen.has(k)) continue; seen.add(k);
    out.push({ house: houseKey(addr), street: streetKey(addr), hasNo: tokens(addr).some(t => /\d/.test(t)), area, rooms: rooms >= 3 ? 3 : rooms, rent });
  }
  return out;
}

// средняя аренда таких же квартир (комнаты, площадь ±30%) в этом доме, а если их нет — на этой улице (не меньше двух)
function rentRef(f) {
  const r = f.rooms.startsWith('Студ') ? 1 : Math.min(3, parseInt(f.rooms) || 1), hk = houseKey(f.address), sk = streetKey(f.address);
  const adj = o => o.rent * Math.max(0.85, Math.min(1.2, Math.sqrt(f.area / o.area)));
  const base = state.A.rentBase[roomsKey(f.rooms)];  // совсем нетипичную аренду (в 2 раза ниже или в 2 раза выше обычной) не берём: чаще всего это опечатка или элитное жильё
  const like = o => o.rooms === r && Math.abs(o.area - f.area) / f.area <= 0.3 && o.rent >= base * 0.6 && o.rent <= base * 1.8;
  const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
  const house = RENTS.filter(o => o.hasNo && o.house === hk && like(o));
  if (house.length) return { rent: mean(house.map(adj)), n: house.length, level: 'house' };
  const street = RENTS.filter(o => o.hasNo && o.street === sk && sk && like(o));
  if (street.length >= 2) return { rent: mean(street.map(adj)), n: street.length, level: 'street' };
  return null;
}
const ringCenter = r => [r.reduce((s, p) => s + p[0], 0) / r.length, r.reduce((s, p) => s + p[1], 0) / r.length];

// квартиры из базы и свои, контуры домов и участков (со своими поправками), соседи и ячейки
export function rebuild() {
  D.flats = [...RAW.map(l => ({ ...l, id: l.url || `${l.address}|${l.area}|${l.price}` })), ...state.userFlats.map(u => ({ ...u, own: true }))];
  D.byId.clear();
  D.flats.forEach(f => {
    f.market = f.market === 'new' ? 'new' : 'secondary';
    if (!/студ|\d/i.test(f.rooms || '')) f.rooms = f.area <= 30 ? 'Студия' : f.area <= 45 ? '1-комн.' : f.area <= 65 ? '2-комн.' : '3-комн.';
    const m = String(f.name || '').match(/(\d+)\s*\/\s*(\d+)\s*эт/);
    if (m) { f.floor = +m[1]; f.floors = +m[2]; }
    const poly = state.userPolys[addrKey(f)];
    if (poly) [f.lat, f.lng] = ringCenter(poly);  // нарисованный участок важнее геокодера
    f.rentRef = rentRef(f);
    D.byId.set(f.id, f);
  });
  // контуры: базовые без квартир, у которых нарисован свой участок, плюс свои
  const mine = new Set(Object.keys(state.userPolys));
  D.buildings = RAWB.map(b => ({ ...b, f: b.f.filter(id => !mine.has(addrKey(D.byId.get(id) || {}))) })).filter(b => b.f.length);
  const groups = new Map();
  D.flats.forEach(f => { const k = addrKey(f); if (mine.has(k) || f.own) { if (!groups.has(k)) groups.set(k, []); groups.get(k).push(f); } });
  for (const [addr, fl] of groups) {
    const poly = state.userPolys[addr], isNew = fl.some(f => f.market === 'new');
    if (poly) { D.buildings.push({ r: poly.concat([poly[0]]), f: fl.map(f => f.id), p: isNew ? 1 : 0, u: 1 }); continue; }
    const [la, lo] = [fl[0].lat, fl[0].lng], dy = (isNew ? 20 : 8) / 111320, dx = (isNew ? 30 : 14) / (111320 * Math.cos(la * Math.PI / 180));
    D.buildings.push({ r: [[la - dy, lo - dx], [la - dy, lo + dx], [la + dy, lo + dx], [la + dy, lo - dx], [la - dy, lo - dx]], f: fl.map(f => f.id), p: isNew ? 1 : 0, s: 1, u: 1 });
  }
  // соседи: все квартиры в радиусе NEAR_R (через сетку из клеток по ~1,5 км) и, если рядом пусто, несколько ближайших
  const bk = new Map(), BY = 0.0135, BX = 0.0243, keyOf = (la, lo) => Math.floor(la / BY) + ':' + Math.floor(lo / BX);
  D.flats.forEach(f => { const k = keyOf(f.lat, f.lng); (bk.get(k) || bk.set(k, []).get(k)).push(f); });
  D.flats.forEach(f => {
    const a = Math.floor(f.lat / BY), b = Math.floor(f.lng / BX), near = [];
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) for (const o of bk.get((a + i) + ':' + (b + j)) || []) {
      if (o === f) continue;
      const d = distM(f.lat, f.lng, o.lat, o.lng);
      if (d <= NEAR_R) near.push({ f: o, d });
    }
    if (near.length < 5) {
      const far = D.flats.filter(o => o !== f && !near.some(n => n.f === o)).map(o => ({ f: o, d: distM(f.lat, f.lng, o.lat, o.lng) })).sort((x, y) => x.d - y.d);
      near.push(...far.slice(0, 5 - near.length));
    }
    f.nb = near.sort((x, y) => x.d - y.d);
  });
  buildCells();
}

// размер ячейки выбирает пользователь, колец столько, чтобы покрыть ту же область
export function buildCells() {
  const side = Math.max(300, Math.min(1500, +state.A.gridSide || 700));
  D.cells = buildGrid(MAP_CENTER, side, Math.max(6, Math.ceil(16980 / (Math.sqrt(3) * side))), 1);
  assignCells();
}

// квартира привязывается к ячейке, в которой лежит
function assignCells() {
  D.cells.forEach(c => { c.flats = []; });
  // грубый индекс центров: клетки по ~0,01° — ищем только в соседних
  const g = new Map(), key = (la, lo) => Math.floor(la / 0.01) + ':' + Math.floor(lo / 0.02);
  D.cells.forEach(c => { const k = key(c.center[0], c.center[1]); (g.get(k) || g.set(k, []).get(k)).push(c); });
  D.flats.forEach(f => {
    let best = null, bd = Infinity;
    const a = Math.floor(f.lat / 0.01), b = Math.floor(f.lng / 0.02);
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) for (const c of g.get((a + i) + ':' + (b + j)) || []) {
      const d = distM(f.lat, f.lng, c.center[0], c.center[1]); if (d < bd) { bd = d; best = c; }
    }
    f.cell = bd <= 450 ? best : null;
    if (f.cell) f.cell.flats.push(f);
  });
}

let envKey = '';
export function recompute() {
  const ex = new Set(state.excluded), A = state.A;
  for (const g in GROUPS) GROUPS[g].w = A.groupW?.[g] ?? GROUPS[g].w; // веса групп среды из допущений
  // среду пересчитываем только когда поменялись места, веса или сетка
  const key = JSON.stringify([state.excluded, A.groupW, A.walkRoute, D.walkVer || 0, D.cells.length, D.cells[0]?.center]);
  const envDirty = key !== envKey;
  envKey = key;
  // цены соседей в 1,5 км относительно города — влияют на аренду
  const cityPpm = median(D.flats.map(f => f.price / f.area));
  D.flats.forEach(f => {
    const near = f.nb.filter(n => n.d <= NEAR_R).map(n => n.f.price / n.f.area), local = near.length >= 3 ? median(near) : cityPpm;
    f.nbK = Math.max(0.9, Math.min(1.12, Math.pow(local / cityPpm, A.nbEffect ?? 0.35)));
  });
  D.flats.forEach(f => {
    f.rentOverride = state.rentOv[f.id] || 0;
    if (envDirty || !f.envR) { f.envR = evaluate(f.lat, f.lng, D.index, ex, A.walkRoute ? f.walk : null); f.env = f.envR.score; }
    f.e = economics(f, f.env, A);
  });
  D.flats.forEach(f => {
    const near = f.nb.filter(n => n.d <= NEAR_R), same = near.filter(n => n.f.market === f.market);
    const med = median((same.length >= 3 ? same : near).map(n => n.f.e.pricePerM2));
    f.med = med; f.disc = med ? (med - f.e.pricePerM2) / med : null;
    f.rs = resale(f, f.env, f.disc, A, f.e);
    f.score = profitScore(f.e, f.env, f.disc, A, f.rs); f.verdict = verdict(f.score);
  });
  [...D.flats].sort((a, b) => b.score - a.score).forEach((f, i) => { f.rank = i + 1; });
  state.medYield = median(D.flats.map(f => f.e.netYield));
  D.cells.forEach(c => {
    if (envDirty || !c.envR) c.envR = evaluate(c.center[0], c.center[1], D.index, ex, A.walkRoute ? c.walk : null);
    if (!c.fl) c.fl = D.flats.filter(f => distM(c.center[0], c.center[1], f.lat, f.lng) <= NEAR_R);
  });
}

// своё фото — не подставленное из соседнего объявления
const hasOwnPhoto = f => !!f.photo && !f.photoShared;
// без учёта рынка — для счётчиков на карточках «Новостройки / Вторичка»
export const passesExceptMarket = f => f.price <= state.f.max
  && (!state.f.rooms.length || state.f.rooms.includes(roomsKey(f.rooms)))
  && (!state.f.loc || f.locality === state.f.loc)
  && (!state.f.fav || state.fav.includes(f.id))
  && (!state.f.photoOnly || hasOwnPhoto(f));
export const passes = f => passesExceptMarket(f) && state.f.market.includes(f.market);
export const SORTERS = {
  score: (a, b) => b.score - a.score, yield: (a, b) => b.e.netYield - a.e.netYield,
  growth: (a, b) => b.rs.cagr - a.rs.cagr, total: (a, b) => b.rs.irr - a.rs.irr,
  price: (a, b) => a.price - b.price, ppm: (a, b) => a.e.pricePerM2 - b.e.pricePerM2, env: (a, b) => (b.env ?? -1) - (a.env ?? -1),
};
export const visible = () => D.flats.filter(passes).sort(SORTERS[state.f.sort]);

export function marketStats() {
  const out = {};
  for (const k of ['new', 'secondary']) {
    const g = D.flats.filter(f => f.market === k);
    out[k] = { n: g.length, ppm: median(g.map(f => f.e.pricePerM2)), yld: median(g.map(f => f.e.netYield)), price: median(g.map(f => f.price)) };
  }
  return out;
}
