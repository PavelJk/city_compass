// общее состояние, утилиты и действия, которые подключают другие модули
import { DEFAULT_ASSUMPTIONS } from './config.js';

export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];
export const esc = t => String(t ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const LS = {
  get(k, d) { try { const v = JSON.parse(localStorage.getItem(k)); return v ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* приватный режим */ } },
};
// выполнить в следующем кадре; если вкладка скрыта и кадров нет — через 60 мс
export function frame(fn) {
  let done = false; const run = () => { if (!done) { done = true; fn(); } };
  requestAnimationFrame(run); setTimeout(run, 60);
}
export const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
export const getJson = async url => {
  try { const r = await fetch(url, { cache: 'no-cache' }); return r.ok ? await r.json() : null; } catch { return null; }
};
export const MARKET_LABEL = { new: 'Новостройка', secondary: 'Вторичка' };
export const ROOM_LABEL = { studio: 'Студия', r1: '1-комн.', r2: '2-комн.', r3: '3+ комн.' };
export const NEAR_R = 1500;

// сохранённые допущения поверх значений по умолчанию
export function mergeA(saved = {}) {
  const d = JSON.parse(JSON.stringify(DEFAULT_ASSUMPTIONS)), out = { ...d, ...saved };
  for (const k of ['rentBase', 'localityK', 'marketK', 'scoreW', 'groupW', 'growthLoc', 'retRange']) out[k] = { ...d[k], ...(saved[k] || {}) };
  return out;
}

export const state = {
  view: 'map', sel: null, mode: 'profit', base: LS.get('base', 'map'),
  show: { grid: LS.get('gridAll', false), flats: true, poi: true }, // grid=false: ячейки только там, где есть объявления
  f: { max: Infinity, rooms: [], loc: '', market: ['new', 'secondary'], sort: LS.get('sort', 'score'), fav: false, photoOnly: LS.get('photoOnly', false) },
  compare: LS.get('compare', []), fav: LS.get('fav', []), rentOv: LS.get('rentOv', {}), excluded: LS.get('excluded', []),
  userFlats: LS.get('userFlats', []), userPolys: LS.get('userPolys', {}),  // добавленные вручную квартиры и нарисованные участки
  A: mergeA(LS.get('A', {})),
  nearSort: 'score', rankSort: { k: 'score', dir: -1 },
};

// данные
export const D = { flats: [], points: [], cells: [], meta: {}, byId: new Map() };

// сюда модули кладут функции, чтобы не было циклических импортов
export const actions = {};

// сохранить локально и, если вошли, на сервер
export function save(key, val) { LS.set(key, val); actions.sync?.(); }
export const snapshot = () => ({ A: state.A, rentOv: state.rentOv, excluded: state.excluded, fav: state.fav, compare: state.compare, userFlats: state.userFlats, userPolys: state.userPolys });

// «без анимаций» из профиля
document.documentElement.classList.toggle('noanim', !!LS.get('noAnim', false));
