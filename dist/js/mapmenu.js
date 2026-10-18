// меню карты: что показывать, слои и параметры сетки; по умолчанию скрыто, открывается кнопкой
import { state, save, $, $$, LS } from './state.js';
import { clearWave, applyBase, map } from './map.js';
import { rebuildGrid } from './pages.js';

const PRESETS = [['Мелкая', 450], ['Средняя', 700], ['Крупная', 1000]];
const km = side => '≈ ' + (Math.sqrt(3) * side * 0.55 / 1000).toFixed(2).replace('.', ',') + ' км';
const menu = $('#mapMenu'), btn = $('#mapMenuBtn'), grid = $('.mm-grid', menu);

const range = (label, id, min, max, step, val, out) => `<label class="gp-range"><span>${label}</span><input type="range" id="${id}" min="${min}" max="${max}" step="${step}" value="${val}"><em id="${id}Out">${out}</em></label>`;

function gridHTML() {
  const A = state.A;
  return `<div class="mm-title">Сетка</div>
    <div class="gp-chips">${PRESETS.map(([t, v]) => `<button type="button" class="chip${+A.gridSide === v ? ' on' : ''}" data-side="${v}">${t}</button>`).join('')}</div>
    ${range('Размер ячейки', 'gpSide', 300, 1500, 50, A.gridSide, km(A.gridSide))}
    <label class="gp-sw"><span>Волна при наведении</span><input type="checkbox" id="gpWave"${A.wave ? ' checked' : ''}><i></i></label>
    <div class="gp-wave"${A.wave ? '' : ' hidden'}>${range('Радиус волны', 'gpCells', 1, 6, 0.5, A.waveCells, A.waveCells + ' яч.')}${range('Высота подъёма', 'gpLift', 0, 24, 1, A.waveLift, A.waveLift + ' px')}</div>`;
}

function setSide(v) {
  state.A.gridSide = Math.max(300, Math.min(1500, +v)); save('A', state.A);
  $$('[data-side]', grid).forEach(b => b.classList.toggle('on', +b.dataset.side === state.A.gridSide));
  $('#gpSide', grid).value = state.A.gridSide; $('#gpSideOut', grid).textContent = km(state.A.gridSide);
  rebuildGrid();
}

function fillGrid() {
  grid.innerHTML = gridHTML();
  grid.addEventListener('click', e => { const b = e.target.closest('[data-side]'); if (b) setSide(b.dataset.side); });
  const side = $('#gpSide', grid);
  side.oninput = () => { $('#gpSideOut', grid).textContent = km(+side.value); };
  side.onchange = () => setSide(side.value);
  $('#gpWave', grid).onchange = e => { state.A.wave = e.target.checked; save('A', state.A); clearWave(); $('.gp-wave', grid).hidden = !state.A.wave; };
  const bind = (id, key, unit) => { const el = $('#' + id, grid); el.oninput = () => { state.A[key] = +el.value; save('A', state.A); clearWave(); $('#' + id + 'Out', grid).textContent = el.value + unit; }; };
  bind('gpCells', 'waveCells', ' яч.'); bind('gpLift', 'waveLift', ' px');
}
fillGrid();

const isOpen = () => !menu.hidden;
function toggle(open) {
  menu.hidden = !open; btn.classList.toggle('open', open); btn.setAttribute('aria-expanded', open);
}
btn.addEventListener('click', e => { e.stopPropagation(); toggle(!isOpen()); });
document.addEventListener('click', e => { if (isOpen() && !menu.contains(e.target) && !btn.contains(e.target)) toggle(false); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && isOpen()) toggle(false); });
// подпись на кнопке — выбранный режим
$('#modeSeg').addEventListener('click', e => { const b = e.target.closest('[data-mode]'); if (b) $('#mapMode').textContent = b.textContent; });

// тема из меню карты
const markTheme = () => $$('#themeSeg button').forEach(b => b.classList.toggle('on', b.dataset.theme === (document.documentElement.dataset.theme === 'light' ? 'light' : 'dark')));
markTheme();
$('#themeSeg').addEventListener('click', e => {
  const b = e.target.closest('[data-theme]'); if (!b) return;
  document.documentElement.dataset.theme = b.dataset.theme; LS.set('theme', b.dataset.theme); applyBase(); markTheme();
});
menu.addEventListener('click', e => { if (e.target.closest('[data-view]')) toggle(false); });
// скрыть/показать боковую панель с квартирами — остаётся чистая карта
export function setDock(show) {
  document.body.classList.toggle('dock-off', !show);
  setTimeout(() => map.invalidateSize(), 60);
}
document.addEventListener('click', e => {
  if (e.target.closest('[data-act=dockhide]')) setDock(false);
  else if (e.target.closest('#dockShow')) setDock(true);
});
document.addEventListener('ri5:select', () => setDock(true));

// полоса прокрутки панели квартир начинается под шапкой: высота шапки → --dh
const dockEl = $('#dock');
const ro = new ResizeObserver(() => { const h = dockEl.querySelector('.dock-head'); dockEl.style.setProperty('--dh', (h && getComputedStyle(dockEl).position === 'absolute' ? h.offsetHeight : 0) + 'px'); });
new MutationObserver(() => { ro.disconnect(); const h = dockEl.querySelector('.dock-head'); if (h) ro.observe(h); }).observe(dockEl, { childList: true });
