import { CATS, GROUPS, ROUTE_MAX } from './config.js';

const K = 111320; // м на градус широты
export function distM(aLat, aLng, bLat, bLng) {
  const dy = (aLat - bLat) * K, dx = (aLng - bLng) * K * Math.cos(aLat * Math.PI / 180);
  return Math.hypot(dx, dy);
}
const W_POS = [1, 0.5, 0.3, 0.2], W_NEG = [1, 0.4, 0.2];

function posFactor(d, c) {
  if (d > c.R) return 0;
  if (c.opt && d < c.opt) return 0.55 + 0.45 * d / c.opt; // слишком близко — шум
  const t = (d - c.opt) / (c.R - c.opt);
  return Math.pow(1 - t, 1.5);
}

// пространственный индекс: корзины по ~750 м на категорию, чтобы не перебирать все места
const BUCKET = 750, LAT0 = 56.64;
const dLat = BUCKET / K, dLng = BUCKET / (K * Math.cos(LAT0 * Math.PI / 180));
const bk = (lat, lng) => `${Math.floor(lat / dLat)},${Math.floor(lng / dLng)}`;
export function buildIndex(points) {
  const idx = {};
  for (const p of points) {
    if (!CATS[p[0]]) continue;
    const m = (idx[p[0]] ||= new Map()), key = bk(p[1], p[2]);
    (m.get(key) || m.set(key, []).get(key)).push(p);
  }
  return idx;
}

// idx — результат buildIndex; excluded — набор отключённых категорий
// walk — пешие расстояния до мест из walk-worker ({ds:{cat:[м]}, n:{cat:имя}}); для «плюсовых» мест ближе ROUTE_MAX берутся они
export function evaluate(lat, lng, idx, excluded = new Set(), walk = null) {
  const pos = {}, neg = {}, near = {}, kx = K * Math.cos(lat * Math.PI / 180);
  let any = false;
  const bx = Math.floor(lat / dLat), by = Math.floor(lng / dLng);
  for (const cat in idx) {
    if (excluded.has(cat)) continue;
    const c = CATS[cat], k = Math.ceil(c.R / BUCKET), m = idx[cat];
    if (walk && c.kind === 'pos' && c.R <= ROUTE_MAX) {
      const ds = walk.ds[cat];
      if (ds) {
        for (const d of ds) { any = true; (pos[c.group] ||= []).push(posFactor(d, c)); }
        near[cat] = { d: ds[0], name: walk.n[cat], route: true };
      }
      continue;
    }
    for (let i = -k; i <= k; i++) for (let j = -k; j <= k; j++) {
      const list = m.get(`${bx + i},${by + j}`); if (!list) continue;
      for (const p of list) {
        const dy = (lat - p[1]) * K, dx = (lng - p[2]) * kx, d = Math.sqrt(dx * dx + dy * dy);
        if (d > c.R) continue;
        any = true;
        const f = c.kind === 'pos' ? posFactor(d, c) : Math.pow(1 - d / c.R, 2);
        (c.kind === 'pos' ? (pos[c.group] ||= []) : (neg[cat] ||= [])).push(f);
        if (!near[cat] || d < near[cat].d) near[cat] = { d, name: p[3] };
      }
    }
  }
  if (!any) return { score: null, pos: 0, neg: 0, groups: {}, near };
  const wSum = Object.values(GROUPS).reduce((m, g) => m + g.w, 0) || 100, wk = 100 / wSum;
  let posTotal = 0; const groups = {};
  for (const g in GROUPS) {
    const a = (pos[g] || []).sort((x, y) => y - x).slice(0, 4);
    const s = a.reduce((m, f, i) => m + f * W_POS[i], 0);
    groups[g] = GROUPS[g].w * wk * (1 - Math.exp(-1.2 * s));
    posTotal += groups[g];
  }
  let negTotal = 0;
  for (const k in neg) {
    const a = neg[k].sort((x, y) => y - x).slice(0, 3);
    negTotal += CATS[k].sev * a.reduce((m, f, i) => m + f * W_NEG[i], 0);
  }
  const score = Math.max(5, Math.min(95, 40 + 0.65 * posTotal - Math.min(55, 2.5 * negTotal)));
  return { score: Math.round(score), pos: posTotal, neg: negTotal, groups, near };
}

export const scoreColor = s => s == null ? '#aab2ac' : s < 40 ? '#e5655d' : s < 60 ? '#e9bd4f' : s < 80 ? '#6fb97c' : '#238a52';
export const scoreWord = s => s == null ? 'нет данных' : s < 40 ? 'неблагоприятно' : s < 60 ? 'нейтрально' : s < 80 ? 'комфортно' : 'очень комфортно';
