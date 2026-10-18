// пешие расстояния до мест: кратчайшие пути по улицам (Дейкстра) в фоновом потоке
// Вход:  {t:'init', buf, pois:[[cat,lat,lng,name]], R:{cat:радиус}, maxR}   — граф (walk.bin) и места
//        {t:'run', sources:[[id,lat,lng]]}                                  — точки, из которых считаем
// Выход: {t:'res', items:[[id, {ds:{cat:[м…]}, n:{cat:имя ближайшего}}|null]]}
let G = null, gridMap = null, poiHead = null, poiNext = null, poiOff = null, P = null, R = null, MAXR = 2200;
const K = 111320, CELL = 150, LAT0 = 56.64, KX = K * Math.cos(LAT0 * Math.PI / 180);
const key = (x, y) => x * 100003 + y;

function setup(m) {
  const dv = new DataView(m.buf), N = dv.getUint32(4, true), E2 = dv.getUint32(8, true);
  let o = 12;
  const lat = new Float32Array(m.buf, o, N); o += 4 * N;
  const lng = new Float32Array(m.buf, o, N); o += 4 * N;
  const off = new Int32Array(m.buf, o, N + 1); o += 4 * (N + 1);
  const adj = new Int32Array(m.buf, o, E2); o += 4 * E2;
  const w = new Float32Array(m.buf, o, E2);
  G = { N, lat, lng, off, adj, w, dist: new Float32Array(N).fill(Infinity), seen: new Uint8Array(N) };
  gridMap = new Map();
  for (let i = 0; i < N; i++) {
    const k = key(Math.floor((lat[i] - LAT0) * K / CELL), Math.floor((lng[i] - 47.8) * KX / CELL));
    (gridMap.get(k) || gridMap.set(k, []).get(k)).push(i);
  }
  R = m.R; MAXR = m.maxR; P = m.pois;
  // места, привязанные к ближайшему узлу графа (связный список по узлам)
  poiHead = new Int32Array(N).fill(-1); poiNext = new Int32Array(P.length).fill(-1); poiOff = new Float32Array(P.length);
  for (let i = 0; i < P.length; i++) {
    const s = nearest(P[i][1], P[i][2]);
    if (!s) { poiOff[i] = -1; continue; }
    poiOff[i] = s.d; poiNext[i] = poiHead[s.i]; poiHead[s.i] = i;
  }
}

// ближайший узел графа (поиск кольцами ячеек до ~750 м)
function nearest(la, lo) {
  const gx = Math.floor((la - LAT0) * K / CELL), gy = Math.floor((lo - 47.8) * KX / CELL);
  let best = -1, bd = Infinity;
  for (let r = 0; r <= 5; r++) {
    for (let dx = -r; dx <= r; dx++) for (let dy = -r; dy <= r; dy++) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) !== r) continue;
      const list = gridMap.get(key(gx + dx, gy + dy)); if (!list) continue;
      for (const i of list) {
        const ddx = (G.lng[i] - lo) * KX, ddy = (G.lat[i] - la) * K, d = ddx * ddx + ddy * ddy;
        if (d < bd) { bd = d; best = i; }
      }
    }
    if (best >= 0 && Math.sqrt(bd) <= r * CELL) break;
  }
  return best < 0 ? null : { i: best, d: Math.sqrt(bd) };
}

// двоичная куча (узел, расстояние)
let hv = new Float32Array(1 << 16), hn = new Int32Array(1 << 16), hs = 0;
function push(n, d) {
  if (hs === hv.length) { const v = new Float32Array(hs * 2), q = new Int32Array(hs * 2); v.set(hv); q.set(hn); hv = v; hn = q; }
  let i = hs++;
  while (i > 0) { const p = (i - 1) >> 1; if (hv[p] <= d) break; hv[i] = hv[p]; hn[i] = hn[p]; i = p; }
  hv[i] = d; hn[i] = n;
}
function pop() {
  const rn = hn[0], rd = hv[0], d = hv[--hs], n = hn[hs];
  let i = 0;
  for (;;) {
    let c = 2 * i + 1; if (c >= hs) break;
    if (c + 1 < hs && hv[c + 1] < hv[c]) c++;
    if (hv[c] >= d) break;
    hv[i] = hv[c]; hn[i] = hn[c]; i = c;
  }
  if (hs > 0) { hv[i] = d; hn[i] = n; }
  popD = rd; return rn;
}
let popD = 0;

function route(lat, lng) {
  const s = nearest(lat, lng); if (!s) return null;
  const { dist, off, adj, w, seen } = G, touched = [], ds = {}, names = {};
  hs = 0; dist[s.i] = 0; touched.push(s.i); push(s.i, 0);
  const lim = MAXR - s.d;
  while (hs) {
    const u = pop(), du = popD;
    if (du > dist[u]) continue;
    if (du > lim) break;
    for (let p = poiHead[u]; p >= 0; p = poiNext[p]) {
      const cat = P[p][0], d = s.d + du + poiOff[p];
      if (d > R[cat]) continue;
      const a = ds[cat] || (ds[cat] = []);
      let i = a.length; if (i < 6) a.push(d); else if (d < a[5]) i = 5; else continue;
      while (i > 0 && a[i - 1] > d) { a[i] = a[i - 1]; i--; }
      a[i] = d;
      if (i === 0) names[cat] = P[p][3];
    }
    for (let e = off[u]; e < off[u + 1]; e++) {
      const v = adj[e], nd = du + w[e];
      if (nd < dist[v]) { if (dist[v] === Infinity) touched.push(v); dist[v] = nd; push(v, nd); }
    }
  }
  for (const i of touched) dist[i] = Infinity;
  void seen;
  return { ds, n: names };
}

onmessage = e => {
  const m = e.data;
  if (m.t === 'init') { setup(m); postMessage({ t: 'ready', nodes: G.N, pois: P.length, snapped: P.length - Array.from(poiOff).filter(x => x < 0).length }); }
  else if (m.t === 'run') {
    let batch = [];
    for (const [id, lat, lng] of m.sources) {
      batch.push([id, route(lat, lng)]);
      if (batch.length >= 60) { postMessage({ t: 'res', items: batch, job: m.job }); batch = []; }
    }
    postMessage({ t: 'res', items: batch, job: m.job, last: true });
  }
};
