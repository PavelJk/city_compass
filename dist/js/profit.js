// блок «Прибыль» в карточке квартиры: три сценария (сдавать, продать, и то и другое), срок владения, график по годам
import { resale, fmt, pct } from './finance.js';
import { state, D, esc } from './state.js';

const MAXY = 15;
let rentExtra = () => '';
export const setRentExtra = fn => { rentExtra = fn; };
const SCEN = [['rent', 'Сдавать', 'fa-key'], ['sale', 'Продать', 'fa-tag'], ['both', 'Вместе', 'fa-arrows-rotate']];

const sign = x => (x < 0 ? '−' : '+');
const mny = x => { const a = Math.abs(x), s = x < 0 ? '−' : ''; return s + (a >= 1e6 ? (a / 1e6).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' млн ₽' : fmt(a) + ' ₽'); };
const smny = x => sign(x) + mny(Math.abs(x));
const short = x => { const a = Math.abs(x); return (x < 0 ? '−' : '') + (a >= 1e6 ? (a / 1e6).toLocaleString('ru-RU', { maximumFractionDigits: 1 }) + ' млн' : Math.round(a / 1e3) + ' тыс'); };
const plural = n => (n % 10 === 1 && n % 100 !== 11 ? 'год' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'года' : 'лет');

export const years = () => Math.max(1, Math.min(MAXY, +state.cardYears || state.A.horizon || 5));
export const scenario = () => state.cardTab || state.A.goal || 'rent';

// всё, что нужно знать про квартиру за n лет владения
function calc(f, n) {
  const A = { ...state.A, horizon: n }, rs = resale(f, f.env, f.disc, A, f.e);
  const repair = f.e.invest - f.price * (1 + (A.buyCostPct || 0) / 100);  // подготовка к сдаче: нужна только если сдавать
  return { n, rs, repair, rent: rs.rentTotal, sale: rs.profit, both: rs.rentTotal + rs.profit - repair };
}

// итоговая карточка «аренда и продажа» — под деталями выбранного сценария (на вкладке «Вместе» всё это уже в деталях)
function total(c, tab) {
  if (tab === 'both') return '';
  return `<button class="pf-sum" data-act="pf-tab" data-v="both"><span class="t">Аренда и продажа вместе</span><b class="num ${c.both < 0 ? 'neg' : ''}">${smny(c.both)}</b>
    <em>аренда ${smny(c.rent)} · продажа ${smny(c.sale)}${c.repair > 0 ? ` · подготовка −${mny(c.repair)}` : ''} за ${c.n} ${plural(c.n)}</em></button>`;
}

const tile = (s, b, em = '') => `<div class="pf-tile"><small>${s}</small><b class="num">${b}</b>${em ? `<em>${em}</em>` : ''}</div>`;
const line = (a, b, cls = '') => `<tr class="${cls}"><td>${a}</td><td class="num">${b}</td></tr>`;

function detail(f, c, tab) {
  const e = f.e, rs = c.rs, n = c.n, A = state.A;
  if (tab === 'rent') {
    return `<div class="pf-tiles">${tile('В месяц чистыми', fmt(e.monthlyNet) + ' ₽', 'после налогов и расходов')}${tile('В год чистыми', fmt(e.net) + ' ₽', `аренда ${fmt(e.rent)} ₽ в месяц`)}
      ${tile('Доходность', pct(e.netYield), 'чистая, в год')}${tile('Окупаемость', isFinite(e.payback) ? e.payback.toFixed(1).replace('.', ',') + ' лет' : '—', 'вложения вернутся')}</div>
    <details class="pf-more"><summary>Расчёт и своя аренда</summary>${rentExtra(f)}</details>`;
  }
  if (tab === 'sale') {
    return `<div class="pf-tiles">${tile(`Цена через ${n} ${plural(n)}`, '≈ ' + mny(rs.exit), `${sign(rs.growth)}${Math.abs(rs.growth * 100).toFixed(0)}% к нынешней`)}${tile('Прибыль', smny(rs.profit), 'после расходов и налога')}
      ${tile('Рост в год', pct(rs.cagr), 'на вложенные деньги')}${tile('На руки', mny(rs.proceeds), 'после продажи')}</div>`;
  }
  return `<div class="pf-tiles">${tile(`Всего за ${n} ${plural(n)}`, smny(c.both), 'аренда + продажа')}${tile('Доходность в год', pct(rs.irr), 'вместе')}
      ${tile('Аренда', smny(c.rent), 'чистыми за срок')}${tile('Продажа', smny(c.sale), 'прибыль после расходов')}</div>`;
}

// график: накопленная прибыль по годам для трёх сценариев
function chart(f, n, tab) {
  const W = 320, H = 150, L = 46, R = 8, T = 10, B = 22, data = [];
  for (let t = 1; t <= MAXY; t++) data.push(calc(f, t));
  const keys = ['rent', 'sale', 'both'], all = data.flatMap(d => keys.map(k => d[k])).concat(0);
  const lo = Math.min(...all), hi = Math.max(...all), pad = (hi - lo) * 0.06 || 1;
  const X = t => L + (t - 1) / (MAXY - 1) * (W - L - R), Y = v => T + (hi + pad - v) / (hi - lo + 2 * pad) * (H - T - B);
  const path = k => data.map((d, i) => (i ? 'L' : 'M') + X(d.n).toFixed(1) + ' ' + Y(d[k]).toFixed(1)).join('');
  const ticks = [lo, 0, hi].filter((v, i, a) => a.indexOf(v) === i).map(v => `<g><line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" class="${v === 0 ? 'z' : 'g'}"/><text x="${L - 6}" y="${Y(v) + 3}" text-anchor="end">${short(v)}</text></g>`).join('');
  const xt = [1, 5, 10, 15].map(t => `<text x="${X(t)}" y="${H - 6}" text-anchor="middle">${t}</text>`).join('');
  const cur = data[n - 1], dots = keys.map(k => `<circle cx="${X(n)}" cy="${Y(cur[k])}" r="${k === tab ? 4.5 : 3}" class="d ${k}"/>`).join('');
  const rows = data.map(d => [Math.round(d.rent), Math.round(d.sale), Math.round(d.both)]), geo = [W, H, L, R, T, B, lo, hi, pad];
  return `<div class="pf-chart" data-rows='${JSON.stringify(rows)}' data-geo='${JSON.stringify(geo)}'><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Прибыль по годам">${ticks}
    <line x1="${X(n)}" x2="${X(n)}" y1="${T}" y2="${H - B}" class="m"/>
    ${keys.map(k => `<path d="${path(k)}" class="ln ${k}${k === tab ? ' on' : ''}"/>`).join('')}${dots}${xt}
    <g class="hv" hidden><line y1="${T}" y2="${H - B}"/>${keys.map(k => `<circle r="4" class="${k}"/>`).join('')}</g></svg>
    <div class="pf-tip" hidden></div>
    <div class="pf-legend"><span class="rent">аренда</span><span class="sale">продажа в этот год</span><span class="both">и то и другое</span><span class="u">по горизонтали — годы</span></div></div>`;
}

export function profitBody(f) {
  const n = years(), tab = scenario(), c = calc(f, n);
  const blk = (k, t, ic) => `<section class="pf-blk ${k}"><h4><i class="fa-solid ${ic}"></i>${t}</h4>${detail(f, c, k)}</section>`;
  return `${blk('rent', 'Сдавать в аренду', 'fa-key')}${blk('sale', 'Продать', 'fa-tag')}${blk('both', 'Аренда и продажа вместе', 'fa-arrows-rotate')}${chart(f, n, '')}`;
}

export function profitHTML(f) {
  const n = years(), tab = scenario();
  return `<section class="pf" data-id="${esc(f.id)}">
    <div class="pf-head"><h3>Прибыль</h3></div>
    <label class="pf-years"><span>Срок владения</span><input type="range" min="1" max="${MAXY}" value="${n}" data-pf-years aria-label="Срок владения, лет"><b class="num" id="pfYears">${n} ${plural(n)}</b></label>
    <div class="pf-body">${profitBody(f)}</div></section>`;
}

// перерисовать только тело блока и подписи (ползунок остаётся на месте)
export function refreshProfit(root) {
  const box = (root || document).querySelector('.pf'); if (!box) return;
  const f = D.byId.get(box.dataset.id); if (!f) return;
  const n = years(), tab = scenario();
  box.querySelector('.pf-body').innerHTML = profitBody(f);
  box.querySelectorAll('.pf-tabs button').forEach(b => b.classList.toggle('on', b.dataset.v === tab));
  box.querySelector('#pfYears').textContent = `${n} ${plural(n)}`;
}

// подсказка над графиком: наведите курсор или коснитесь — покажет значения за выбранный год, клик задаёт срок владения
function chartPoint(e) {
  const box = e.target.closest('.pf-chart'); if (!box) return null;
  const svg = box.querySelector('svg'), r = svg.getBoundingClientRect(), [W, H, L, R, T, B, lo, hi, pad] = JSON.parse(box.dataset.geo);
  const x = (e.clientX - r.left) / r.width * W; if (x < L - 6 || x > W - R + 6) return { box, off: true };
  const t = Math.max(1, Math.min(MAXY, Math.round(1 + (x - L) / (W - L - R) * (MAXY - 1))));
  const X = L + (t - 1) / (MAXY - 1) * (W - L - R), Y = v => T + (hi + pad - v) / (hi - lo + 2 * pad) * (H - T - B);
  return { box, svg, t, X, Y, rows: JSON.parse(box.dataset.rows)[t - 1], r, W };
}
function showTip(e) {
  const p = chartPoint(e); if (!p) return;
  const hv = p.box.querySelector('.hv'), tip = p.box.querySelector('.pf-tip');
  if (p.off) { hv.setAttribute('hidden', ''); tip.hidden = true; return; }
  const [rent, sale, both] = p.rows;
  hv.removeAttribute('hidden'); hv.querySelector('line').setAttribute('x1', p.X); hv.querySelector('line').setAttribute('x2', p.X);
  hv.querySelectorAll('circle').forEach((c, i) => { c.setAttribute('cx', p.X); c.setAttribute('cy', p.Y(p.rows[i])); });
  tip.innerHTML = `<b>Через ${p.t} ${plural(p.t)}</b><span class="rent">Аренда <em>${smny(rent)}</em></span><span class="sale">Продажа <em>${smny(sale)}</em></span><span class="both">Вместе <em>${smny(both)}</em></span>`;
  tip.hidden = false;
  const bw = p.box.clientWidth, tw = tip.offsetWidth, px = (p.X / p.W) * p.svg.clientWidth + 10;
  tip.style.left = Math.max(4, Math.min(bw - tw - 4, px + tw + 12 > bw ? px - tw - 20 : px)) + 'px';
}
function hideTip(e) {
  const box = e.target.closest?.('.pf-chart'); if (!box || box.contains(e.relatedTarget)) return;
  box.querySelector('.hv')?.setAttribute('hidden', ''); const t = box.querySelector('.pf-tip'); if (t) t.hidden = true;
}
const dock = document.getElementById('dock');
dock.addEventListener('pointermove', showTip);
dock.addEventListener('pointerdown', showTip);
dock.addEventListener('pointerout', hideTip);
dock.addEventListener('click', e => {
  const p = chartPoint(e); if (!p || p.off) return;
  state.cardYears = p.t; refreshProfit(dock);
});
