// Карта: подложки, сетка шестиугольников, подписи, места
import { CATS, MAP_CENTER } from './config.js';
import { fmtM, pct } from './finance.js';
import { passes } from './model.js';
import { state, D, esc, actions, NEAR_R, $, frame } from './state.js';
import { outline } from './hex.js';

export const map = L.map('map', { zoomControl: false, attributionControl: false, preferCanvas: false, zoomSnap: 1, wheelPxPerZoomLevel: 90 }).setView(MAP_CENTER, 12);
document.getElementById('mapStack').prepend(L.control.zoom({ position: 'topright' }).addTo(map).getContainer());
if (location.search.includes('debug')) window.__map = map;

// подложки
const tiles = {
  light: L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap', keepBuffer: 1 }),
  dark: L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, className: 'tiles-dark', attribution: '© OpenStreetMap', keepBuffer: 1 }),
  sat: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 18, attribution: 'Tiles © Esri', keepBuffer: 1 }),
};
let curTile = null;
export function applyBase() {
  const key = state.base === 'sat' ? 'sat' : (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
  if (curTile) map.removeLayer(curTile);
  curTile = tiles[key].addTo(map); curTile.bringToBack();
}

// цвета
// шкалы: красный → янтарный → лайм → изумруд
const STOPS = {
  profit: [[0, '#f0566b'], [30, '#f5b04c'], [50, '#9bd35a'], [75, '#28c28c']],
  env: [[20, '#f0566b'], [45, '#f5b04c'], [65, '#9bd35a'], [90, '#28c28c']],
  ppm: [[50000, '#28c28c'], [85000, '#9bd35a'], [105000, '#f5b04c'], [135000, '#f0566b']],
};
const RGB = Object.fromEntries(Object.entries(STOPS).map(([k, st]) => [k, st.map(([v, c]) => [v, [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16))])]));
const gradCache = new Map();
function grad(v, key) {
  if (v == null) return '#7c84ad';
  const ck = key + ':' + Math.round(v * 10) / 10;
  let out = gradCache.get(ck);
  if (out) return out;
  const st = RGB[key];
  if (v <= st[0][0]) out = `rgb(${st[0][1].join(',')})`;
  else if (v >= st[st.length - 1][0]) out = `rgb(${st[st.length - 1][1].join(',')})`;
  else for (let i = 1; i < st.length; i++) if (v <= st[i][0]) {
    const t = (v - st[i - 1][0]) / (st[i][0] - st[i - 1][0]), a = st[i - 1][1], b = st[i][1];
    out = `rgb(${a.map((n, k) => Math.round(n + (b[k] - n) * t)).join(',')})`; break;
  }
  gradCache.set(ck, out);
  return out;
}
const MKT_COLOR = { new: '#2bb7a0', secondary: '#f0894b', mixed: '#b9a14a' };

const cellFlats = c => state.show.flats ? c.flats.filter(passes) : [];
const cellMarket = fl => fl.every(f => f.market === 'new') ? 'new' : fl.every(f => f.market !== 'new') ? 'secondary' : 'mixed';
const cellMetric = (c, fl) => state.mode === 'market' ? fl.length : state.mode === 'env' ? c.envR.score
  : state.mode === 'ppm' ? fl.reduce((s, f) => s + f.e.pricePerM2, 0) / fl.length : Math.max(...fl.map(f => f.score));
const cellColor = (c, fl) => state.mode === 'market' ? MKT_COLOR[cellMarket(fl)] : grad(cellMetric(c, fl), state.mode);
const cellLabel = (c, fl) => {
  if (state.mode === 'market') return fl.length;
  const v = cellMetric(c, fl);
  return state.mode === 'env' ? (v ?? '·') : state.mode === 'ppm' ? Math.round(v / 1000) : v;
};

// сетка
const hexLayer = L.layerGroup().addTo(map), labelLayer = L.layerGroup().addTo(map);
const cellPoly = new Map(), labelMarker = new Map();
let outlineLayer = null, selCircle = null;
map.createPane('bld').style.zIndex = 610;  // выше значков мест (marker-pane 600), ниже подсказок (650)
const bldLayer = L.layerGroup().addTo(map), bldPoly = [];

// волна: ячейки у курсора приподнимаются
let cellPx = 60, lifted = new Set(), waveRaf = 0, cursor = null, moving = false;
function cachePoints() {
  D.cells.forEach(c => { c.pt = map.latLngToLayerPoint(c.center); });
  const a = D.cells.find(c => c.id === '0:0'), b = D.cells.find(c => c.id === '1:0');
  if (a && b) cellPx = Math.max(8, a.pt.distanceTo(b.pt));
}
function setLift(c, lift) {
  const el = cellPoly.get(c.id)?.getElement(), tile = labelMarker.get(c.id)?.getElement()?.firstChild;
  const h = (state.A.waveLift ?? 10) * lift, on = lift > 0.01;
  if (el) {
    el.style.transform = on ? `translateY(${-h}px) scale(${1 + lift * 0.16})` : '';
    el.style.filter = on ? `drop-shadow(0 ${h * .9}px ${h * 1.1}px rgba(0,0,0,${.32 * lift}))` : '';
  }
  if (tile) tile.style.transform = on ? `translateY(${-h}px)` : '';
}
function runWave() {
  waveRaf = 0;
  if (!cursor || !state.A.wave) return;
  const R = Math.max(1, state.A.waveCells ?? 3) * cellPx, now = new Set();
  for (const c of D.cells) {
    if (!c._vis) continue;
    const dx = c.pt.x - cursor.x, dy = c.pt.y - cursor.y;
    if (dx > R || dx < -R || dy > R || dy < -R) continue;
    const d = Math.hypot(dx, dy);
    if (d < R) { const t = 1 - d / R; setLift(c, t * t); now.add(c); }
  }
  for (const c of lifted) if (!now.has(c)) setLift(c, 0);
  lifted = now;
}
export function clearWave() {
  cursor = null;
  for (const c of lifted) setLift(c, 0);
  lifted.clear();
}
map.on('mousemove', e => {
  if (!state.A.wave || !D.cells.length || moving) return;
  cursor = e.layerPoint;
  if (!waveRaf) waveRaf = requestAnimationFrame(runWave);
});
map.getContainer().addEventListener('mouseleave', clearWave);
map.on('zoomstart movestart', () => { moving = true; clearWave(); });
map.on('zoomend moveend', () => { moving = false; });
map.on('zoomend', cachePoints);

export function buildHex() {
  cachePoints(); cellPoints.clear();
  hexLayer.clearLayers(); cellPoly.clear(); labelLayer.clearLayers(); labelMarker.clear();
  D.cells.forEach(c => { c._sig = ''; c._lsig = ''; c._vis = false; });
  bldLayer.clearLayers(); bldPoly.length = 0;
  buildBuildings();
  if (outlineLayer) map.removeLayer(outlineLayer);
  outlineLayer = L.polyline(outline(D.cells), { className: 'outline', weight: 1.5, interactive: false, lineJoin: 'round' }).addTo(map);
  updateMarkers();
}

// ячейку рисуем, только когда в ней есть квартиры, она выбрана или включена вся сетка
function ensureCell(c) {
  let p = cellPoly.get(c.id);
  if (p) return p;
  {
    p = L.polygon(c.shape, { className: 'hex', lineJoin: 'round', fillOpacity: 0, opacity: 1, weight: 1 });
    p.on('click', () => actions.select({ type: 'cell', id: c.id }));
    p.bindTooltip(() => {
      const fl = cellFlats(c);
      if (!fl.length) return `Без объявлений${c.envR.score != null ? ' · среда ' + c.envR.score : ''}`;
      const best = [...fl].sort((a, b) => b.score - a.score)[0];
      const g = state.A.goal || 'rent', ret = g === 'resale' ? `рост ${pct(best.rs.cagr)} в год` : g === 'mix' ? `доходность ${pct(best.rs.irr)} в год` : `чистая доходность ${pct(best.e.netYield)}`;
      return `${fl.length} ${fl.length === 1 ? 'квартира' : fl.length < 5 ? 'квартиры' : 'квартир'} · лучшая ${fmtM(best.price)}<br>${ret} · среда ${c.envR.score ?? '—'}`;
    }, { direction: 'top', sticky: false, className: 'tip', offset: [0, -6] });
    hexLayer.addLayer(p); cellPoly.set(c.id, p);
    labelMarker.set(c.id, L.marker(c.center, { interactive: false, keyboard: false, icon: L.divIcon({ className: 'tilewrap', iconSize: [48, 30], iconAnchor: [24, 15], html: '' }) }));
  }
  return p;
}

// контуры домов и участков с квартирами
function buildBuildings() {
  (D.buildings || []).forEach((b, i) => {
    const fl = b.f.map(id => D.byId.get(id)).filter(Boolean); if (!fl.length) return;
    bldPoly.push({ b, p: null, fl, i, dash: b.s ? '5 4' : b.p ? '2 4' : null, sig: '' });
  });
}
function bldShape(o) {
  const { b, fl, i } = o;
  const p = L.polygon(b.r, { pane: 'bld', className: 'bld', weight: 1.5, lineJoin: 'round', fillOpacity: .5 });
  const inSel = () => { const c = selectedCell(); return c ? fl.filter(f => passes(f) && f.cell === c) : []; };
  p.on('click', () => { const v = inSel(); if (v.length) actions.select(v.length === 1 ? { type: 'flat', id: v[0].id } : { type: 'bld', id: i }); });
  p.bindTooltip(() => { const n = inSel().length; return `${b.p ? 'Участок' : 'Дом'} · ${n} ${n === 1 ? 'квартира' : n < 5 ? 'квартиры' : 'квартир'} в продаже`; }, { sticky: true, className: 'tip', direction: 'top' });
  p.addTo(bldLayer);
  return p;
}

// перекраска: DOM трогаем только если у ячейки что-то изменилось
let upRaf = 0;
export function updateMarkers() { if (!upRaf) { upRaf = 1; frame(() => { upRaf = 0; paintAll(); }); } }
function paintAll() {
  const selFlat = state.sel?.type === 'flat' ? D.byId.get(state.sel.id) : null;
  const selCellId = selectedCell()?.id, selBld = state.sel?.type === 'bld' ? state.sel.id : -1;
  const nearCells = new Set();
  if (selFlat) selFlat.nb.filter(n => n.d <= NEAR_R).forEach(n => n.f.cell && nearCells.add(n.f.cell.id));
  const z = map.getZoom(), showLabels = z >= 12, emptyLabels = state.mode === 'env' && z >= 13 && state.show.grid;
  for (const c of D.cells) {
    const fl = cellFlats(c), sel = c.id === selCellId;
    let poly = cellPoly.get(c.id);
    if (!poly) {
      if (!fl.length && !state.show.grid && !sel) { c._vis = false; continue; }
      poly = ensureCell(c);
    }
    const dim = !!selFlat && !sel && !nearCells.has(c.id) && fl.length > 0;
    let color, op;
    if (fl.length) { color = cellColor(c, fl); op = dim ? .12 : .62; }
    else { color = grad(c.envR.score, 'env'); op = state.show.grid || sel ? .38 : 0; }
    c._vis = op > 0;
    const sig = `${color}|${op}|${sel ? 1 : 0}|${!fl.length && !state.show.grid && !sel ? 1 : 0}`;
    if (sig !== c._sig) {
      c._sig = sig;
      poly.setStyle({ fillColor: color, fillOpacity: op, weight: sel ? 2.5 : 1 });
      const el = poly.getElement();
      if (el) { el.classList.toggle('selhex', sel); el.classList.toggle('gridoff', !fl.length && !state.show.grid && !sel); }
    }
    // подписи
    const m = labelMarker.get(c.id);
    let html = '';
    // значение режима и число квартир под ним, если ячейка достаточно крупная
    if (showLabels && fl.length) html = `<div class="tile${sel ? ' sel' : ''}${dim ? ' dim' : ''}"><b>${cellLabel(c, fl)}</b>${cellPx >= 34 ? `<small>${fl.length} кв.</small>` : ''}</div>`;
    else if (emptyLabels && c.envR.score != null) html = `<div class="tile faint${sel ? ' sel' : ''}">${c.envR.score}</div>`;
    if (html !== c._lsig) {
      c._lsig = html;
      if (html) { m.setIcon(L.divIcon({ className: 'tilewrap', iconSize: [48, 30], iconAnchor: [24, 15], html })); if (!labelLayer.hasLayer(m)) labelLayer.addLayer(m); }
      else if (labelLayer.hasLayer(m)) labelLayer.removeLayer(m);
    }
  }
  for (const b of bldPoly) {
    const v = state.show.flats && selCellId ? b.fl.filter(f => passes(f) && f.cell?.id === selCellId) : [], on = v.length > 0, hasSel = (!!selFlat && v.includes(selFlat)) || b.i === selBld;
    const color = on ? MKT_COLOR[cellMarket(v)] : '#000', sig = `${on ? color : 0}|${hasSel ? 1 : 0}|${on ? v.length : 0}`;
    if (sig === b.sig) continue;
    b.sig = sig;
    if (!b.p) { if (!on) continue; b.p = bldShape(b); }
    b.p.setStyle(on ? { color: '#fff', fillColor: color, opacity: .95, fillOpacity: hasSel ? 1 : .9, weight: hasSel ? 3 : 1.5, dashArray: b.dash, interactive: true } : { opacity: 0, fillOpacity: 0, interactive: false });
    b.p.getElement()?.classList.toggle('off', !on);
  }
  if (outlineLayer?.getElement()) outlineLayer.getElement().style.opacity = state.show.grid ? 1 : 0;
  renderLegend(); legendMark();
}
map.on('zoomend', updateMarkers);

// отметка на шкале легенды для выбранной ячейки или квартиры
function legendMark() {
  const mk = $('#legend .lg-mark'); if (!mk) return;
  const mode = state.mode, st = STOPS[mode]; let v = null;
  if (st && state.sel) {
    if (state.sel.type === 'flat') { const f = D.byId.get(state.sel.id); v = f && (mode === 'env' ? f.env : mode === 'ppm' ? f.e.pricePerM2 : f.score); }
    else { const c = D.cells.find(x => x.id === state.sel.id), fl = c && cellFlats(c); if (c) v = fl.length ? cellMetric(c, fl) : mode === 'env' ? c.envR.score : null; }
  }
  if (v == null || !st) { mk.hidden = true; return; }
  const lo = st[0][0], hi = st[st.length - 1][0], t = Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
  mk.hidden = false; mk.style.left = (t * 100) + '%';
  mk.firstChild.textContent = mode === 'ppm' ? Math.round(v / 1000) + ' тыс.' : Math.round(v);
}
function renderLegend() {
  const box = $('#legend'), sw = (c, t) => `<span><i style="background:${c}"></i>${t}</span>`;
  const key = state.mode, gk = key + (state.A.goal || 'rent');
  if (box._key === gk) return;
  box._key = gk;
  setTimeout(legendMark, 0);
  if (key === 'market') {
    box.innerHTML = `<b>Новостройки и вторичка</b><div class="row">${sw(MKT_COLOR.new, 'новостройки')}${sw(MKT_COLOR.secondary, 'вторичка')}${sw(MKT_COLOR.mixed, 'и то и другое')}</div>`;
    return;
  }
  const info = {
    profit: [{ rent: 'Индекс выгодности аренды', resale: 'Индекс выгодности перепродажи', mix: 'Индекс выгодности: аренда и продажа' }[state.A.goal || 'rent'], 'profit', ['слабо', 'сильно']],
    env: ['Индекс среды', 'env', ['неблагоприятно', 'комфортно']],
    ppm: ['Цена за м²', 'ppm', ['дёшево', 'дорого']],
  }[key];
  const st = STOPS[info[1]], lo = st[0][0], hi = st[st.length - 1][0];
  const bar = st.map(([v, c]) => `${c} ${Math.round(100 * (v - lo) / (hi - lo))}%`).join(',');
  box.innerHTML = `<b>${info[0]}</b><div class="grad" style="background:linear-gradient(90deg,${bar})"><u class="lg-mark" hidden><span></span></u></div><div class="ends"><span>${info[2][0]}</span><span>${info[2][1]}</span></div>`;
}

// места: показываем только внутри выбранной ячейки
const iconLayer = L.layerGroup();
const inPoly = (lat, lng, ring) => {
  let c = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [yi, xi] = ring[i], [yj, xj] = ring[j];
    if ((yi > lat) !== (yj > lat) && lng < (xj - xi) * (lat - yi) / (yj - yi) + xi) c = !c;
  }
  return c;
};
export const selectedCell = () => {
  const s = state.sel; if (!s) return null;
  if (s.type === 'cell') return D.cells.find(c => c.id === s.id) || null;
  if (s.type === 'bld') return D.byId.get(D.buildings[s.id]?.f[0])?.cell || null;
  return D.byId.get(s.id)?.cell || null;
};
const cellPoints = new Map();  // кеш: ячейка → места внутри неё
function pointsIn(c) {
  let pts = cellPoints.get(c);
  if (!pts) {
    const la = c.poly.map(p => p[0]), lo = c.poly.map(p => p[1]), a = Math.min(...la), b = Math.max(...la), x = Math.min(...lo), y = Math.max(...lo);
    pts = D.points.filter(p => CATS[p[0]] && p[1] >= a && p[1] <= b && p[2] >= x && p[2] <= y && inPoly(p[1], p[2], c.poly));
    cellPoints.set(c, pts);
  }
  return pts;
}
let poiPending = 0;
export function syncPoi() {
  const stamp = ++poiPending;
  frame(() => {
    if (stamp !== poiPending) return;  // уже есть более свежий запрос
    iconLayer.clearLayers();
    const c = selectedCell();
    if (!state.show.poi || !c) { if (map.hasLayer(iconLayer)) map.removeLayer(iconLayer); return; }
    if (!map.hasLayer(iconLayer)) iconLayer.addTo(map);
    for (const p of pointsIn(c).slice(0, 700)) {
      const cat = CATS[p[0]];
      L.marker([p[1], p[2]], { keyboard: false, zIndexOffset: -500, icon: L.divIcon({ className: 'poiwrap', iconSize: [22, 22], iconAnchor: [11, 11], html: `<div class="poi ${cat.kind}"><i class="fa-solid ${cat.icon}"></i></div>` }) })
        .bindTooltip(`${cat.label}${p[3] ? ': ' + esc(p[3]) : ''}`, { direction: 'top', className: 'tip', offset: [0, -11] }).addTo(iconLayer);
    }
  });
}
export function drawCircle(lat, lng) {
  if (selCircle) { map.removeLayer(selCircle); selCircle = null; }
  if (lat != null) selCircle = L.circle([lat, lng], { radius: NEAR_R, color: '#6b7280', weight: 1.5, dashArray: '6 6', fillOpacity: .03, interactive: false }).addTo(map);
}
// показать все квартиры; если у карты ещё нет размера, пробуем позже
// приблизить к ячейке или точке и сдвинуть влево, чтобы она была по центру свободной части карты
function dockShift() {
  const d = $('#dock'), r = d?.getBoundingClientRect(), w = map.getSize().x;
  return r && innerWidth > 1000 && r.width && r.left < w ? Math.max(0, w - r.left) / 2 : 0;
}
export function focusOn(center, bounds, minZoom = 15) {
  const sh = dockShift(), size = map.getSize();
  let z = minZoom;
  if (bounds) z = Math.min(16, map.getBoundsZoom(bounds, false, L.point(60 + sh * 2, 90)));
  z = Math.max(z, Math.min(map.getZoom(), 17), minZoom - 1);
  const c = map.unproject(map.project(center, z).add([sh, 0]), z);
  map.setView(c, z, { animate: true });
}
export function focusCell(c) { focusOn(c.center, L.latLngBounds(c.shape)); }
export function fitFlats(fl) {
  if (!fl.length) return;
  const pts = fl.map(f => [f.lat, f.lng]);
  pts.length > 1 ? map.fitBounds(L.latLngBounds(pts).pad(0.15), { animate: true, maxZoom: 15 }) : map.setView(pts[0], Math.max(map.getZoom(), 14), { animate: true });
}
export function fitAll(tries = 0) {
  if (map.getSize().x < 50 || map.getSize().y < 50) { if (tries < 25) setTimeout(() => { map.invalidateSize(); fitAll(tries + 1); }, 200); return; }
  const core = D.flats.filter(f => f.locality === 'Йошкар-Ола'), pts = (core.length ? core : D.flats).map(f => [f.lat, f.lng]);
  if (pts.length > 1) map.fitBounds(L.latLngBounds(pts).pad(0.15), { animate: false });
}
