// сетка шестиугольников в Web Mercator (метры), вся область — тоже шестиугольник
const R_EARTH = 6378137;
const toMerc = (lat, lng) => [R_EARTH * lng * Math.PI / 180, R_EARTH * Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360))];
const fromMerc = (x, y) => [(2 * Math.atan(Math.exp(y / R_EARTH)) - Math.PI / 2) * 180 / Math.PI, x / R_EARTH * 180 / Math.PI];

// side — сторона ячейки в метрах проекции, rings — число колец вокруг центра
export function buildGrid(centerLatLng, side, rings, inset = 0.93) {
  const [cx, cy] = toMerc(...centerLatLng), cells = [];
  const w = Math.sqrt(3) * side; // pointy-top
  for (let q = -rings; q <= rings; q++) {
    for (let r = Math.max(-rings, -q - rings); r <= Math.min(rings, -q + rings); r++) {
      const x = cx + w * (q + r / 2), y = cy + 1.5 * side * r;
      const poly = [], shape = [];
      for (let i = 0; i < 6; i++) {
        const a = Math.PI / 180 * (60 * i - 30);
        poly.push(fromMerc(x + side * Math.cos(a), y + side * Math.sin(a)));
        shape.push(fromMerc(x + side * inset * Math.cos(a), y + side * inset * Math.sin(a)));
      }
      cells.push({ id: `${q}:${r}`, q, r, center: fromMerc(x, y), poly, shape });
    }
  }
  return cells;
}

// внешний контур: рёбра ячеек без соседа
const DIRS = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]]; // сосед напротив ребра i (вершины i и i+1)
export function outline(cells) {
  const ids = new Set(cells.map(c => c.id)), segs = [];
  for (const c of cells) DIRS.forEach(([dq, dr], i) => {
    if (!ids.has(`${c.q + dq}:${c.r + dr}`)) segs.push([c.poly[i], c.poly[(i + 1) % 6]]);
  });
  return segs;
}
