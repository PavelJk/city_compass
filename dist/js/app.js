// старт приложения: данные, шапка, вкладки, вход
import { load, recompute, rebuild } from './model.js';
import { map, applyBase, buildHex, updateMarkers, syncPoi, fitAll } from './map.js';
import { auth, initAuth, flushSync } from './api.js';
import { state, D, $, $$, LS, mergeA, actions } from './state.js';
import { renderDock, syncBadges, refreshAll } from './flat.js';
import { avatar } from './pages.js';
import { computeWalk, walk } from './walk.js';
import { initDropdowns } from './dropdown.js';
import './own.js';
import './mapmenu.js';

// вкладки
const PAGES = new Set(['rank', 'compare', 'calc', 'data', 'profile']);
let closing = 0;
function setView(name) {
  const prev = state.view;
  // окно закрывается с небольшой анимацией, повторные клики в это время игнорируем
  if (name === 'map' && prev !== 'map' && !closing) {
    const p = $('#view-' + prev);
    if (p && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      closing = setTimeout(() => { closing = 0; p.classList.remove('leaving'); finishView('map'); }, 170);
      p.classList.add('leaving'); state.view = 'map'; $$('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.view === 'map'));
      $$('.top-end [data-view]').forEach(b => b.classList.remove('on'));
      return;
    }
  }
  if (closing) { clearTimeout(closing); closing = 0; $$('.page.leaving').forEach(p => p.classList.remove('leaving')); }
  finishView(name);
}
function finishView(name) {
  state.view = name;
  $$('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.view === name));
  $$('#showSeg [data-show=grid]').forEach(b => b.classList.toggle('on', state.show.grid));
  $$('.top-end [data-view]').forEach(b => b.classList.toggle('on', b.dataset.view === name));
  // карта остаётся внизу, остальные разделы — окна поверх неё
  $$('.view').forEach(s => s.classList.toggle('on', s.id === 'view-map' || s.id === 'view-' + name));
  document.body.classList.toggle('modal-open', name !== 'map');
  if (name === 'map') { map.invalidateSize(); renderDock(); }
  else if (PAGES.has(name)) {
    actions.renderPage(name); const p = $('#view-' + name); p.querySelector('.wrap')?.scrollTo(0, 0);
    p.classList.add('enter'); setTimeout(() => p.classList.remove('enter'), 260);
  }
}

// закрыть окно можно крестиком, Esc или кликом по затемнению
const renderPageRaw = actions.renderPage;
actions.renderPage = name => {
  renderPageRaw(name);
  const w = $('#view-' + name + ' .wrap');
  if (w && !w.querySelector('.modal-x')) w.insertAdjacentHTML('afterbegin', '<button class="modal-x" data-close aria-label="Закрыть" title="Закрыть"><i class="fa-solid fa-xmark"></i></button>');
};
document.addEventListener('click', e => {
  if (e.target.closest('[data-close]')) return setView('map');
  if (e.target.classList?.contains('page') && state.view !== 'map') setView('map');
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && state.view !== 'map') setView('map'); });
actions.setView = setView;
// пришла очередная порция маршрутов — пересчитываем среду
actions.walkUpdated = done => {
  D.walkVer = (D.walkVer || 0) + 1;
  recompute(); updateMarkers();
  if (state.view === 'map') { const dk = $('#dock'), top = dk.scrollTop; renderDock(); dk.scrollTop = top; }
  else if (done) actions.renderPage(state.view);
};
actions.computeWalk = computeWalk;
document.addEventListener('click', e => { const b = e.target.closest('[data-view]'); if (b) setView(b.dataset.view); });

// шапка
function headerAuth() {
  const b = $('#profileBtn');
  if (auth.user) b.innerHTML = avatar(auth.user, 'sm') + '<span class="pname">' + (auth.user.name || '').split(' ')[0].replace(/[<>&"']/g, '') + '</span>';
  else b.innerHTML = auth.available === false ? '<i class="fa-regular fa-user"></i>' : '<i class="fa-regular fa-user"></i><span class="pname">Войти</span>';
  b.setAttribute('aria-label', auth.user ? 'Профиль' : 'Войти');
}
actions.headerAuth = headerAuth;

// настройки с сервера важнее локальных
function applySettings(s) {
  if (!s || !Object.keys(s).length) return false;
  if (s.A) state.A = mergeA(s.A);
  if (s.rentOv) state.rentOv = s.rentOv;
  if (Array.isArray(s.excluded)) state.excluded = s.excluded;
  if (Array.isArray(s.fav)) state.fav = s.fav;
  if (Array.isArray(s.compare)) state.compare = s.compare;
  if (Array.isArray(s.userFlats)) state.userFlats = s.userFlats;
  if (s.userPolys && typeof s.userPolys === 'object') state.userPolys = s.userPolys;
  for (const k of ['A', 'rentOv', 'excluded', 'fav', 'compare', 'userFlats', 'userPolys']) LS.set(k, state[k]);
  return true;
}
actions.onAuth = async (settings, fresh) => {
  if (!applySettings(settings)) await flushSync(); // новый аккаунт: отправляем то, что накопилось локально
  headerAuth(); syncBadges(); actions.reloadData(); setView('map');
};
actions.onLogout = () => { headerAuth(); setView('map'); };

// панель карты
$('#modeSeg').addEventListener('click', e => {
  const b = e.target.closest('[data-mode]'); if (!b) return;
  state.mode = b.dataset.mode; $$('#modeSeg button').forEach(x => x.classList.toggle('on', x === b)); updateMarkers();
});
$('#showSeg').addEventListener('click', e => {
  const b = e.target.closest('[data-show]'); if (!b) return;
  const k = b.dataset.show; state.show[k] = !state.show[k]; b.classList.toggle('on', state.show[k]);
  if (k === 'grid') LS.set('gridAll', state.show.grid);
  k === 'poi' ? syncPoi() : updateMarkers();
});
$('#baseSeg').addEventListener('click', e => {
  const b = e.target.closest('[data-base]'); if (!b) return;
  state.base = b.dataset.base === 'sat' ? 'sat' : 'map'; LS.set('base', state.base); $$('#baseSeg button').forEach(x => x.classList.toggle('on', x === b)); applyBase();
});

// запуск
initDropdowns();
(async () => {
  $('#dock').innerHTML = '<div class="empty"><i class="fa-solid fa-spinner fa-spin"></i>Загружаю данные…</div>';
  applyBase();
  const [settings] = await Promise.all([initAuth(), load()]);
  if (applySettings(settings)) rebuild();  // свои квартиры из аккаунта
  headerAuth(); recompute(); syncBadges();
  buildHex(); updateMarkers(); syncPoi(); renderDock(); fitAll();
  setTimeout(() => map.invalidateSize(), 100);
  $$('#baseSeg button').forEach(x => x.classList.toggle('on', (x.dataset.base === 'sat') === (state.base === 'sat')));
  const sv = LS.get('startView', 'map'); if (sv !== 'map' && $('#view-' + sv)) setView(sv);
  computeWalk();  // маршруты считаются в фоне, пока их нет — расстояния по прямой
})();
