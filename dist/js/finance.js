export const roomsKey = r => /студ/i.test(r) ? 'studio' : /^1/.test(r) ? 'r1' : /^2/.test(r) ? 'r2' : 'r3';

// оценка аренды: типичная по комнатности с поправками на размер, соседей, среду, пункт, рынок, этаж,
// потом обрезается до диапазона (20–35 тыс.). Введённая вручную аренда не трогается.
const TYPICAL_AREA = { studio: 25, r1: 38, r2: 55, r3: 75 };
const clampN = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
export function rentFactors(f, env, A) {
  const edge = f.floor && f.floors && (f.floor === 1 || f.floor === f.floors) && f.floors > 2;
  return [
    ['Размер квартиры', clampN(Math.sqrt(f.area / TYPICAL_AREA[roomsKey(f.rooms)]), 0.85, 1.2)],
    ['Цены соседних квартир', f.nbK ?? 1],
    ['Среда', 1 + (A.envEffect / 100) * (((env ?? 50) - 50) / 50)],
    ['Населённый пункт', A.localityK?.[f.locality] ?? 1],
    [f.market === 'new' ? 'Новостройка' : 'Вторичка', A.marketK?.[f.market] ?? 1],
    ['Крайний этаж', edge ? A.edgeFloorK : 1],
  ];
}
function estimateRent(f, env, A) {
  if (f.rentOverride) return { rent: f.rentOverride, kind: 'введена вами' };
  if (f.rent && !f.rentEstimated) return { rent: f.rent, kind: 'из данных' };
  if (f.rentRef) {  // средняя аренда похожих квартир в этом доме (или на этой улице)
    const raw = f.rentRef.rent;
    return { rent: Math.round(clampN(raw, A.rentMin, A.rentMax) / 500) * 500, kind: f.rentRef.level === 'house' ? 'по аренде в этом доме' : 'по аренде на этой улице', raw };
  }
  const raw = A.rentBase[roomsKey(f.rooms)] * rentFactors(f, env, A).reduce((m, [, v]) => m * v, 1);
  return { rent: Math.round(clampN(raw, A.rentMin, A.rentMax) / 500) * 500, kind: 'оценка модели', raw };
}

export function economics(f, env, A) {
  const { rent, kind, raw } = estimateRent(f, env, A);
  const invest = f.price + A.repairPerM2 * f.area + f.price * A.buyCostPct / 100;
  const months = Math.max(0, 12 - A.vacancyMonths);
  const revenue = rent * months;
  const mgmt = revenue * A.mgmtPct / 100, maint = revenue * A.maintPct / 100;
  const taxBase = revenue - mgmt;
  const tax = A.taxMode === 'ndfl13' ? taxBase * 0.13 : A.taxMode === 'self4' ? taxBase * 0.04 : 0;
  const propTax = f.price * A.propTaxPct / 100;
  const net = revenue - mgmt - maint - tax - propTax;
  const out = {
    rent, rentKind: kind, rentRaw: raw, invest, revenue, mgmt, maint, tax, propTax, net,
    gross: rent * 12 / f.price, netYield: net / invest, payback: net > 0 ? invest / net : Infinity,
    pricePerM2: f.price / f.area, monthlyNet: net / 12,
  };
  if (A.mortgageOn) {
    const loan = f.price * (1 - A.down / 100), r = A.rate / 100 / 12, n = A.years * 12;
    const pmt = r ? loan * r / (1 - Math.pow(1 + r, -n)) : loan / n;
    const equity = invest - loan;
    out.loan = loan; out.pmt = pmt; out.cashflow = net / 12 - pmt;
    out.cashOnCash = equity > 0 ? (net - 12 * pmt) / equity : 0; out.equity = equity;
  }
  return out;
}

// индекс выгодности 0–100: доходность, среда, цена против соседей
const clamp = (x, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, x));

// перепродажа: цена × (1 + сближение с соседями) × (1 + рост)^лет
// рост = базовый + среда + новостройка + пункт; налог 13% с прибыли, если владели меньше 5 лет
export function resale(f, env, disc, A, e) {
  const n = Math.max(1, A.horizon || 5), catchUp = clamp(disc ?? 0, -0.15, 0.15) * (A.catchUp ?? 0.5);
  const g = ((A.priceGrowth ?? 6) + (A.growthEnv ?? 0) * (((env ?? 50) - 50) / 50) + (f.market === 'new' ? (A.growthNew ?? 0) : 0) + (A.growthLoc?.[f.locality] ?? 0)) / 100;
  const exit = f.price * (1 + catchUp) * Math.pow(1 + g, n);
  const sellCost = exit * (A.sellCostPct ?? 0) / 100;
  const taxFree = A.saleTax === 'none' || (A.saleTax === 'auto' && n >= 5);
  const tax = taxFree ? 0 : Math.max(0, exit - Math.max(f.price, 1e6)) * 0.13;
  const proceeds = exit - sellCost - tax, invest = f.price * (1 + (A.buyCostPct ?? 0) / 100), profit = proceeds - invest;
  const cagr = proceeds > 0 ? Math.pow(proceeds / invest, 1 / n) - 1 : -1;
  // с арендой: деньги каждый год и продажа в конце, доходность — IRR этих потоков
  const rentTotal = e.net * n, investRent = e.invest, totalProfit = proceeds + rentTotal - investRent;
  const npv = r => -investRent + Array.from({ length: n }, (_, i) => (e.net + (i === n - 1 ? proceeds : 0)) / Math.pow(1 + r, i + 1)).reduce((s, x) => s + x, 0);
  let lo = -0.5, hi = 1; for (let i = 0; i < 40; i++) { const m = (lo + hi) / 2; npv(m) > 0 ? lo = m : hi = m; }
  return { years: n, g, catchUp, fair: f.med ? f.med * f.area : null, exit, growth: exit / f.price - 1, sellCost, tax, taxFree, proceeds, profit, cagr, rentTotal, totalProfit, irr: (lo + hi) / 2 };
}
export const GOALS = { rent: 'Сдавать', resale: 'Продать', mix: 'Оба' };
const goalLabel = { rent: 'Доходность аренды', resale: 'Рост цены', mix: 'Общая доходность' };
export function scoreParts(e, env, discount, A, rs) {
  const W = A?.scoreW || { yield: 70, env: 15, price: 15 }, sum = (W.yield + W.env + W.price) || 100, k = 100 / sum;
  const goal = rs ? (A?.goal || 'rent') : 'rent';
  const ret = goal === 'resale' ? rs.cagr : goal === 'mix' ? rs.irr : e.netYield;
  const rg = A?.retRange?.[goal];
  const lo = (goal === 'rent' ? (A?.yieldMin ?? 2) : (rg?.[0] ?? 0)) / (goal === 'rent' ? 100 : 100), hi = (goal === 'rent' ? (A?.yieldMax ?? 6) : (rg?.[1] ?? 10)) / 100;
  const y = clamp((ret - lo) / (hi - lo)), c = env == null ? 0.5 : clamp((env - 20) / 70), d = clamp(0.5 + (discount ?? 0) * 2.5);
  const wy = W.yield * k, we = W.env * k, wp = W.price * k;
  return [
    { key: 'yield', label: goalLabel[goal], max: wy, share: y, v: wy * y },
    { key: 'env', label: 'Среда вокруг', max: we, share: c, v: we * c },
    { key: 'price', label: 'Цена против соседей', max: wp, share: d, v: wp * d },
  ];
}
export const profitScore = (e, env, discount, A, rs) => Math.round(scoreParts(e, env, discount, A, rs).reduce((s, p) => s + p.v, 0));
export const verdict = s => s >= 65 ? ['Сильный вариант', 'good'] : s >= 45 ? ['Хороший вариант', 'ok'] : s >= 30 ? ['Средний вариант', 'mid'] : ['Слабый вариант', 'bad'];

export const fmt = n => Math.round(n).toLocaleString('ru-RU');
export const fmtM = n => n >= 1e6 ? (n / 1e6).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' млн ₽' : fmt(n) + ' ₽';
export const pct = (x, d = 1) => (x * 100).toLocaleString('ru-RU', { maximumFractionDigits: d, minimumFractionDigits: d }) + '%';
