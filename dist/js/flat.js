// карточки квартир, правая панель, объяснение оценки
import { CATS, GROUPS } from './config.js';
import { scoreWord } from './score.js';
import { rentFactors, scoreParts, fmt, fmtM, pct, roomsKey, GOALS } from './finance.js';
import { profitHTML, refreshProfit, setRentExtra } from './profit.js';
import { recompute, visible, passes, passesExceptMarket, SORTERS, marketStats } from './model.js';
import { map, updateMarkers, drawCircle, syncPoi, fitFlats, focusOn, focusCell, selectedCell } from './map.js';
import { state, D, $, $$, esc, save, LS, actions, frame, MARKET_LABEL, ROOM_LABEL, NEAR_R } from './state.js';

// общие мелочи
const num1 = x => String(x).replace('.', ',');
export const roomName = f => ROOM_LABEL[roomsKey(f.rooms)];
const shortAddr = f => f.address && f.address !== f.name ? f.address : f.locality;
const payback = f => isFinite(f.e.payback) ? f.e.payback.toFixed(1).replace('.', ',') + ' лет' : '—';
const isFav = f => state.fav.includes(f.id);
const foldOpen = (k, d) => state.fold?.[k] ?? d;
state.fold = {};
state.gal = {};
state.filtersOpen = LS.get('filtersOpen2', false);  // фильтры по умолчанию свёрнуты
export const activeFilters = () => (state.f.market.length < 2 ? 1 : 0) + (state.f.rooms.length ? 1 : 0) + (state.f.loc ? 1 : 0) + (state.f.max !== Infinity ? 1 : 0) + (state.f.fav ? 1 : 0) + (state.f.photoOnly ? 1 : 0);
const filterBadge = () => { const n = activeFilters(); return n ? `<b class="fbadge">${n}</b>` : ''; };

const thumbSrc = p => p.replace('assets/photos/', 'assets/photos/t/');
// для списков берём уменьшенную копию, если её нет — оригинал
const picture = (f, i = 0, small = false) => {
  const src = (f.photos && f.photos[i]) || f.photo;
  if (!src) return `<span class="nophoto"><i class="fa-solid fa-house"></i><em>нет фото</em></span>`;
  const s = small ? thumbSrc(src) : src;
  return `<img src="${esc(s)}" loading="lazy" decoding="async" alt="" referrerpolicy="no-referrer" onerror="if(!this.dataset.f&&'${esc(src)}'!=='${esc(s)}'){this.dataset.f=1;this.src='${esc(src)}'}else this.remove()">`;
};
const galIdx = f => Math.min(state.gal?.[f.id] || 0, Math.max(0, (f.photos?.length || 1) - 1));
const photoTitle = f => f.photoShared ? ' title="Фото из другого объявления в этом доме или ЖК"' : f.photo ? '' : ' title="В объявлении нет фото"';
export const thumb = f => `<div class="thumb${f.photo ? '' : ' illoed'}"${photoTitle(f)}>${picture(f, 0, true)}</div>`;
const heart = f => `<button class="heart${isFav(f) ? ' on' : ''}" data-act="fav" data-id="${esc(f.id)}" aria-label="${isFav(f) ? 'Убрать из избранного' : 'В избранное'}"><i class="fa-${isFav(f) ? 'solid' : 'regular'} fa-heart"></i></button>`;
const mk = f => `<span class="mk ${f.market}">${MARKET_LABEL[f.market]}</span>`;

const goal = () => state.A.goal || 'rent';
const sgn = x => (x >= 0 ? '+' : '−') + Math.abs(x * 100).toFixed(0) + '%';
function mline(f) {
  const g = goal(), rs = f.rs, v = f.verdict[1];
  if (g === 'resale') return `<span class="v-${v}" title="Рост цены за ${rs.years} лет">${sgn(rs.growth)}</span><i>·</i><span title="Цена через ${rs.years} лет">≈ ${fmtM(Math.round(rs.exit / 1e4) * 1e4)}</span>`;
  if (g === 'mix') return `<span class="v-${v}" title="Общая доходность в год: аренда + продажа">${pct(rs.irr)}/год</span><i>·</i><span title="Рост цены за ${rs.years} лет">${sgn(rs.growth)} цена</span>`;
  return `<span class="v-${v}" title="Чистая доходность">${pct(f.e.netYield)}</span><i>·</i><span title="Окупаемость">${payback(f)}</span>`;
}
export const flatCard = f => `
  <div class="card${state.sel?.id === f.id ? ' sel' : ''}" data-act="open" data-id="${esc(f.id)}" role="button" tabindex="0">
    <div class="thumb${f.photo ? '' : ' illoed'}"${photoTitle(f)}>${picture(f, 0, true)}
      <span class="score v-${f.verdict[1]}" title="Оценка выгодности">${f.score}</span></div>
    <div class="cbody">
      <div class="crow"><span class="price num">${fmtM(f.price)}</span>${heart(f)}</div>
      <div class="meta">${f.complex ? esc(f.complex) + ' · ' : ''}${roomName(f)} · ${num1(f.area)} м² · ${esc(shortAddr(f))}</div>
      <div class="mline">${mline(f)}<i>·</i><span title="Индекс среды">среда ${f.env ?? '—'}</span></div>
      <div class="cfoot">${mk(f)}${f.own ? '<span class="mk own">Своя</span>' : ''}<span class="rank">№ ${f.rank} из ${D.flats.length}</span></div>
    </div>
  </div>`;

// фильтры
export function marketCards() {
  const st = marketStats(), cnt = k => D.flats.filter(f => f.market === k && passesExceptMarket(f)).length;
  return `<div class="mkts">${['new', 'secondary'].map(k => `<button class="mkt ${k}${state.f.market.includes(k) ? ' on' : ''}" data-act="mkt" data-v="${k}" aria-pressed="${state.f.market.includes(k)}">
      <span class="mk ${k}">${MARKET_LABEL[k]}</span><b class="num">${cnt(k)}</b>
      <small>${st[k].ppm ? fmt(st[k].ppm / 1000) + ' тыс. ₽/м²' : '—'} · ${st[k].yld != null ? pct(st[k].yld) : '—'}</small></button>`).join('')}</div>`;
}
export function filterBar(photoChip = true) {
  const prices = D.flats.map(f => f.price), lo = Math.min(...prices), hi = Math.max(...prices);
  const cur = Math.min(state.f.max, hi), locs = [...new Set(D.flats.map(f => f.locality))];
  return `<div class="filters">
    <div class="frow between"><span class="sub">Бюджет</span><span class="num" id="maxLabel">${state.f.max >= hi ? 'любая цена' : 'до ' + fmtM(cur)}</span></div>
    <input type="range" id="maxRange" min="${Math.floor(lo / 1e5) * 1e5}" max="${Math.ceil(hi / 1e5) * 1e5}" step="100000" value="${cur}" aria-label="Максимальная цена">
    <div class="frow">${Object.entries(ROOM_LABEL).map(([k, v]) => `<button class="chip${state.f.rooms.includes(k) ? ' on' : ''}" data-room="${k}">${v}</button>`).join('')}
      ${true ? `<button class="chip${state.f.photoOnly ? ' on' : ''}" data-photof="1"><i class="fa-regular fa-image"></i> Только с фото</button>` : ''}</div>
    <div class="frow fline">
      <button class="chip reset" data-act="freset"${activeFilters() ? '' : ' hidden'}><i class="fa-solid fa-rotate-left"></i> Сбросить</button>
      <button class="chip${state.f.fav ? ' on' : ''}" data-favf="1" title="Только избранное"><i class="fa-solid fa-heart"></i> Избранное</button>
      <select class="field" id="locSel" aria-label="Населённый пункт"><option value="">Все пункты</option>${locs.map(l => `<option${state.f.loc === l ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>
      ${photoChip ? `<select class="field" id="sortSel" aria-label="Сортировка">${[['score', 'Выгодные'], ['yield', 'Доходность аренды'], ['growth', 'Рост цены'], ['total', 'Общая доходность'], ['price', 'Дешёвые'], ['ppm', 'Дешевле за м²'], ['env', 'Лучшая среда']].map(([k, v]) => `<option value="${k}"${state.f.sort === k ? ' selected' : ''}>${v}</option>`).join('')}</select>` : ''}
    </div></div>`;
}
export function bindFilterBar(root, onChange) {
  const hi = Math.max(...D.flats.map(f => f.price));
  $('#maxRange', root).oninput = e => {
    const v = +e.target.value; state.f.max = v >= Math.ceil(hi / 1e5) * 1e5 ? Infinity : v;
    $('#maxLabel', root).textContent = state.f.max === Infinity ? 'любая цена' : 'до ' + fmtM(v); onChange();
  };
  $$('[data-room]', root).forEach(b => b.onclick = () => {
    const k = b.dataset.room, i = state.f.rooms.indexOf(k);
    i < 0 ? state.f.rooms.push(k) : state.f.rooms.splice(i, 1); b.classList.toggle('on'); onChange();
  });
  $('[data-favf]', root).onclick = e => { state.f.fav = !state.f.fav; e.currentTarget.classList.toggle('on', state.f.fav); onChange(); };
  const pf = $('[data-photof]', root);
  if (pf) pf.onclick = e => {
    state.f.photoOnly = !state.f.photoOnly; LS.set('photoOnly', state.f.photoOnly); e.currentTarget.classList.toggle('on', state.f.photoOnly);
    $$('[data-act=photoonly]').forEach(b => { b.classList.toggle('on', state.f.photoOnly); b.setAttribute('aria-pressed', state.f.photoOnly); }); onChange();
  };
  $('#locSel', root).onchange = e => { state.f.loc = e.target.value; onChange(); if (state.f.loc) fitFlats(visible()); };
  const ss = $('#sortSel', root); if (ss) ss.onchange = e => { state.f.sort = e.target.value; LS.set('sort', state.f.sort); onChange(); };
}

// правая панель
let dockKey = '';
export function renderDock() {
  const d = $('#dock');
  // анимация при смене вида (список, квартира, ячейка), но не при обновлении того же
  const key = state.sel ? state.sel.type + ':' + state.sel.id : 'list';
  if (key !== dockKey) { dockKey = key; d.classList.remove('swap'); void d.offsetWidth; d.classList.add('swap'); }
  if (!D.flats.length) { d.innerHTML = '<div class="empty"><i class="fa-solid fa-inbox"></i>Нет объявлений. Загрузите данные — раздел «Данные».</div>'; return; }
  if (state.sel?.type === 'flat') d.innerHTML = detailHTML(D.byId.get(state.sel.id));
  else if (state.sel?.type === 'cell') d.innerHTML = cellHTML(D.cells.find(c => c.id === state.sel.id));
  else if (state.sel?.type === 'bld') d.innerHTML = bldHTML(state.sel.id);
  else {
    d.innerHTML = `<div class="dock-head compact"><div class="dh-top"><h2>Квартиры</h2><span class="cnt" id="listCount"></span>
      <span class="dh-actions"><button class="ib" data-act="own-add" title="Добавить свою квартиру" aria-label="Добавить квартиру"><i class="fa-solid fa-plus"></i></button><button class="ib${state.f.sort !== 'score' ? ' on' : ''}" data-act="sort" title="Сортировка" aria-label="Сортировка" aria-haspopup="menu"><i class="fa-solid fa-arrow-down-wide-short"></i></button>
      <button class="ib ftoggle${state.filtersOpen ? ' open' : ''}" data-act="ftoggle" aria-expanded="${state.filtersOpen}" title="Фильтры" aria-label="Фильтры"><i class="fa-solid fa-sliders"></i><span id="fbadge">${filterBadge()}</span></button><button class="ib dockhide" data-act="dockhide" title="Скрыть панель — показать только карту" aria-label="Скрыть панель"><i class="fa-solid fa-angles-right"></i></button></span></div>
      ${goalSeg()}${sortMenu()}
      <div class="fwrap${state.filtersOpen ? '' : ' collapsed'}"${state.filtersOpen ? '' : ' inert'}><div class="fin">${marketCards()}${filterBar(false)}</div></div></div><div class="list" id="listBody"></div>`;
    bindFilterBar(d, refreshList); refreshList();
  }
}
const SORTS = [['score', 'Выгодные'], ['yield', 'Доходность аренды'], ['growth', 'Рост цены'], ['total', 'Общая доходность'], ['price', 'Дешёвые'], ['ppm', 'Дешевле за м²'], ['env', 'Лучшая среда']];
const sortMenu = () => `<div class="sortpop" role="menu" hidden>${SORTS.map(([k, t]) => `<button type="button" role="menuitemradio" aria-checked="${state.f.sort === k}" class="${state.f.sort === k ? 'on' : ''}" data-act="sort-pick" data-v="${k}">${t}<i class="fa-solid fa-check"></i></button>`).join('')}</div>`;
const goalSeg = () => `<div class="goal" role="group" aria-label="Цель"><span class="gl">Цель</span>${Object.entries(GOALS).map(([k, v]) => `<button class="${goal() === k ? 'on' : ''}" data-act="goal" data-v="${k}" aria-pressed="${goal() === k}">${v}</button>`).join('')}</div>`;
let listRaf = 0;
function refreshList() { if (!listRaf) { listRaf = 1; frame(() => { listRaf = 0; drawList(); }); } }
function drawList() {
  if (!$('#listBody')) return;
  const v = visible();
  $('#listCount').textContent = `${v.length} из ${D.flats.length}`;
  const fb = $('#fbadge'); if (fb) fb.innerHTML = filterBadge();
  $$('.mkt[data-v]').forEach(b => { b.classList.toggle('on', state.f.market.includes(b.dataset.v)); b.setAttribute('aria-pressed', state.f.market.includes(b.dataset.v)); b.querySelector('b').textContent = D.flats.filter(f => f.market === b.dataset.v && passesExceptMarket(f)).length; });
  const rs = $('.fline .reset'); if (rs) rs.hidden = !activeFilters();
  listItems = v; listShown = 0;
  $('#listBody').innerHTML = v.length ? '' : '<div class="empty"><i class="fa-solid fa-filter-circle-xmark"></i>Под фильтры ничего не подошло</div>';
  showMore();
  updateMarkers();
}
// карточки добавляются по 24 штуки, когда список докручен до конца: меньше DOM и загруженных картинок
const PAGE = 24;
let listItems = [], listShown = 0;
function showMore() {
  const box = $('#listBody'); if (!box) return;
  box.querySelector('.more')?.remove();
  const next = listItems.slice(listShown, listShown + PAGE);
  box.insertAdjacentHTML('beforeend', next.map(flatCard).join(''));
  listShown += next.length;
  if (listShown < listItems.length) box.insertAdjacentHTML('beforeend', '<div class="more" aria-hidden="true"></div>');
}
function checkMore() {
  const m = $('#listBody .more');
  if (m && m.getBoundingClientRect().top < innerHeight + 600) { showMore(); frame(checkMore); }
}
document.addEventListener('scroll', checkMore, { capture: true, passive: true });

// блоки карточки
// что есть в 15 минутах пешком (1200 м, 80 м/мин)
const WALK15 = [
  ['Магазин', ['grocery', 'supermarket', 'shop_other', 'bakery'], 'fa-basket-shopping'], ['Остановка', ['transport', 'tram'], 'fa-bus-simple'],
  ['Школа', ['school'], 'fa-school'], ['Детский сад', ['kindergarten'], 'fa-child-reaching'], ['Аптека или поликлиника', ['pharmacy', 'clinic'], 'fa-kit-medical'],
  ['Парк или сквер', ['park', 'square', 'forest'], 'fa-tree'], ['Кафе', ['cafe'], 'fa-mug-hot'], ['Спорт и детская площадка', ['sport', 'pitch', 'playground'], 'fa-dumbbell'],
];
function walk15(r) {
  const rows = WALK15.map(([label, cats, icon]) => {
    const ds = cats.map(c => r.near[c]).filter(Boolean).map(x => x.d), d = ds.length ? Math.min(...ds) : null;
    return { label, icon, d, min: d == null ? null : Math.max(1, Math.round(d / 80)), ok: d != null && d <= 1200 };
  });
  return { rows, n: rows.filter(x => x.ok).length };
}
function walk15Block(r) {
  const w = walk15(r), route = Object.values(r.near).some(x => x.route);
  return `<div class="w15"><div class="w15-head"><b class="num">${w.n} из ${w.rows.length}</b><span>в 15 минутах пешком${route ? '' : ' (по прямой)'}</span></div>
    <div class="w15-grid">${w.rows.map(x => `<div class="w15-i${x.ok ? ' ok' : ''}"><i class="fa-solid ${x.icon}"></i><span>${x.label}</span><em>${x.d == null ? 'нет рядом' : x.min + ' мин'}</em></div>`).join('')}</div></div>`;
}
function envBlock(r) {
  const wk = 100 / (Object.values(GROUPS).reduce((m, g) => m + g.w, 0) || 100);
  const bars = Object.entries(GROUPS).map(([k, g]) => { const mx = g.w * wk; return `<div class="bar"><span>${g.label}</span><i><u style="width:${Math.round(100 * (r.groups[k] || 0) / mx)}%"></u></i><span class="num">${Math.round(r.groups[k] || 0)}/${Math.round(mx)}</span></div>`; }).join('');
  const near = Object.entries(r.near).map(([k, v]) => ({ k, ...v, c: CATS[k] })).filter(x => x.c);
  const pos = near.filter(x => x.c.kind === 'pos').sort((a, b) => a.d - b.d).slice(0, 8), neg = near.filter(x => x.c.kind === 'neg').sort((a, b) => a.d - b.d);
  const row = (x, cls) => `<div class="fact"><span class="${cls}"><i class="fa-solid ${x.c.icon}"></i>${esc(x.c.label)}${x.name ? ' · ' + esc(x.name) : ''}</span><span class="num">${fmt(x.d)} м</span></div>`;
  return `${walk15Block(r)}<div class="bars">${bars}</div>
    <div class="facts">${pos.map(x => row(x, 'p')).join('')}${neg.map(x => row(x, 'n')).join('')}</div>
    <p class="note">${Object.values(r.near).some(x => x.route) ? 'Расстояния до магазинов, школ, остановок и других «плюсов» — пешком по улицам (до 2,2 км), до шумных и вредных объектов — по прямой. ' : 'Расстояния посчитаны по прямой. '}Наличие фактора — потенциальный риск, а не измеренный шум или загрязнение.</p>`;
}
function economicsTable(f) {
  const e = f.e, A = state.A, months = Math.max(0, 12 - A.vacancyMonths);
  const r = (a, b, cls = '') => `<tr class="${cls}"><td>${a}</td><td class="num">${b}</td></tr>`;
  const taxName = A.taxMode === 'ndfl13' ? 'НДФЛ 13%' : A.taxMode === 'self4' ? 'Налог самозанятого 4%' : 'Налог';
  let h = `<table class="tbl">
    ${r(`Аренда ${fmt(e.rent)} ₽ × ${months} мес.`, fmt(e.revenue) + ' ₽')}
    ${A.mgmtPct ? r('Управляющий', '−' + fmt(e.mgmt) + ' ₽') : ''}
    ${r(`Ремонт и расходы ${A.maintPct}%`, '−' + fmt(e.maint) + ' ₽')}
    ${A.taxMode !== 'none' ? r(taxName, '−' + fmt(e.tax) + ' ₽') : ''}
    ${r('Налог на имущество', '−' + fmt(e.propTax) + ' ₽')}
    ${r('Чистый доход за год', fmt(e.net) + ' ₽', 'total')}
  </table>
  <table class="tbl gap">
    ${r('Цена квартиры', fmt(f.price) + ' ₽')}
    ${r(`Подготовка к сдаче ${fmt(A.repairPerM2)} ₽/м²`, fmt(A.repairPerM2 * f.area) + ' ₽')}
    ${r(`Расходы на сделку ${A.buyCostPct}%`, fmt(f.price * A.buyCostPct / 100) + ' ₽')}
    ${r('Всего вложений', fmt(e.invest) + ' ₽', 'total')}
  </table>`;
  if (A.mortgageOn) h += `<table class="tbl gap">
    ${r(`Ипотека: взнос ${A.down}%, ${A.rate}%, ${A.years} лет`, 'платёж ' + fmt(e.pmt) + ' ₽/мес')}
    ${r('Свои деньги', fmt(e.equity) + ' ₽')}
    ${r('Денежный поток в месяц', (e.cashflow >= 0 ? '+' : '') + fmt(e.cashflow) + ' ₽', 'total')}
    ${r('Доходность на свои деньги', pct(e.cashOnCash))}</table>`;
  return h;
}
function rentBreakdown(f) {
  if (f.rentRef && f.e.rentKind.startsWith('по аренде')) {
    const cap = Math.abs(f.e.rentRaw - f.e.rent) > 250, n = f.rentRef.n;
    return `<p class="note rentnote">${f.rentRef.level === 'house' ? 'В этом доме' : 'На этой улице'} сдаётся ${n} ${n === 1 ? 'такая квартира' : n < 5 ? 'похожие квартиры' : 'похожих квартир'} (${roomName(f).toLowerCase()}, площадь ±30%): в среднем ${fmt(f.rentRef.rent)} ₽ в месяц${cap ? ` → ограничено диапазоном ${fmt(state.A.rentMin)}–${fmt(state.A.rentMax)} ₽` : ''}.</p>`;
  }
  if (f.e.rentKind !== 'оценка модели') return '';
  const A = state.A, fs = rentFactors(f, f.env, A).filter(([, v]) => Math.abs(v - 1) > 0.001), capped = Math.abs(f.e.raw - f.e.rent) > 250;
  return `<p class="note rentnote">Типичная аренда ${roomName(f).toLowerCase()} — ${fmt(A.rentBase[roomsKey(f.rooms)])} ₽${fs.map(([n, v]) => ` · ${n.toLowerCase()} ×${v.toFixed(2).replace('.', ',')}`).join('')}${capped ? ` → ограничено диапазоном ${fmt(A.rentMin)}–${fmt(A.rentMax)} ₽` : ''}</p>`;
}
function nearbyBlock(f) {
  let list = f.nb.filter(n => n.d <= NEAR_R), far = false;
  if (list.length < 3) { list = f.nb.slice(0, 3); far = list.some(n => n.d > NEAR_R); }
  list = [...list].sort(state.nearSort === 'dist' ? (a, b) => a.d - b.d : (a, b) => b.f.score - a.f.score);
  const inR = f.nb.filter(n => n.d <= NEAR_R);
  const medTxt = f.med ? `Медиана цены за м² рядом — ${fmt(f.med)} ₽, эта квартира ${f.disc >= 0 ? 'дешевле' : 'дороже'} на ${Math.abs(f.disc * 100).toFixed(0)}%.` : 'Для сравнения цены рядом слишком мало квартир.';
  const better = inR.filter(n => n.f.score > f.score).sort((a, b) => b.f.score - a.f.score)[0];
  const sum = `<div class="near-sum">${inR.length ? `В радиусе 1,5 км: ${inR.length}. ` : 'В радиусе 1,5 км других объявлений нет — показаны ближайшие. '}${medTxt}${better ? ` Выгоднее рядом: ${esc(better.f.name)} (${pct(better.f.e.netYield)}).` : inR.length ? ' Это лучшая по выгодности квартира в округе.' : ''}</div>`;
  const items = list.map(n => {
    const o = n.f, dp = (o.e.pricePerM2 - f.e.pricePerM2) / f.e.pricePerM2;
    return `<div class="mini" data-act="open" data-id="${esc(o.id)}" role="button" tabindex="0">${thumb(o)}
      <span><b class="num">${fmtM(o.price)}</b><small>${roomName(o)} · ${num1(o.area)} м² · ${n.d < 1000 ? fmt(n.d) + ' м' : (n.d / 1000).toFixed(1).replace('.', ',') + ' км'}</small></span>
      <span class="r"><span class="num">${pct(o.e.netYield)}</span><small class="delta ${dp <= 0 ? 'up' : 'down'}">${dp <= 0 ? '' : '+'}${(dp * 100).toFixed(0)}% ₽/м²</small></span></div>`;
  }).join('');
  return `<div class="frow between tight"><span class="sub">${far ? 'Ближайшие объявления' : 'Сортировка'}</span>
    <span class="frow"><button class="chip${state.nearSort === 'score' ? ' on' : ''}" data-act="near-sort" data-v="score">По выгодности</button><button class="chip${state.nearSort === 'dist' ? ' on' : ''}" data-act="near-sort" data-v="dist">По расстоянию</button></span></div>
    ${sum}<div class="stack">${items}</div>`;
}

// почему такая оценка
function whyReasons(f) {
  const e = f.e, A = state.A, out = [];
  const parts = scoreParts(e, f.env, f.disc, A, f.rs), [py, pe, pp] = parts, g = goal(), rs = f.rs;
  if (g !== 'rent') out.push({ t: (g === 'resale' ? rs.cagr : rs.irr) >= (g === 'resale' ? 0.06 : 0.09) ? 'pos' : (g === 'resale' ? rs.cagr : rs.irr) >= (g === 'resale' ? 0.03 : 0.05) ? 'mid' : 'neg',
    h: g === 'resale' ? `Прогноз: ${fmtM(Math.round(rs.exit / 1e4) * 1e4)} через ${rs.years} лет` : `Общая доходность ${pct(rs.irr)} в год`,
    x: g === 'resale' ? `Рост цен около ${pct(rs.g)} в год (среда, рынок, пункт) и сближение с ценой соседей ${sgn(rs.catchUp)}: ${sgn(rs.growth)} за ${rs.years} лет. После расходов на продажу${rs.taxFree ? '' : ' и налога'} остаётся ${fmtM(Math.round(rs.proceeds / 1e4) * 1e4)}, прибыль ${fmtM(Math.round(rs.profit / 1e4) * 1e4)} (${pct(rs.cagr)} в год).` : `За ${rs.years} лет: аренда чистыми ${fmtM(Math.round(rs.rentTotal / 1e4) * 1e4)} и продажа за ${fmtM(Math.round(rs.exit / 1e4) * 1e4)}. Общая прибыль ${fmtM(Math.round(rs.totalProfit / 1e4) * 1e4)} на вложения ${fmtM(Math.round(e.invest / 1e4) * 1e4)}.` });
  out.push({ t: e.netYield >= 0.05 ? 'pos' : e.netYield >= 0.035 ? 'mid' : 'neg', h: e.netYield >= 0.05 ? 'Хорошая доходность' : e.netYield >= 0.035 ? 'Доходность средняя' : 'Низкая доходность',
    x: `Аренда ${fmt(e.rent)} ₽ в месяц при цене ${fmtM(f.price)}: валовая доходность ${pct(e.gross)}. После простоя (${A.vacancyMonths} мес.), налогов, расходов и подготовки к сдаче остаётся ${pct(e.netYield)} чистыми.` });
  if (e.rentKind === 'оценка модели') out.push({ t: 'mid', h: 'Аренда — оценка модели', x: 'Реальной аренды по этой квартире в данных нет. Введите свою сумму в блоке «Доходность аренды» — расчёт обновится.' });
  if (f.disc == null) out.push({ t: 'mid', h: 'Мало данных о соседях', x: 'Рядом слишком мало объявлений, чтобы сравнить цену за м².' });
  else if (f.disc < -0.05) out.push({ t: 'neg', h: 'Дороже соседей', x: `Цена за м² (${fmt(e.pricePerM2)} ₽) выше медианы рядом (${fmt(f.med)} ₽) на ${Math.abs(f.disc * 100).toFixed(0)}%.` });
  else if (f.disc > 0.05) out.push({ t: 'pos', h: 'Дешевле соседей', x: `Цена за м² (${fmt(e.pricePerM2)} ₽) ниже медианы рядом (${fmt(f.med)} ₽) на ${(f.disc * 100).toFixed(0)}%.` });
  else out.push({ t: 'mid', h: 'Цена на уровне соседей', x: `Цена за м² (${fmt(e.pricePerM2)} ₽) близка к медиане рядом (${fmt(f.med)} ₽).` });
  if (f.env == null) out.push({ t: 'mid', h: 'Нет данных о среде', x: 'В радиусах анализа нет учитываемых мест — индекс не посчитан, в оценке взято нейтральное значение.' });
  else {
    const wk = 100 / (Object.values(GROUPS).reduce((m, g) => m + g.w, 0) || 100);
    const weak = Object.entries(GROUPS).filter(([k, g]) => (f.envR.groups[k] || 0) / (g.w * wk) < 0.35).map(([, g]) => g.label.toLowerCase());
    const neg = Object.entries(f.envR.near).map(([k, v]) => ({ ...v, c: CATS[k] })).filter(x => x.c?.kind === 'neg' && x.d < x.c.R * 0.7).sort((a, b) => b.c.sev / (1 + b.d / 100) - a.c.sev / (1 + a.d / 100)).slice(0, 3);
    const bits = [];
    if (weak.length) bits.push(`слабо представлено: ${weak.join(', ')}`);
    if (neg.length) bits.push(`рядом: ${neg.map(x => `${x.c.label.toLowerCase()} ${fmt(x.d)} м`).join(', ')}`);
    out.push({ t: f.env >= 60 ? 'pos' : f.env >= 40 ? 'mid' : 'neg', h: `Среда ${f.env} — ${scoreWord(f.env)}`, x: bits.length ? bits.join('; ') + '.' : 'Инфраструктура вокруг сбалансирована, заметных минусов нет.' });
  }
  return { parts, out };
}
function whyAdvice(f) {
  const e = f.e, A = state.A, parts = scoreParts(e, f.env, f.disc, A, f.rs), [py, pe, pp] = parts, target = 65;
  if (f.score >= target || goal() !== 'rent') return '';
  const yNeed = (target - pe.v - pp.v) / py.max;
  if (yNeed > 1) return 'Даже при идеальной доходности оценка не дотянет до уровня «сильный вариант» — мешают среда и цена относительно соседей.';
  const netNeed = (A.yieldMin + (A.yieldMax - A.yieldMin) * Math.max(0, yNeed)) / 100;
  const investNeed = e.net / netNeed, priceNeed = (investNeed - A.repairPerM2 * f.area) / (1 + A.buyCostPct / 100);
  const rentNeed = e.rent * ((netNeed * e.invest + e.propTax) / (e.net + e.propTax));
  const bits = [];
  if (priceNeed > 0 && priceNeed < f.price) bits.push(`цена около <b>${fmtM(Math.round(priceNeed / 1e4) * 1e4)}</b> (на ${((1 - priceNeed / f.price) * 100).toFixed(0)}% ниже)`);
  if (isFinite(rentNeed) && rentNeed > e.rent) bits.push(`аренда около <b>${fmt(Math.round(rentNeed / 500) * 500)} ₽/мес</b>`);
  return bits.length ? `Чтобы вариант стал сильным (${target}+), при прочих равных нужна ${bits.join(' или ')}.` : '';
}
function whyHTML(f) {
  const { out } = whyReasons(f), adv = whyAdvice(f);
  const icon = { pos: 'fa-circle-check', mid: 'fa-circle-minus', neg: 'fa-circle-xmark' };
  return `<div class="reasons">${out.map(r => `<div class="reason ${r.t}"><i class="fa-solid ${icon[r.t]}"></i><div><span class="rh">${r.h}</span><p>${r.x}</p></div></div>`).join('')}</div>
    ${adv ? `<div class="advice"><i class="fa-regular fa-lightbulb"></i><span>${adv}</span></div>` : ''}`;
}
export function mainMinus(f) {
  const { parts } = whyReasons(f), w = [...parts].sort((a, b) => (b.max - b.v) - (a.max - a.v))[0];
  return f.score >= 65 ? '—' : w.label;
}

// карточка квартиры
const fold = (key, title, body, def = false, aside = '', icon = 'fa-circle-info') =>
  `<details class="fold" data-fold="${key}"${foldOpen(key, def) ? ' open' : ''}><summary><i class="fi fa-solid ${icon}"></i><span>${title}</span>${aside ? `<em>${aside}</em>` : ''}<i class="chev fa-solid fa-chevron-down"></i></summary><div class="fbody">${body}</div></details>`;

function galleryControls(f) {
  const n = f.photoShared ? 1 : (f.photos?.length || 0);
  if (n < 2) return '';
  const i = galIdx(f);
  return `<button class="gal prev" data-act="gal" data-id="${esc(f.id)}" data-d="-1" aria-label="Предыдущее фото"><i class="fa-solid fa-chevron-left"></i></button>
    <button class="gal next" data-act="gal" data-id="${esc(f.id)}" data-d="1" aria-label="Следующее фото"><i class="fa-solid fa-chevron-right"></i></button>
    <span class="gal-count">${i + 1} / ${n}</span>
    <div class="gal-strip">${f.photos.slice(0, 8).map((p, k) => `<button class="gal-dot${k === i ? ' on' : ''}" data-act="gal-go" data-id="${esc(f.id)}" data-i="${k}" aria-label="Фото ${k + 1}" style="background-image:url('${esc(thumbSrc(p))}')"></button>`).join('')}</div>`;
}
function heroNote(f) { return f.photoShared ? '<span class="illo-note">Фото из другого объявления в этом доме / ЖК</span>' : ''; }
function heroInner(f) {
  return `${picture(f, galIdx(f))}${galleryControls(f)}${heroNote(f)}`;
}
const m10 = x => fmtM(Math.round(x / 1e4) * 1e4);
const kp = (s, b, em) => `<div class="kpi"><small>${s}</small><b class="num">${b}</b><em>${em}</em></div>`;
function ownTools(f) {
  const hasPoly = !!state.userPolys[String(f.address || '').trim()];
  return `<div class="own-tools"><button class="chip" data-act="own-edit-poly" data-id="${esc(f.id)}"><i class="fa-solid fa-vector-square"></i>Изменить контур</button><button class="chip" data-act="own-poly" data-id="${esc(f.id)}"><i class="fa-solid fa-draw-polygon"></i>Нарисовать заново</button>
    ${hasPoly ? `<button class="chip" data-act="own-poly-reset" data-id="${esc(f.id)}"><i class="fa-solid fa-rotate-left"></i>Сбросить участок</button>` : ''}
    ${f.own ? `<button class="chip" data-act="own-edit" data-id="${esc(f.id)}"><i class="fa-solid fa-pen"></i>Изменить</button><button class="chip danger" data-act="own-del" data-id="${esc(f.id)}"><i class="fa-regular fa-trash-can"></i>Удалить</button>` : ''}</div>`;
}
// оценка: кольцо, вердикт и три составляющие
function scoreBlock(f) {
  const parts = scoreParts(f.e, f.env, f.disc, state.A, f.rs);
  return `<div class="verdict ${f.verdict[1]}"><div class="ring" style="--p:${f.score}"><span>${f.score}</span></div>
    <div class="sc-body"><b>${f.verdict[0]}</b><div class="bars">${parts.map(p => `<div class="bar"><span>${p.label}</span><i><u style="width:${Math.round(100 * p.share)}%"></u></i><span class="num">${Math.round(p.v)}/${Math.round(p.max)}</span></div>`).join('')}</div></div></div>`;
}
// вкладка «Сдавать» блока прибыли: своя аренда, откуда взята сумма и годовой расчёт
setRentExtra(f => `<div class="rent-edit"><label for="rentIn">Аренда в месяц, ₽</label><input class="field" id="rentIn" type="number" min="0" step="500" placeholder="${fmt(f.e.rent)}" value="${f.rentOverride || ''}">${f.rentOverride ? '<button class="chip" data-act="rent-reset">Сбросить</button>' : ''}</div>${rentBreakdown(f)}${economicsTable(f)}`);

function detailHTML(f) {
  const e = f.e, inCmp = state.compare.includes(f.id), nearCnt = f.nb.filter(n => n.d <= NEAR_R).length, hasPoly = !!state.userPolys[String(f.address || '').trim()];
  const facts = [roomName(f), num1(f.area) + ' м²', f.floor ? `${f.floor} из ${f.floors} эт.` : ''].filter(Boolean);
  return `
  <div class="dock-head slim"><button class="back" data-act="back"><i class="fa-solid fa-arrow-left"></i>Все квартиры</button>
    <span class="tools">${heart(f)}<button class="tool${inCmp ? ' on' : ''}" data-act="cmp" data-id="${esc(f.id)}" aria-label="Сравнить" title="${inCmp ? 'Убрать из сравнения' : 'Добавить к сравнению'}"><i class="fa-solid fa-scale-balanced"></i></button></span></div>
  <div class="hero">${heroInner(f)}</div>
  <div class="sec head">
    <div class="ttl"><div class="big num">${fmt(f.price)} ₽</div><div class="ppm num">${fmt(e.pricePerM2)} ₽/м²</div></div>
    <div class="addr">${esc(f.address || f.name)}</div>
    <div class="facts">${facts.map(x => `<span>${esc(x)}</span>`).join('')}${mk(f)}${f.complex ? `<span>${esc(f.complex)}</span>` : ''}</div>
    ${f.approx ? '<div class="note"><i class="fa-solid fa-location-crosshairs"></i> Точное место не определено: квартира отмечена приблизительно.</div>' : ''}
    ${f.url ? `<a class="btn primary wide" href="${esc(f.url)}" target="_blank" rel="noopener"><i class="fa-solid fa-arrow-up-right-from-square"></i>Открыть объявление${f.source ? ' · ' + esc(f.source) : ''}</a>` : ''}
  </div>
  <div class="sec">${scoreBlock(f)}</div>
  <div class="sec">${profitHTML(f)}</div>
  <div class="accordion">
  ${fold('why', 'Что влияет на оценку', whyHTML(f), false, '', 'fa-chart-simple')}
  ${fold('near', 'Квартиры рядом', nearbyBlock(f), false, String(nearCnt), 'fa-building')}
  ${fold('env', 'Среда вокруг', envBlock(f.envR), false, f.env == null ? '—' : `индекс ${f.env} · ${walk15(f.envR).n}/8 пешком`, 'fa-tree-city')}
  ${fold('own', 'Контур дома на карте', ownTools(f), false, hasPoly ? 'свой' : 'автоматически', 'fa-draw-polygon')}
  </div>`;
}

// карточка территории
function cellHTML(c) {
  const all = c.flats, inside = all.filter(passes).sort(SORTERS[state.f.sort]), hidden = all.length - inside.length;
  return `
  <div class="dock-head slim"><button class="back" data-act="back"><i class="fa-solid fa-arrow-left"></i>Все квартиры</button></div>
  <div class="cell-head"><h2>Квартиры в ячейке</h2><div class="sub">${inside.length ? pluralFlats(inside.length) : 'нет подходящих'}${hidden ? ` · ещё ${hidden} скрыто фильтрами` : ''}</div></div>
  <div class="list">${inside.length ? inside.map(flatCard).join('') : '<div class="empty"><i class="fa-solid fa-filter-circle-xmark"></i>' + (all.length ? 'Все квартиры ячейки скрыты фильтрами' : 'В этой ячейке нет объявлений') + '</div>'}</div>`;
}
function bldHTML(i) {
  const all = D.buildings[i].f.map(id => D.byId.get(id)).filter(Boolean), v = all.filter(passes).sort(SORTERS[state.f.sort]), hidden = all.length - v.length;
  return `
  <div class="dock-head slim"><button class="back" data-act="back"><i class="fa-solid fa-arrow-left"></i>К ячейке</button></div>
  <div class="cell-head"><h2>${D.buildings[i].p ? 'Квартиры на участке' : 'Квартиры в доме'}</h2><button class="chip bld-edit" data-act="own-edit-poly" data-id="${esc(all[0].id)}"><i class="fa-solid fa-vector-square"></i>Изменить контур</button><div class="sub">${esc(shortAddr(all[0]))} · ${v.length ? pluralFlats(v.length) : 'нет подходящих'}${hidden ? ` · ещё ${hidden} скрыто фильтрами` : ''}</div></div>
  <div class="list">${v.length ? v.map(flatCard).join('') : '<div class="empty"><i class="fa-solid fa-filter-circle-xmark"></i>Все квартиры дома скрыты фильтрами</div>'}</div>`;
}
const pluralFlats = n => `${n} ${n % 10 === 1 && n % 100 !== 11 ? 'квартира' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'квартиры' : 'квартир'}`;

// выбор и действия
export function select(sel) {
  state.sel = sel;
  if (sel) document.dispatchEvent(new Event('ri5:select'));
  if (sel?.type === 'flat') {
    const f = D.byId.get(sel.id); drawCircle(f.lat, f.lng);
    focusOn([f.lat, f.lng], null, 16);
  } else if (sel?.type === 'cell') {
    const c = D.cells.find(x => x.id === sel.id); drawCircle(...c.center); focusCell(c);
  } else drawCircle();
  updateMarkers(); syncPoi(); renderDock();
  $('#dock').scrollTop = 0;
}
// клик по включённому виду выключает его, по выключенному включает; можно выключить оба — список пустой
export function toggleMarket(k) {
  const m = state.f.market, i = m.indexOf(k);
  state.f.market = i >= 0 ? m.filter(x => x !== k) : [...m, k];
}
export function toggleFav(id) {
  const i = state.fav.indexOf(id);
  i >= 0 ? state.fav.splice(i, 1) : state.fav.push(id);
  save('fav', state.fav);
  const on = state.fav.includes(id);
  $$(`.heart[data-id="${CSS.escape(id)}"], .heart[data-fav="${CSS.escape(id)}"]`).forEach(b => {
    b.classList.toggle('on', on); b.firstElementChild.className = `fa-${on ? 'solid' : 'regular'} fa-heart`;
    if (on) { b.classList.remove('burst'); void b.offsetWidth; b.classList.add('burst'); }
    b.setAttribute('aria-label', on ? 'Убрать из избранного' : 'В избранное');
  });
  if (state.f.fav) { if (state.view === 'map') refreshList(); else actions.renderPage?.(state.view); }
  else if (state.view === 'profile') actions.renderPage('profile');
}
function refreshOpen() { // перерисовать панель с сохранением прокрутки
  const top = $('#dock').scrollTop; renderDock(); $('#dock').scrollTop = top;
}
export function toggleCompare(id) {
  const i = state.compare.indexOf(id);
  if (i >= 0) state.compare.splice(i, 1);
  else { if (state.compare.length >= 4) state.compare.shift(); state.compare.push(id); }
  save('compare', state.compare); syncBadges();
  const on = state.compare.includes(id);
  $$(`.tool[data-id="${CSS.escape(id)}"]`).forEach(b => b.classList.toggle('on', on));
  if (state.view === 'compare') actions.renderPage('compare');
}
export function syncBadges() {
  state.compare = state.compare.filter(id => D.byId.has(id));
  state.fav = state.fav.filter(id => D.byId.has(id));
  const b = $('#cmpCount'); b.hidden = !state.compare.length; b.textContent = state.compare.length;
}
function setRent(id, v) {
  v ? state.rentOv[id] = v : delete state.rentOv[id];
  save('rentOv', state.rentOv); refreshAll();
}
export function refreshAll() {
  recompute(); updateMarkers();
  if (state.view === 'map') { const top = $('#dock').scrollTop; renderDock(); $('#dock').scrollTop = top; } else actions.renderPage(state.view);
}

$('#dock').addEventListener('input', e => {
  if (e.target.matches('[data-pf-years]')) { state.cardYears = +e.target.value; refreshProfit($('#dock')); }
});

$('#dock').addEventListener('click', e => {
  if (!e.target.closest('.sortpop, [data-act=sort]')) $('.sortpop')?.setAttribute('hidden', '');
  const el = e.target.closest('[data-act]'); if (!el) return;
  const a = el.dataset.act, id = el.dataset.id;
  if (a === 'open') select({ type: 'flat', id });
  else if (a === 'sort') { const p = $('.sortpop'); p.hidden = !p.hidden; }
  else if (a === 'sort-pick') { state.f.sort = el.dataset.v; LS.set('sort', state.f.sort); $('.sortpop').hidden = true; $$('.sortpop button').forEach(b => { b.classList.toggle('on', b === el); b.setAttribute('aria-checked', b === el); }); $('[data-act=sort]').classList.toggle('on', state.f.sort !== 'score'); refreshList(); }
  else if (a === 'pf-tab') { state.cardTab = el.dataset.v; refreshProfit($('#dock')); }
  else if (a === 'own-add') actions.ownAdd();
  else if (a === 'own-edit') actions.ownEdit(id);
  else if (a === 'own-del') actions.ownDelete(id);
  else if (a === 'own-poly') actions.ownPoly(id);
  else if (a === 'own-edit-poly') actions.ownEditPoly(id);
  else if (a === 'own-poly-reset') actions.ownPolyReset(id);
  else if (a === 'back') select(state.sel?.type === 'bld' ? { type: 'cell', id: selectedCell()?.id } : null);
  else if (a === 'gal' || a === 'gal-go') {
    const f = D.byId.get(id), n = f.photos?.length || 1, cur = galIdx(f);
    state.gal[id] = a === 'gal' ? (cur + +el.dataset.d + n) % n : +el.dataset.i; $('.hero').innerHTML = heroInner(f);
  }
  else if (a === 'fav') { e.stopPropagation(); toggleFav(id); }
  else if (a === 'ftoggle') {
    state.filtersOpen = !state.filtersOpen; LS.set('filtersOpen2', state.filtersOpen);
    const fw = $('.fwrap'); fw.classList.toggle('collapsed', !state.filtersOpen); fw.toggleAttribute('inert', !state.filtersOpen);
    el.classList.toggle('open', state.filtersOpen); el.setAttribute('aria-expanded', state.filtersOpen);
  }
  else if (a === 'photoonly') {
    state.f.photoOnly = !state.f.photoOnly; LS.set('photoOnly', state.f.photoOnly);
    el.classList.toggle('on', state.f.photoOnly); el.setAttribute('aria-pressed', state.f.photoOnly); refreshList();
  }
  else if (a === 'mkt') { toggleMarket(el.dataset.v); refreshList(); }
  else if (a === 'goal') { state.A.goal = el.dataset.v; save('A', state.A); refreshAll(); }
  else if (a === 'freset') {
    Object.assign(state.f, { market: ['new', 'secondary'], rooms: [], loc: '', max: Infinity, fav: false, photoOnly: false });
    LS.set('photoOnly', false); renderDock();
  }
  else if (a === 'cmp') toggleCompare(id);
  else if (a === 'near-sort') { state.nearSort = el.dataset.v; refreshOpen(); }
  else if (a === 'rent-reset') setRent(state.sel.id, 0);
});
$('#dock').addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.target.matches('[data-act=open]')) select({ type: 'flat', id: e.target.dataset.id });
});
$('#dock').addEventListener('change', e => { if (e.target.id === 'rentIn') setRent(state.sel.id, +e.target.value || 0); });
$('#dock').addEventListener('toggle', e => { const k = e.target.dataset?.fold; if (k) state.fold[k] = e.target.open; }, true);

actions.select = select;
