// пешие маршруты: граф улиц и расчёт в фоновом потоке (walk-worker.js)
import { CATS, ROUTE_MAX } from './config.js';
import { state, D, actions } from './state.js';

export const walk = { status: 'idle', nodes: 0, pois: 0, done: 0, total: 0 }; // idle | loading | ready | off | error
let worker = null, job = 0, cellIndex = new Map(), pending = 0, flushTimer = 0, flushNeeded = false;

function applyBatch(items) {
  for (const [id, res] of items) {
    if (id.startsWith('f:')) { const f = D.byId.get(id.slice(2)); if (f) f.walk = res || null; }
    else { const c = cellIndex.get(id.slice(2)); if (c) c.walk = res || null; }
  }
  walk.done += items.length; flushNeeded = true;
  if (!flushTimer) flushTimer = setTimeout(() => { flushTimer = 0; if (flushNeeded) { flushNeeded = false; actions.walkUpdated?.(walk.done >= walk.total); } }, 400);
}

async function ensureWorker() {
  if (worker) return true;
  walk.status = 'loading';
  try {
    const r = await fetch('data/walk.bin'); if (!r.ok) throw new Error('нет графа');
    const buf = await r.arrayBuffer();
    // только «плюсовые» места в пределах пешей доступности: шум и запахи от расстояния по улицам не зависят
    const R = {}; for (const [k, c] of Object.entries(CATS)) if (c.kind === 'pos' && c.R <= ROUTE_MAX) R[k] = c.R;
    const pois = D.points.filter(p => R[p[0]] != null);
    worker = new Worker('js/walk-worker.js');
    await new Promise((ok, fail) => {
      worker.onmessage = e => { if (e.data.t === 'ready') { walk.nodes = e.data.nodes; walk.pois = e.data.snapped; ok(); } };
      worker.onerror = fail;
      worker.postMessage({ t: 'init', buf, pois, R, maxR: ROUTE_MAX }, [buf]);
    });
    worker.onmessage = e => {
      const m = e.data; if (m.t !== 'res' || m.job !== job) return;
      applyBatch(m.items);
      if (m.last) { walk.status = 'ready'; }
    };
    return true;
  } catch (e) {
    walk.status = 'error'; worker = null; return false;
  }
}

// считаем маршруты для квартир и ячеек, при перестройке сетки — заново
export async function computeWalk() {
  if (!state.A.walkRoute) { walk.status = 'off'; return; }
  if (!await ensureWorker()) return;
  cellIndex = new Map(D.cells.map(c => [c.id, c]));
  const sources = [...D.flats.map(f => ['f:' + f.id, f.lat, f.lng]), ...D.cells.map(c => ['c:' + c.id, c.center[0], c.center[1]])];
  walk.done = 0; walk.total = sources.length; walk.status = 'ready'; job++;
  worker.postMessage({ t: 'run', sources, job });
}

export function walkOff() {
  job++; walk.status = 'off';
  D.flats.forEach(f => { f.walk = null; }); D.cells.forEach(c => { c.walk = null; });
}
