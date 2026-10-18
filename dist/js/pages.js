// страницы: рейтинг, сравнение, модель, данные, профиль
import { CATS, GROUPS, PRESETS, LOCALITIES } from './config.js';
import { scoreColor } from './score.js';
import { economics, fmt, fmtM, pct, resale } from './finance.js';
import { recompute, passes, buildCells } from './model.js';
import { updateMarkers, buildHex, clearWave, syncPoi, applyBase } from './map.js';
import { walk, computeWalk, walkOff } from './walk.js';
import { auth, register, login, logout, updateProfile, changePassword, deleteAccount } from './api.js';
import { state, D, $, $$, esc, save, mergeA, actions, MARKET_LABEL, LS, snapshot } from './state.js';
import { filterBar, bindFilterBar, activeFilters, marketCards, mainMinus, thumb, flatCard, roomName, select, toggleCompare, toggleFav, toggleMarket, refreshAll, syncBadges } from './flat.js';

const num1 = x => String(x).replace('.', ',');
const goMap = id => { actions.setView('map'); select({ type: 'flat', id }); };

// рейтинг
const COLS = [
  ['rank', '№', f => f.rank, 'score'],
  ['name', 'Квартира', f => `<span class="nm">${esc(roomName(f))} · ${esc(f.address || f.name)}</span>`, null],
  ['mkt', 'Рынок', f => MARKET_LABEL[f.market], 'mkt'], ['loc', 'Район', f => esc(f.locality), 'loc'],
  ['price', 'Цена', f => fmtM(f.price), 'price'], ['area', 'м²', f => num1(f.area), 'area'],
  ['ppm', '₽/м²', f => fmt(f.e.pricePerM2), 'ppm'], ['rent', 'Аренда/мес', f => fmt(f.e.rent) + ' ₽', 'rent'],
  ['yield', 'Доходность', f => `<span class="tag ${f.verdict[1]}">${pct(f.e.netYield)}</span>`, 'yield'],
  ['pay', 'Окупаемость', f => isFinite(f.e.payback) ? f.e.payback.toFixed(1).replace('.', ',') + ' лет' : '—', 'pay'],
  ['exit', 'Цена после продажи', f => fmtM(Math.round(f.rs.exit / 1e4) * 1e4), 'exit'], ['growth', 'Рост цены', f => `<span class="tag ${f.rs.growth >= 0.2 ? 'good' : f.rs.growth >= 0.1 ? 'ok' : 'mid'}">${(f.rs.growth >= 0 ? '+' : '−') + Math.abs(f.rs.growth * 100).toFixed(0)}%</span>`, 'growth'],
  ['irr', 'Аренда + продажа', f => pct(f.rs.irr) + '/год', 'irr'],
  ['env', 'Среда', f => `<span class="dot" style="background:${scoreColor(f.env)}"></span> ${f.env ?? '—'}`, 'env'],
  ['score', 'Оценка', f => f.score, 'score'],
  ['why', 'Что снижает оценку', f => `<span class="note">${mainMinus(f)}</span>`, null],
  ['fav', '', f => `<button class="heart${state.fav.includes(f.id) ? ' on' : ''}" data-fav="${esc(f.id)}" aria-label="Избранное"><i class="fa-${state.fav.includes(f.id) ? 'solid' : 'regular'} fa-heart"></i></button>`, null],
];
const SORT_VAL = { score: f => f.score, mkt: f => f.market, loc: f => f.locality, price: f => f.price, area: f => f.area, ppm: f => f.e.pricePerM2, rent: f => f.e.rent, yield: f => f.e.netYield, exit: f => f.rs.exit, growth: f => f.rs.growth, irr: f => f.rs.irr, pay: f => f.e.payback, env: f => f.env ?? -1 };
const RIGHT = new Set(['price', 'area', 'ppm', 'rent', 'yield', 'exit', 'growth', 'irr', 'pay', 'env', 'score', 'rank']);

function renderRank() {
  const v = $('#view-rank');
  v.innerHTML = `<div class="wrap"><h1>Рейтинг квартир</h1><p class="lead">Все объявления по выгодности: сдача в аренду, перепродажа или то и другое — цель выбирается в панели карты. Нажмите на заголовок столбца для сортировки, на строку — чтобы открыть квартиру на карте.</p>
    <div class="panel" id="rankFilters">${marketCards()}${filterBar()}</div><div class="tablewrap" id="rankTable"></div></div>`;
  bindFilterBar(v, drawRankTable);
  // выпадающая «сортировка» из фильтров управляет таблицей
  const SMAP = { score: 'score', yield: 'yield', growth: 'growth', total: 'irr', price: 'price', ppm: 'ppm', env: 'env' }, ss = $('#sortSel', v);
  if (ss) {
    const cur = Object.keys(SMAP).find(k => SMAP[k] === state.rankSort.k); if (cur) ss.value = cur;
    ss.onchange = e => { const k = SMAP[e.target.value]; state.rankSort = { k, dir: ['price', 'ppm'].includes(k) ? 1 : -1 }; drawRankTable(); };
  }
  drawRankTable();
  // перерисовка идёт через actions.renderPage — иначе пропадает кнопка закрытия окна
  $$('[data-act=mkt]', v).forEach(b => b.onclick = () => { toggleMarket(b.dataset.v); actions.renderPage('rank'); });
  $$('[data-act=freset]', v).forEach(b => b.onclick = () => {
    Object.assign(state.f, { market: ['new', 'secondary'], rooms: [], loc: '', max: Infinity, fav: false, photoOnly: false });
    LS.set('photoOnly', false); actions.renderPage('rank');
  });
}
const RANK_PAGE = 40;  // строки рисуются порциями: 1000+ строк × 17 ячеек разом сильно тормозят телефон
function drawRankTable() {
  const s = state.rankSort, key = SORT_VAL[s.k] || SORT_VAL.score, box = $('#rankTable');
  const rs = $('#rankFilters .reset'); if (rs) rs.hidden = !activeFilters();
  const rows = D.flats.filter(passes).sort((a, b) => { const x = key(a), y = key(b); return (x > y ? 1 : x < y ? -1 : 0) * s.dir; });
  const rowHtml = f => `<tr data-id="${esc(f.id)}">${COLS.map(c => `<td class="${RIGHT.has(c[0]) ? 'r num' : ''}">${c[2](f)}</td>`).join('')}</tr>`;
  box.innerHTML = `<table class="data"><thead><tr>${COLS.map(c => `<th data-sort="${c[3] || ''}" class="${RIGHT.has(c[0]) ? 'r ' : ''}${c[3] === s.k ? 'sorted' : ''}">${c[1]}${c[3] === s.k ? (s.dir < 0 ? ' ↓' : ' ↑') : ''}</th>`).join('')}</tr></thead><tbody></tbody></table>
    <button class="btn more-rows" type="button" hidden></button>`;
  const tb = $('tbody', box), more = $('.more-rows', box), wrap = box.closest('.wrap');
  let shown = 0;
  const next = () => {
    if (shown >= rows.length) return;
    const part = rows.slice(shown, shown + RANK_PAGE); shown += part.length;
    tb.insertAdjacentHTML('beforeend', part.map(rowHtml).join(''));
    more.hidden = shown >= rows.length; more.textContent = `Показать ещё · ${rows.length - shown}`;
  };
  next();
  more.onclick = next;
  if (wrap) wrap.onscroll = () => { if (!more.hidden && wrap.scrollTop + wrap.clientHeight > wrap.scrollHeight - 600) next(); };
  box.onclick = e => {
    const th = e.target.closest('th[data-sort]');
    if (th) {
      const k = th.dataset.sort; if (!k) return;
      state.rankSort = { k, dir: s.k === k ? -s.dir : (['pay', 'ppm', 'price', 'loc', 'mkt'].includes(k) ? 1 : -1) }; return drawRankTable();
    }
    const h = e.target.closest('[data-fav]');
    if (h) { e.stopPropagation(); return toggleFav(h.dataset.fav); }
    const tr = e.target.closest('tbody tr'); if (tr) goMap(tr.dataset.id);
  };
}

// сравнение
// просмотр фото в модальном окне: стрелки, клавиши ← → Esc, клик вне фото закрывает
function openPhoto(f) {
  const list = (f?.photos?.length ? f.photos : f?.photo ? [f.photo] : []);
  if (!list.length) return;
  let i = 0;
  const box = document.createElement('div');
  box.className = 'lightbox'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true');
  const show = () => {
    box.innerHTML = `<button class="lb-x" data-lb="close" aria-label="Закрыть"><i class="fa-solid fa-xmark"></i></button>
      ${list.length > 1 ? '<button class="lb-nav prev" data-lb="prev" aria-label="Назад"><i class="fa-solid fa-chevron-left"></i></button><button class="lb-nav next" data-lb="next" aria-label="Вперёд"><i class="fa-solid fa-chevron-right"></i></button>' : ''}
      <img src="${esc(list[i])}" alt="" referrerpolicy="no-referrer"><div class="lb-cap">${esc(roomName(f))} · ${esc(f.address || f.name)}${list.length > 1 ? ` · ${i + 1}/${list.length}` : ''}</div>`;
  };
  const close = () => { box.remove(); document.removeEventListener('keydown', key, true); };
  const go = d => { i = (i + d + list.length) % list.length; show(); };
  const key = e => {
    if (e.key === 'Escape') { e.stopPropagation(); close(); } else if (e.key === 'ArrowLeft') go(-1); else if (e.key === 'ArrowRight') go(1);
  };
  box.onclick = e => {
    const b = e.target.closest('[data-lb]');
    if (b) { const a = b.dataset.lb; a === 'close' ? close() : go(a === 'next' ? 1 : -1); } else if (e.target.tagName !== 'IMG') close();
  };
  document.addEventListener('keydown', key, true);
  show(); document.body.appendChild(box);
}

function renderCompare() {
  syncBadges();
  const v = $('#view-compare'), items = state.compare.map(id => D.byId.get(id)).filter(Boolean);
  if (!items.length) {
    v.innerHTML = `<div class="wrap"><h1>Сравнение</h1><p class="lead">Добавьте до четырёх квартир кнопкой весов в карточке — здесь они встанут рядом, лучшие значения подсветятся.</p>
      <div class="panel empty"><i class="fa-solid fa-scale-balanced"></i><p>Пока ничего не выбрано.</p><button class="btn primary" data-go="map">Выбрать на карте</button></div></div>`;
    $('[data-go]', v).onclick = () => actions.setView('map'); return;
  }
  const rows = [
    ['Фото', f => f.photo ? `<button class="lnk" type="button" data-photo="${esc(f.id)}"><i class="fa-regular fa-image"></i> Открыть${f.photos?.length > 1 ? ` (${f.photos.length})` : ''}</button>` : '—', () => 0, 0], ['Рынок', f => MARKET_LABEL[f.market], () => 0, 0], ['Цена', f => fmtM(f.price), f => f.price, -1], ['Площадь', f => num1(f.area) + ' м²', f => f.area, 1],
    ['Цена за м²', f => fmt(f.e.pricePerM2) + ' ₽', f => f.e.pricePerM2, -1], ['Аренда в месяц', f => fmt(f.e.rent) + ' ₽', f => f.e.rent, 1],
    ['Чистыми в месяц', f => fmt(f.e.monthlyNet) + ' ₽', f => f.e.monthlyNet, 1], ['Чистая доходность', f => pct(f.e.netYield), f => f.e.netYield, 1],
    [`Цена через ${state.A.horizon} лет`, f => '≈ ' + fmtM(Math.round(f.rs.exit / 1e4) * 1e4), f => f.rs.exit, 1], ['Рост цены', f => (f.rs.growth >= 0 ? '+' : '−') + Math.abs(f.rs.growth * 100).toFixed(0) + '%', f => f.rs.growth, 1],
    ['Прибыль с продажи', f => fmtM(Math.round(f.rs.profit / 1e4) * 1e4), f => f.rs.profit, 1], ['Доходность аренда + продажа', f => pct(f.rs.irr) + ' в год', f => f.rs.irr, 1],
    ['Окупаемость', f => isFinite(f.e.payback) ? f.e.payback.toFixed(1).replace('.', ',') + ' лет' : '—', f => f.e.payback, -1],
    ['Всего вложений', f => fmtM(f.e.invest), f => f.e.invest, -1], ['Индекс среды', f => f.env ?? '—', f => f.env ?? -1, 1],
    ['Цена против соседей', f => f.disc == null ? '—' : (f.disc >= 0 ? 'ниже на ' : 'выше на ') + Math.abs(f.disc * 100).toFixed(0) + '%', f => f.disc ?? -9, 1],
    ['Оценка', f => `${f.score} · ${f.verdict[0]}`, f => f.score, 1], ['Что снижает оценку', f => mainMinus(f), () => 0, 0],
  ];
  const n = items.length;
  const out = ['<div class="c h"></div>', ...items.map(f => `<div class="c h cmp-head"><div class="ct">${esc(roomName(f))} · ${esc(f.address || f.name)}</div>
      <div class="frow"><button class="chip" data-open="${esc(f.id)}">На карте</button><button class="chip" data-del="${esc(f.id)}">Убрать</button></div></div>`)];
  rows.forEach(([label, show, val, dir]) => {
    const vals = items.map(val), best = dir === 0 ? NaN : dir > 0 ? Math.max(...vals) : Math.min(...vals);
    out.push(`<div class="c h">${label}</div>`, ...items.map(f => `<div class="c num${n > 1 && val(f) === best ? ' best' : ''}">${show(f)}</div>`));
  });
  v.innerHTML = `<div class="wrap"><h1>Сравнение</h1><p class="lead">Зелёным отмечено лучшее значение в строке.</p>
    <div class="cmp" style="grid-template-columns:190px repeat(${n},minmax(180px,1fr))">${out.join('')}</div></div>`;
  $$('[data-photo]', v).forEach(b => b.onclick = () => openPhoto(D.byId.get(b.dataset.photo)));
  $$('[data-open]', v).forEach(b => b.onclick = () => goMap(b.dataset.open));
  $$('[data-del]', v).forEach(b => b.onclick = () => toggleCompare(b.dataset.del));
}

// модель: коэффициенты
const SAMPLE = { area: 54, rooms: '2-комн.', locality: 'Йошкар-Ола', market: 'secondary', price: 5500000, floor: 3, floors: 9 };
const walkStatus = () => ({ idle: 'граф ещё не загружен', loading: 'загружаю граф улиц…', ready: walk.done >= walk.total && walk.total ? `граф: ${walk.nodes.toLocaleString('ru-RU')} узлов, маршруты готовы` : `считаю маршруты: ${walk.done} из ${walk.total}`, off: 'маршруты выключены', error: 'граф улиц недоступен — расчёт по прямой' }[walk.status] || '');
const gridKm = () => '≈ ' + (Math.sqrt(3) * (+state.A.gridSide || 700) * 0.55 / 1000).toFixed(2).replace('.', ',') + ' км';
export function rebuildGrid() { clearWave(); buildCells(); recompute(); buildHex(); updateMarkers(); if (state.sel?.type === 'cell') actions.select(null); syncPoi(); computeWalk(); }
const getPath = (o, p) => p.split('.').reduce((x, k) => x?.[k], o);
function field(path, label, { step = 1, unit = '', hint = '' } = {}) {
  return `<label class="fld"><span class="fl">${label}</span><span class="inp"><input class="field" type="number" step="${step}" data-k="${path}" value="${getPath(state.A, path)}">${unit ? `<em>${unit}</em>` : ''}</span>${hint ? `<small>${hint}</small>` : ''}</label>`;
}
function previewHTML() {
  const e = economics(SAMPLE, 55, state.A), rs = resale(SAMPLE, 55, 0, state.A, e);
  return `Типовая 2-комнатная, 54 м², 3 этаж из 9, Йошкар-Ола, вторичка, цена 5,5 млн ₽, среда 55: аренда <b>${fmt(e.rent)} ₽/мес</b>, чистая доходность <b>${pct(e.netYield)}</b>, окупаемость <b>${isFinite(e.payback) ? e.payback.toFixed(1).replace('.', ',') + ' лет' : '—'}</b>; перепродажа через ${rs.years} лет за <b>${fmtM(Math.round(rs.exit / 1e4) * 1e4)}</b> (${pct(rs.cagr)} в год).`;
}
// какой набор сейчас выбран: тот, у которого совпадают его параметры и аренда; после ручных правок — никакой
function currentPreset() {
  const base = mergeA({}), A = state.A;
  return Object.keys(PRESETS).find(k => {
    const p = PRESETS[k].set, sc = p.rentScale || 1;
    return Object.entries(p).filter(([n]) => n !== 'rentScale').every(([n, v]) => A[n] === v)
      && Object.entries(base.rentBase).every(([n, v]) => A.rentBase[n] === Math.round(v * sc / 500) * 500)
      && ['vacancyMonths', 'maintPct', 'taxMode'].filter(n => !(n in p)).every(n => A[n] === base[n]);
  }) || null;
}
const markPreset = v => { const cur = currentPreset(); $$('[data-preset]', v).forEach(b => { b.classList.toggle('on', b.dataset.preset === cur); b.setAttribute('aria-pressed', b.dataset.preset === cur); }); };
function applyPreset(key) {
  const p = PRESETS[key].set, base = mergeA({}), k = p.rentScale || 1;
  const A = { ...base, ...Object.fromEntries(Object.entries(p).filter(([n]) => n !== 'rentScale')) };
  A.rentBase = Object.fromEntries(Object.entries(base.rentBase).map(([n, v]) => [n, Math.round(v * k / 500) * 500]));
  state.A = A; save('A', A); refreshAll();
}
const calcOpen = new Set();
function renderCalc() {
  const A = state.A, v = $('#view-calc');
  const grp = Object.entries(GROUPS).map(([k, g]) => field('groupW.' + k, g.label, { unit: 'вес' })).join('');
  const cats = kind => Object.entries(CATS).filter(([, c]) => c.kind === kind).map(([k, c]) => `<label><input type="checkbox" data-cat="${k}"${state.excluded.includes(k) ? '' : ' checked'}><i class="fa-solid ${c.icon}"></i>${c.label}</label>`).join('');
  v.innerHTML = `<div class="wrap"><h1>Модель и коэффициенты</h1>
    <p class="lead">Все показатели считаются по этим допущениям. Измените их под себя — рейтинг, карта и карточки пересчитаются сразу${auth.user ? ', настройки сохраняются в вашем профиле' : ''}.</p>
    <div class="presets">${Object.entries(PRESETS).map(([k, p]) => `<button class="preset${currentPreset() === k ? ' on' : ''}" data-preset="${k}" aria-pressed="${currentPreset() === k}"><span>${p.label}</span><small>${p.note}</small></button>`).join('')}</div>
    <div class="panel preview" id="preview">${previewHTML()}</div>
    <div class="calc-list">
      <details class="panel fold-panel" data-sec="Аренда"${calcOpen.has('Аренда') ? ' open' : ''}><summary><h3>Аренда</h3><i class="chev fa-solid fa-chevron-down"></i></summary><p class="hint">Типичная аренда по комнатности с поправками, всегда в заданном диапазоне. Свою сумму можно ввести в карточке квартиры.</p>
        <div class="form">${field('rentBase.studio', 'Студия', { step: 500, unit: '₽/мес' })}${field('rentBase.r1', '1-комнатная', { step: 500, unit: '₽/мес' })}${field('rentBase.r2', '2-комнатная', { step: 500, unit: '₽/мес' })}${field('rentBase.r3', '3+ комнат', { step: 500, unit: '₽/мес' })}
        ${field('rentMin', 'Аренда не ниже', { step: 500, unit: '₽/мес' })}${field('rentMax', 'Аренда не выше', { step: 500, unit: '₽/мес' })}${field('nbEffect', 'Влияние цен соседей', { step: 0.05, unit: 'степень', hint: '0 — не учитывать' })}</div>
        <h4>Поправки к аренде</h4>
        <div class="form">${field('envEffect', 'Влияние среды', { unit: '±%', hint: 'при индексе 100 / 0' })}${field('marketK.new', 'Новостройка', { step: 0.01, unit: '×' })}${field('marketK.secondary', 'Вторичка', { step: 0.01, unit: '×' })}${field('edgeFloorK', 'Крайний этаж', { step: 0.01, unit: '×', hint: 'первый и последний' })}
          ${LOCALITIES.map(l => field('localityK.' + l, l, { step: 0.01, unit: '×' })).join('')}</div></details>
      <details class="panel fold-panel" data-sec="Расходы и налоги"${calcOpen.has('Расходы и налоги') ? ' open' : ''}><summary><h3>Расходы и налоги</h3><i class="chev fa-solid fa-chevron-down"></i></summary><p class="hint">Из аренды вычитаются простой, расходы, налог на доход и налог на имущество.</p>
        <div class="form">${field('vacancyMonths', 'Простой в год', { step: 0.5, unit: 'мес.' })}${field('maintPct', 'Ремонт и расходы', { unit: '% аренды' })}${field('mgmtPct', 'Управляющий', { unit: '% аренды' })}
          <label class="fld"><span class="fl">Налог на доход</span><select class="field" data-k="taxMode"><option value="ndfl13"${A.taxMode === 'ndfl13' ? ' selected' : ''}>НДФЛ 13%</option><option value="self4"${A.taxMode === 'self4' ? ' selected' : ''}>Самозанятый 4%</option><option value="none"${A.taxMode === 'none' ? ' selected' : ''}>Не учитывать</option></select></label>
          ${field('propTaxPct', 'Налог на имущество', { step: 0.05, unit: '% цены' })}${field('repairPerM2', 'Подготовка к сдаче', { step: 500, unit: '₽/м²' })}${field('buyCostPct', 'Расходы на сделку', { step: 0.5, unit: '% цены' })}</div>
        <h4>Ипотека</h4>
        <div class="form"><label class="fld"><span class="fl">Покупка</span><select class="field" data-k="mortgageOn"><option value="0"${A.mortgageOn ? '' : ' selected'}>За свои</option><option value="1"${A.mortgageOn ? ' selected' : ''}>С ипотекой</option></select></label>
          ${field('down', 'Первый взнос', { unit: '%' })}${field('rate', 'Ставка', { step: 0.1, unit: '% год.' })}${field('years', 'Срок', { unit: 'лет' })}</div></details>
      <details class="panel fold-panel" data-sec="Перепродажа"${calcOpen.has('Перепродажа') ? ' open' : ''}><summary><h3>Перепродажа</h3><i class="chev fa-solid fa-chevron-down"></i></summary><p class="hint">Цена через несколько лет и сколько останется после продажи. Цель (сдавать, продать или оба) переключается в панели карты.</p>
        <div class="form"><label class="fld"><span class="fl">Цель</span><select class="field" data-k="goal"><option value="rent"${A.goal === 'rent' ? ' selected' : ''}>Сдавать в аренду</option><option value="resale"${A.goal === 'resale' ? ' selected' : ''}>Перепродать</option><option value="mix"${A.goal === 'mix' ? ' selected' : ''}>Аренда, потом продажа</option></select></label>
          ${field('horizon', 'Срок до продажи', { unit: 'лет' })}${field('priceGrowth', 'Рост цен в год', { step: 0.5, unit: '%' })}${field('sellCostPct', 'Расходы на продажу', { step: 0.5, unit: '% цены' })}
          <label class="fld"><span class="fl">Налог с продажи</span><select class="field" data-k="saleTax"><option value="auto"${A.saleTax === 'auto' ? ' selected' : ''}>13% с прибыли, если владели &lt; 5 лет</option><option value="none"${A.saleTax === 'none' ? ' selected' : ''}>Не учитывать</option></select></label></div></details>
      <details class="panel fold-panel" data-sec="Индекс выгодности"${calcOpen.has('Индекс выгодности') ? ' open' : ''}><summary><h3>Индекс выгодности</h3><i class="chev fa-solid fa-chevron-down"></i></summary><p class="hint">Оценка 0–100: доходность, среда и цена против соседей. Веса нормируются к 100.</p>
        <div class="form">${field('scoreW.yield', 'Доходность аренды', { unit: 'вес' })}${field('scoreW.env', 'Среда вокруг', { unit: 'вес' })}${field('scoreW.price', 'Цена против соседей', { unit: 'вес' })}
          ${field('yieldMin', 'Доходность на 0 баллов', { step: 0.5, unit: '%' })}${field('yieldMax', 'Доходность на максимум', { step: 0.5, unit: '%' })}</div></details>
      <details class="panel fold-panel" data-sec="Сетка и карта"${calcOpen.has('Сетка и карта') ? ' open' : ''}><summary><h3>Сетка и карта</h3><i class="chev fa-solid fa-chevron-down"></i></summary><p class="hint">Размер ячеек и волна при наведении.</p>
        <div class="form">${field('gridSide', 'Размер ячейки', { step: 50, unit: gridKm() })}
          <label class="fld"><span class="fl">Волна при наведении</span><select class="field" data-k="wave"><option value="1"${A.wave ? ' selected' : ''}>Включена</option><option value="0"${A.wave ? '' : ' selected'}>Выключена</option></select></label>
          ${field('waveCells', 'Радиус волны', { step: 0.5, unit: 'ячеек', hint: 'сколько ячеек вокруг курсора поднимаются' })}${field('waveLift', 'Высота подъёма', { step: 1, unit: 'px' })}</div>
        <div class="btns row" style="margin:14px 0 0">${[450, 700, 1000].map(v => `<button class="chip${+A.gridSide === v ? ' on' : ''}" data-grid="${v}">${{ 450: 'Мелкая', 700: 'Средняя', 1000: 'Крупная' }[v]}</button>`).join('')}</div></details>
      <details class="panel fold-panel" data-sec="Индекс среды"${calcOpen.has('Индекс среды') ? ' open' : ''}><summary><h3>Индекс среды</h3><i class="chev fa-solid fa-chevron-down"></i></summary><p class="hint">Вес каждой группы мест в индексе среды.</p>
        <div class="form"><label class="fld"><span class="fl">Расстояния до мест</span><select class="field" data-k="walkRoute"><option value="1"${A.walkRoute ? ' selected' : ''}>Пешком по улицам</option><option value="0"${A.walkRoute ? '' : ' selected'}>По прямой</option></select><small>${walkStatus()}</small></label>${grp}</div></details>
    </div>
    <details class="panel fold-panel" data-sec="Какие места учитывать"${calcOpen.has('Какие места учитывать') ? ' open' : ''}><summary><h3>Какие места учитывать</h3><i class="chev fa-solid fa-chevron-down"></i></summary><h4>Плюсы</h4><div class="checks">${cats('pos')}</div><h4>Минусы</h4><div class="checks">${cats('neg')}</div></details>
    <div class="btns row"><button class="btn" id="resetA"><i class="fa-solid fa-rotate-left"></i>Сбросить допущения</button></div>
    <details class="panel fold-panel" data-sec="Как мы выбираем выгодную квартиру"${calcOpen.has('Как мы выбираем выгодную квартиру') ? ' open' : ''}><summary><h3>Как мы выбираем выгодную квартиру</h3><i class="chev fa-solid fa-chevron-down"></i></summary><ol class="steps">
      <li><div><b>Аренда.</b> Типичная аренда по комнатности (20–35 тыс. ₽) × размер, цены соседних квартир и поправки: среда, населённый пункт, рынок, крайний этаж. Своя аренда в карточке заменяет оценку.</div></li>
      <li><div><b>Чистый доход.</b> Аренда за (12 − простой) месяцев минус управляющий, ремонт и расходы, налог на доход и налог на имущество.</div></li>
      <li><div><b>Вложения.</b> Цена + подготовка к сдаче + расходы на сделку. Чистая доходность = чистый доход за год ÷ вложения, окупаемость — их отношение в годах.</div></li>
      <li><div><b>Оценка 0–100.</b> Доходность, среда и цена против соседей в радиусе 1,5 км с весами выше. В карточке квартиры видно, сколько баллов дала каждая часть и что тянет оценку вниз.</div></li></ol>
      <p class="note">Индекс среды — эвристическая модель, а не научный показатель. Модель не гарантирует прибыль; перед покупкой проверьте аренду по реальным объявлениям и документы на квартиру.</p></details></div>`;
  $$('[data-preset]', v).forEach(b => b.onclick = () => applyPreset(b.dataset.preset));
  $$('[data-k]', v).forEach(el => el.onchange = () => {
    const path = el.dataset.k.split('.'), last = path.pop(), o = path.reduce((x, p) => x[p], state.A);
    o[last] = el.tagName === 'SELECT' ? (['mortgageOn', 'wave', 'walkRoute'].includes(last) ? el.value === '1' : el.value) : (+el.value || 0);
    save('A', state.A);
    if (last === 'walkRoute') { state.A.walkRoute ? computeWalk() : (walkOff(), recompute(), updateMarkers()); actions.renderPage('calc'); return; }
    if (last === 'gridSide') { state.A.gridSide = Math.max(300, Math.min(1500, state.A.gridSide)); rebuildGrid(); actions.renderPage('calc'); return; }
    if (last === 'wave' || last === 'waveCells' || last === 'waveLift') { clearWave(); return; }
    recompute(); updateMarkers(); $('#preview').innerHTML = previewHTML(); markPreset(v);
  });
  $$('[data-grid]', v).forEach(b => b.onclick = () => { state.A.gridSide = +b.dataset.grid; save('A', state.A); rebuildGrid(); actions.renderPage('calc'); });
  $$('[data-cat]', v).forEach(el => el.onchange = () => {
    const k = el.dataset.cat, i = state.excluded.indexOf(k);
    el.checked ? (i >= 0 && state.excluded.splice(i, 1)) : (i < 0 && state.excluded.push(k));
    save('excluded', state.excluded); recompute(); updateMarkers(); $('#preview').innerHTML = previewHTML();
  });
  $$('details[data-sec]', v).forEach(d => d.ontoggle = () => d.open ? calcOpen.add(d.dataset.sec) : calcOpen.delete(d.dataset.sec));
  $('#resetA', v).onclick = () => { state.A = mergeA({}); save('A', state.A); refreshAll(); };
}

// данные
function renderData() {
  const v = $('#view-data'), med = a => { const x = [...a].sort((p, q) => p - q), m = x.length >> 1; return x.length ? (x.length % 2 ? x[m] : (x[m - 1] + x[m]) / 2) : null; };
  const group = (key) => {  // квартиры по ключу: число, новостройки/вторичка, медианы цены и ₽/м²; от большего к меньшему
    const g = {}; D.flats.forEach(f => (g[key(f) || '—'] ||= []).push(f));
    return Object.entries(g).sort((a, b) => b[1].length - a[1].length);
  };
  const row = ([k, fl]) => `<tr><td>${esc(k)}</td><td class="r num">${fl.length}</td><td class="r num">${fl.filter(f => f.market === 'new').length}</td><td class="r num">${fl.filter(f => f.market !== 'new').length}</td><td class="r num">${fmtM(med(fl.map(f => f.price)))}</td><td class="r num">${fmt(med(fl.map(f => f.e.pricePerM2)))} ₽</td></tr>`;
  const tbl = (title, rows) => `<div class="tscroll"><table class="data compact"><thead><tr><th>${title}</th><th class="r">Всего</th><th class="r">Новостроек</th><th class="r">Вторичка</th><th class="r">Цена, медиана</th><th class="r">₽/м²</th></tr></thead><tbody>${rows.map(row).join('')}</tbody></table></div>`;
  // места по группам: плюсы по группам индекса среды, минусы отдельно; внутри — по убыванию числа
  const pc = {}; D.points.forEach(p => { pc[p[0]] = (pc[p[0]] || 0) + 1; });
  const byGroup = {}, neg = [];
  for (const [k, n] of Object.entries(pc)) { const c = CATS[k]; if (!c) continue; (c.kind === 'neg' ? neg : (byGroup[c.group] ||= [])).push([k, n]); }
  const cat = ([k, n]) => `<span><i class="fa-solid ${CATS[k].icon}"></i>${esc(CATS[k].label)}<b class="num">${n}</b></span>`;
  const sortG = a => a.sort((x, y) => y[1] - x[1]);
  const total = a => a.reduce((s, [, n]) => s + n, 0);
  const placeBlock = (title, items, cls = '') => `<div class="pgroup ${cls}"><h4>${title}<em>${total(items).toLocaleString('ru-RU')}</em></h4><div class="checks">${sortG(items).map(cat).join('')}</div></div>`;
  const groups = Object.entries(byGroup).sort((a, b) => total(b[1]) - total(a[1]));
  const stat = (n, t, i) => `<div><i class="fa-solid ${i}"></i><b>${n}</b><span>${t}</span></div>`;
  const d10 = x => esc(x ? String(x).slice(0, 10) : '—');
  v.innerHTML = `<div class="wrap"><h1>Данные</h1><p class="lead">Откуда берутся объявления и места на карте, сколько их и как обновлять.</p>
    <section class="panel"><h3>Состояние базы</h3><div class="stat tiles">
      ${stat(D.flats.length, 'объявлений', 'fa-house')}${stat(D.flats.filter(f => f.market === 'new').length, 'новостроек', 'fa-city')}${stat(D.flats.filter(f => f.market !== 'new').length, 'вторичка', 'fa-building')}${stat(D.flats.filter(f => f.photo).length, 'с фото', 'fa-image')}
      ${stat(D.points.length.toLocaleString('ru-RU'), 'мест и факторов', 'fa-location-dot')}${stat(walk.status === 'ready' && walk.nodes ? walk.nodes.toLocaleString('ru-RU') : '—', 'узлов графа улиц', 'fa-route')}</div>
      <p class="note gap">Объявления обновлены ${d10(D.meta.listingsAt)} · места обновлены ${esc(D.meta.poiAt || '—')}</p></section>
    <section class="panel"><h3>Объявления</h3>${tbl('Населённый пункт', group(f => f.locality))}<div class="gap"></div>${tbl('Источник', group(f => f.source))}</section>
    <section class="panel"><h3>Места на карте <em class="cnt">${D.points.length.toLocaleString('ru-RU')}</em></h3>
      <div class="pgrid">${groups.map(([g, items]) => placeBlock(GROUPS[g]?.label || g, items, 'pos')).join('')}${neg.length ? placeBlock('Негативные факторы', neg, 'neg') : ''}</div>
      <p class="note gap">Данные и карта © участники OpenStreetMap, спутниковые снимки © Esri, карта — Leaflet. Полнота зависит от разметки OSM; линейные объекты (магистрали, железная дорога, ЛЭП) представлены вершинами через ~250 м.</p></section>
    <details class="panel fold-panel"><summary><h3>Как обновить данные</h3><i class="chev fa-solid fa-chevron-down"></i></summary><ol class="steps">
      <li><div>Откройте выдачу Авито, Этажей или другого сайта в обычном браузере и сохраните страницу целиком (<code>Ctrl+S</code>, «Веб-страница полностью»). Так сохранятся и фото.</div></li>
      <li><div>Положите <code>.html</code> и папку <code>…_files</code> в <code>data/inbox/</code>. Можно также класть CSV/JSON по шаблону <code>data/inbox-template.csv</code>. Веб-архивы Safari сначала прогоните через <code>scripts/import_webarchive.py</code>.</div></li>
      <li><div>Запустите <code>python scripts/sync_listings.py</code>, затем <code>python scripts/build_buildings.py</code> (контуры домов). Ежедневная задача делает синхронизацию в 07:00.</div></li>
      <li><div>Места берутся из выгрузки OpenStreetMap: <code>data/osm/mari_el.pbf</code> → <code>python scripts/build_poi_from_pbf.py</code>.</div></li></ol></details></div>`;
}

// профиль и вход
const COLOR_HEX = { teal: '#1f9e86', violet: '#7b6cf0', amber: '#e0a43a', rose: '#e0627a', sky: '#4a9fd6', lime: '#7fb347', slate: '#7a8696' };
export const avatar = (u, cls = '') => `<span class="avatar ${cls}" style="background:${COLOR_HEX[u?.color] || COLOR_HEX.teal}"><i class="fa-solid fa-user"></i></span>`;
let authTab = 'login';
const msg = (el, text, ok = false) => { el.textContent = text; el.className = 'form-msg ' + (text ? (ok ? 'ok' : 'err') : ''); };

function authPage() {
  return `<div class="wrap narrow"><div class="auth-grid">
    <div class="auth-intro"><h1>Профиль</h1><p class="lead">Войдите, чтобы сохранять избранные квартиры, допущения расчёта и сравнение — они будут на любом устройстве.</p>
      <ul class="ticks"><li><i class="fa-solid fa-heart"></i>Избранное и сравнение квартир</li><li><i class="fa-solid fa-sliders"></i>Свои ставки аренды, налоги и веса оценки</li><li><i class="fa-solid fa-pen"></i>Своя аренда по каждой квартире</li></ul></div>
    <div class="panel auth-card"><div class="seg wide"><button data-at="login" class="${authTab === 'login' ? 'on' : ''}">Вход</button><button data-at="register" class="${authTab === 'register' ? 'on' : ''}">Регистрация</button></div>
      <form id="authForm" novalidate>
        ${authTab === 'register' ? '<label class="fld"><span class="fl">Имя</span><input class="field" name="name" autocomplete="name" maxlength="60" placeholder="Как к вам обращаться"></label>' : ''}
        <label class="fld"><span class="fl">Почта</span><input class="field" name="email" type="email" autocomplete="email" required placeholder="name@example.com"></label>
        <label class="fld"><span class="fl">Пароль</span><input class="field" name="password" type="password" autocomplete="${authTab === 'login' ? 'current-password' : 'new-password'}" required minlength="8" placeholder="${authTab === 'register' ? 'Не короче 8 символов' : 'Ваш пароль'}"></label>
        <div class="form-msg" id="authMsg" role="alert"></div>
        <button class="btn primary wide" type="submit">${authTab === 'login' ? 'Войти' : 'Создать аккаунт'}</button>
      </form></div></div></div>`;
}

// настройки интерфейса и свои данные — работают и без входа (хранятся в браузере)
const PREF_SORTS = [['score', 'Выгодные'], ['yield', 'Доходность аренды'], ['growth', 'Рост цены'], ['total', 'Общая доходность'], ['price', 'Дешёвые'], ['ppm', 'Дешевле за м²'], ['env', 'Лучшая среда']];
const PREF_VIEWS = [['map', 'Карта'], ['rank', 'Рейтинг'], ['compare', 'Сравнение'], ['calc', 'Модель']];
const sw = (id, label, hint, on) => `<label class="pref-sw"><span><b>${label}</b><small>${hint}</small></span><input type="checkbox" id="${id}"${on ? ' checked' : ''}><i></i></label>`;
const pseg = (id, items, cur) => `<div class="seg pref-seg" id="${id}">${items.map(([k, t]) => `<button type="button" data-v="${k}" class="${k === cur ? 'on' : ''}">${t}</button>`).join('')}</div>`;
const prow = (label, ctl) => `<div class="pref-row"><span>${label}</span>${ctl}</div>`;
function prefsPanel() {
  const dark = document.documentElement.dataset.theme !== 'light';
  return `<section class="panel"><h3>Интерфейс</h3><div class="pref-list">
    ${prow('Тема', pseg('prTheme', [['light', 'Светлая'], ['dark', 'Тёмная']], dark ? 'dark' : 'light'))}
    ${prow('Подложка карты', pseg('prBase', [['map', 'Карта'], ['sat', 'Спутник']], state.base))}
    ${prow('Что открывать при запуске', pseg('prView', PREF_VIEWS, LS.get('startView', 'map')))}
    ${prow('Сортировка списка', `<select class="field" id="prSort" aria-label="Сортировка по умолчанию">${PREF_SORTS.map(([k, t]) => `<option value="${k}"${state.f.sort === k ? ' selected' : ''}>${t}</option>`).join('')}</select>`)}
    ${sw('prAll', 'Показывать пустые ячейки', 'Сетка на всю карту, а не только там, где есть объявления', state.show.grid)}
    ${sw('prPhoto', 'Только объявления с фото', 'Скрывать карточки без собственного снимка', state.f.photoOnly)}
    ${sw('prAnim', 'Анимации', 'Выключите, если интерфейс тормозит', !LS.get('noAnim', false))}
  </div></section>
  <section class="panel"><h3>Мои данные</h3><p class="note">Избранное, сравнение, свои квартиры и контуры, ставки аренды и допущения расчёта: ${state.fav.length} · ${state.compare.length} · ${state.userFlats.length} · ${Object.keys(state.rentOv).length}. Файл можно перенести на другое устройство.</p>
    <div class="pref-btns"><button class="btn" id="prExport" type="button"><i class="fa-solid fa-download"></i>Скачать</button>
      <label class="btn" for="prImport"><i class="fa-solid fa-upload"></i>Загрузить</label><input type="file" id="prImport" accept="application/json,.json" hidden>
      <button class="btn danger" id="prReset" type="button"><i class="fa-solid fa-rotate-left"></i>Сбросить</button></div>
    <div class="form-msg" id="prMsg" role="status"></div></section>`;
}
const DATA_KEYS = ['A', 'rentOv', 'excluded', 'fav', 'compare', 'userFlats', 'userPolys'];
const PREF_KEYS = ['theme', 'base', 'startView', 'sort', 'gridAll', 'photoOnly', 'noAnim'];
function bindPrefs(v) {
  const on = (id, fn) => { const el = $('#' + id, v); if (el) el.onchange = fn; };
  const seg = (id, fn) => { const el = $('#' + id, v); if (el) el.onclick = e => { const b = e.target.closest('[data-v]'); if (!b) return; $$('button', el).forEach(x => x.classList.toggle('on', x === b)); fn(b.dataset.v); }; };
  seg('prTheme', t => { document.documentElement.dataset.theme = t; LS.set('theme', t); applyBase(); });
  seg('prBase', b => { state.base = b; LS.set('base', b); $$('#baseSeg button').forEach(x => x.classList.toggle('on', (x.dataset.base === 'sat') === (b === 'sat'))); applyBase(); });
  seg('prView', k => LS.set('startView', k));
  on('prSort', e => { state.f.sort = e.target.value; LS.set('sort', state.f.sort); });
  on('prAll', e => { state.show.grid = e.target.checked; LS.set('gridAll', e.target.checked); $$('#showSeg [data-show=grid]').forEach(x => x.classList.toggle('on', e.target.checked)); updateMarkers(); });
  on('prPhoto', e => { state.f.photoOnly = e.target.checked; LS.set('photoOnly', e.target.checked); });
  on('prAnim', e => { LS.set('noAnim', !e.target.checked); document.documentElement.classList.toggle('noanim', !e.target.checked); });
  const m = $('#prMsg', v); if (!m) return;
  $('#prExport', v).onclick = () => {
    const out = { app: 'gorodskoy-kompas', v: 1, data: snapshot(), prefs: Object.fromEntries(PREF_KEYS.map(k => [k, LS.get(k, null)])) };
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], { type: 'application/json' }));
    a.download = 'gorodskoy-kompas-' + new Date().toISOString().slice(0, 10) + '.json'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    msg(m, 'Файл сохранён', true);
  };
  $('#prImport', v).onchange = async e => {
    try {
      const j = JSON.parse(await e.target.files[0].text());
      if (j.app !== 'gorodskoy-kompas' || !j.data) throw 0;
      for (const k of DATA_KEYS) if (j.data[k] != null) { LS.set(k, j.data[k]); }
      for (const k of PREF_KEYS) if (j.prefs?.[k] != null) LS.set(k, j.prefs[k]);
      actions.sync?.(); msg(m, 'Загружено, перезапускаю…', true); setTimeout(() => location.reload(), 500);
    } catch { msg(m, 'Это не файл «Городского компаса»'); }
  };
  $('#prReset', v).onclick = () => {
    if (!confirm('Стереть избранное, сравнение, свои квартиры и все настройки на этом устройстве?')) return;
    for (const k of [...DATA_KEYS, ...PREF_KEYS]) { try { localStorage.removeItem(k); } catch { /* */ } }
    state.A = mergeA({}); for (const k of DATA_KEYS.slice(1)) state[k] = Array.isArray(snapshot()[k]) ? [] : {}; actions.sync?.(); location.reload();
  };
}
function offlinePage() {
  return `<div class="wrap"><h1>Профиль</h1><p class="lead">Входа нет — приложение открыто как статический сайт. Всё хранится в этом браузере.</p>
    <div class="pf-cols"><div class="pf-col">${prefsPanel()}</div><div class="pf-col">${favPanel()}
    <section class="panel"><h3>Синхронизация</h3><p class="note">Чтобы войти и переносить данные между устройствами автоматически, запустите сервер: <code>python server/app.py</code>. Пока можно перенести файлом — «Мои данные».</p></section></div></div></div>`;
}
function favPanel() {
  const favs = state.fav.map(id => D.byId.get(id)).filter(Boolean);
  return `<section class="panel"><h3>Избранное <em class="cnt">${favs.length}</em></h3>${favs.length ? `<div class="favgrid">${favs.map(flatCard).join('')}</div>` : '<p class="note">Пока пусто. Отмечайте квартиры сердечком в списке и в карточке.</p>'}</section>`;
}
function profilePage() {
  const u = auth.user;
  return `<div class="wrap"><div class="prof-head">${avatar(u, 'xl')}<div><h1>${esc(u.name)}</h1><p class="lead">${esc(u.email)}</p></div><button class="btn logout" id="logoutBtn" title="Выйти" aria-label="Выйти"><i class="fa-solid fa-arrow-right-from-bracket"></i></button></div>
    <div class="pf-cols"><div class="pf-col">
      <section class="panel"><h3>Аккаунт</h3><form id="profForm">
        <label class="fld"><span class="fl">Имя</span><input class="field" name="name" maxlength="60" value="${esc(u.name)}"></label>
        <div class="fld"><span class="fl">Цвет аватара</span><div class="swatches">${Object.entries(COLOR_HEX).map(([k, c]) => `<label class="sw"><input type="radio" name="color" value="${k}"${u.color === k ? ' checked' : ''}><span style="background:${c}"></span></label>`).join('')}</div></div>
        <div class="form-msg" id="profMsg" role="status"></div><button class="btn primary" type="submit">Сохранить</button></form></section>
      ${prefsPanel()}
    </div><div class="pf-col">
      ${favPanel()}
      <section class="panel"><h3>Безопасность</h3><form id="pwForm"><div class="form">
        <label class="fld"><span class="fl">Текущий пароль</span><input class="field" type="password" name="old" autocomplete="current-password"></label>
        <label class="fld"><span class="fl">Новый пароль</span><input class="field" type="password" name="new" autocomplete="new-password" minlength="8" placeholder="Не короче 8 символов"></label></div>
        <div class="form-msg" id="pwMsg" role="status"></div><button class="btn" type="submit">Сменить пароль</button><p class="note gap">После смены пароля остальные устройства будут разлогинены.</p></form></section>
      <section class="panel danger"><h3>Удаление аккаунта</h3><p class="note">Аккаунт и сохранённые настройки будут удалены без возможности восстановления.</p>
        <form id="delForm" class="inline"><input class="field" type="password" name="password" placeholder="Пароль для подтверждения" autocomplete="current-password"><button class="btn danger" type="submit">Удалить</button></form><div class="form-msg" id="delMsg" role="alert"></div></section>
    </div></div></div>`;
}
function renderProfile() {
  const v = $('#view-profile');
  if (auth.available === false) { v.innerHTML = offlinePage(); bindFav(v); bindPrefs(v); return; }
  v.innerHTML = auth.user ? profilePage() : authPage();
  bindFav(v); bindPrefs(v);
  if (!auth.user) {
    $$('[data-at]', v).forEach(b => b.onclick = () => { authTab = b.dataset.at; actions.renderPage('profile'); });
    $('#authForm', v).onsubmit = async e => {
      e.preventDefault();
      const fd = new FormData(e.target), m = $('#authMsg', v), btn = $('button[type=submit]', e.target);
      btn.disabled = true; msg(m, '');
      const r = authTab === 'login' ? await login(fd.get('email'), fd.get('password')) : await register(fd.get('email'), fd.get('password'), fd.get('name'));
      btn.disabled = false;
      if (!r.ok) return msg(m, r.message);
      actions.onAuth(r.data.settings || {}, authTab === 'register');
    };
    return;
  }
  $('#logoutBtn', v).onclick = async () => { await logout(); actions.onLogout(); };
  $('#profForm', v).onsubmit = async e => {
    e.preventDefault(); const fd = new FormData(e.target), m = $('#profMsg', v);
    const r = await updateProfile(fd.get('name'), fd.get('color') || auth.user.color);
    r.ok ? (msg(m, 'Сохранено', true), actions.headerAuth()) : msg(m, r.message);
    if (r.ok) setTimeout(() => actions.renderPage('profile'), 600);
  };
  $('#pwForm', v).onsubmit = async e => {
    e.preventDefault(); const fd = new FormData(e.target), m = $('#pwMsg', v);
    const r = await changePassword(fd.get('old'), fd.get('new'));
    msg(m, r.ok ? 'Пароль изменён' : r.message, r.ok); if (r.ok) e.target.reset();
  };
  $('#delForm', v).onsubmit = async e => {
    e.preventDefault(); const m = $('#delMsg', v);
    const r = await deleteAccount(new FormData(e.target).get('password'));
    r.ok ? actions.onLogout() : msg(m, r.message);
  };
}
function bindFav(v) {
  $$('.card', v).forEach(c => c.onclick = e => {
    const h = e.target.closest('[data-act=fav]');
    if (h) { toggleFav(h.dataset.id); return; }
    goMap(c.dataset.id);
  });
}

actions.renderPage = name => ({ rank: renderRank, compare: renderCompare, calc: renderCalc, data: renderData, profile: renderProfile })[name]?.();
