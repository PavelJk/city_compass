// свои квартиры и участки: форма добавления, выбор места и контура на карте
import { LOCALITIES } from './config.js';
import { map, buildHex, updateMarkers } from './map.js';
import { rebuild, recompute } from './model.js';
import { computeWalk } from './walk.js';
import { renderDock, select, syncBadges } from './flat.js';
import { state, D, $, $$, esc, save, actions } from './state.js';

const ORANGE = '#f59a45';
const ROOMS = ['Студия', '1-комн.', '2-комн.', '3-комн.'];
const key = a => String(a || '').trim();

// ---------- пересчёт после любых изменений ----------
function reload(selectId) {
  if (state.sel?.type === 'bld') state.sel = null;
  rebuild(); recompute(); buildHex(); updateMarkers(); syncBadges();
  if (selectId && D.byId.has(selectId)) select({ type: 'flat', id: selectId });
  else { if (state.sel?.type === 'flat' && !D.byId.has(state.sel.id)) state.sel = null; renderDock(); }
  computeWalk();
}
actions.reloadData = reload;

// ---------- рисование на карте ----------
let draw = null, bar = null;

function stopDraw() {
  if (!draw) return;
  map.off('click', onClick); map.doubleClickZoom.enable(); map.removeLayer(draw.group);
  map.getContainer().style.cursor = ''; document.body.classList.remove('drawing');
  bar?.remove(); bar = null; document.removeEventListener('keydown', onKey, true);
  draw = null;
}
function onKey(e) { if (e.key === 'Escape') { e.stopPropagation(); cancelDraw(); } else if (e.key === 'Enter' && draw?.mode === 'poly') finishDraw(); }
function cancelDraw() { const d = draw; stopDraw(); d?.cancel?.(); }
function finishDraw() {
  if (!draw || (draw.mode === 'poly' && draw.pts.length < 3)) return;
  const d = draw, pts = d.pts.slice(); stopDraw(); d.done(pts);
}
function onClick(e) {
  if (draw.mode === 'edit') return;
  draw.pts.push([e.latlng.lat, e.latlng.lng]);
  if (draw.mode === 'point') return finishDraw();
  paint();
}
function paint() {
  draw.group.clearLayers();
  draw.pts.forEach(p => L.circleMarker(p, { radius: 5, color: '#fff', weight: 2, fillColor: ORANGE, fillOpacity: 1, interactive: false }).addTo(draw.group));
  if (draw.pts.length >= 2) L.polygon(draw.pts, { color: ORANGE, weight: 2, dashArray: '5 4', fillColor: ORANGE, fillOpacity: .2, interactive: false }).addTo(draw.group);
  const ok = draw.pts.length >= 3;
  bar.querySelector('[data-b=ok]').disabled = !ok;
  bar.querySelector('[data-b=undo]').disabled = !draw.pts.length;
  bar.querySelector('.n').textContent = draw.pts.length ? `Точек: ${draw.pts.length}` : '';
}
function startDraw(mode, text, done, cancel, initial) {
  stopDraw();
  draw = { mode, pts: initial ? initial.map(p => p.slice()) : [], group: L.layerGroup().addTo(map), done, cancel };
  document.body.classList.add('drawing'); map.getContainer().style.cursor = 'crosshair';
  map.on('click', onClick);
  if (mode !== 'point') map.doubleClickZoom.disable();
  bar = document.createElement('div'); bar.className = 'drawbar';
  bar.innerHTML = `<span class="t">${text}</span><span class="n"></span>${mode === 'poly'
    ? '<button class="btn" data-b="undo" disabled>Назад</button><button class="btn primary" data-b="ok" disabled>Готово</button>'
    : mode === 'edit' ? '<button class="btn primary" data-b="ok">Готово</button>' : ''}<button class="btn" data-b="cancel">Отмена</button>`;
  bar.onclick = e => { const b = e.target.closest('[data-b]')?.dataset.b; if (b === 'cancel') cancelDraw(); else if (b === 'ok') finishDraw(); else if (b === 'undo') { draw.pts.pop(); paint(); } };
  document.body.appendChild(bar); document.addEventListener('keydown', onKey, true);
  if (mode === 'edit') paintEdit();
}

// правка контура: точки двигаются мышью, кружок между точками добавляет новую, двойной клик по точке убирает её
const vtx = cls => L.divIcon({ className: 'vtx ' + cls, iconSize: [cls === 'mid' ? 12 : 18, cls === 'mid' ? 12 : 18] });
function paintEdit() {
  const g = draw.group, pts = draw.pts; g.clearLayers();
  const poly = L.polygon(pts, { color: ORANGE, weight: 2, dashArray: '5 4', fillColor: ORANGE, fillOpacity: .2, interactive: false }).addTo(g);
  pts.forEach((p, i) => {
    const q = pts[(i + 1) % pts.length];
    L.marker([(p[0] + q[0]) / 2, (p[1] + q[1]) / 2], { icon: vtx('mid'), keyboard: false }).on('click', () => { pts.splice(i + 1, 0, [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2]); paintEdit(); }).addTo(g);
  });
  pts.forEach((p, i) => {
    L.marker(p, { icon: vtx('pt'), draggable: true, keyboard: false })
      .on('drag', e => { pts[i] = [e.latlng.lat, e.latlng.lng]; poly.setLatLngs(pts); })
      .on('dragend', paintEdit)
      .on('dblclick contextmenu', () => { if (pts.length > 3) { pts.splice(i, 1); paintEdit(); } }).addTo(g);
  });
  bar.querySelector('.n').textContent = `Точек: ${pts.length}`;
}

// ---------- форма ----------
let sheet = null, draft = null;

const blank = () => ({ address: '', locality: 'Йошкар-Ола', market: 'new', rooms: '1-комн.', area: '', price: '', floor: '', floors: '', rent: '', complex: '', url: '', point: null, poly: null });

function fromFlat(f) {
  return { id: f.id, address: f.address, locality: f.locality, market: f.market, rooms: f.rooms, area: f.area, price: f.price, floor: f.floor || '', floors: f.floors || '',
    rent: f.rent || '', complex: f.complex || '', url: f.url || '', point: [f.lat, f.lng], poly: state.userPolys[key(f.address)] || null };
}

function readForm() {
  if (!sheet) return;
  const g = n => sheet.querySelector(`[name=${n}]`)?.value ?? '';
  Object.assign(draft, { address: g('address').trim(), locality: g('locality'), market: g('market'), rooms: g('rooms'), area: g('area'), price: g('price'),
    floor: g('floor'), floors: g('floors'), rent: g('rent'), complex: g('complex').trim(), url: g('url').trim() });
}

function closeSheet() { sheet?.remove(); sheet = null; }

function renderSheet(msg = '') {
  closeSheet();
  const d = draft, sel = (n, opts, v) => `<select class="field" name="${n}">${opts.map(([val, t]) => `<option value="${esc(val)}"${val === v ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
  const inp = (n, label, type = 'text', ph = '', extra = '') => `<label class="fld"><span class="fl">${label}</span><input class="field" name="${n}" type="${type}" value="${esc(d[n] ?? '')}" placeholder="${ph}" ${extra}></label>`;
  const place = d.poly ? `<i class="fa-solid fa-circle-check"></i> Участок нарисован (${d.poly.length} точек)` : d.point ? '<i class="fa-solid fa-circle-check"></i> Точка выбрана' : 'Место на карте не выбрано';
  sheet = document.createElement('div'); sheet.className = 'sheet';
  sheet.innerHTML = `<form class="panel sheet-card" novalidate>
    <h2>${d.id ? 'Изменить квартиру' : 'Добавить квартиру'}</h2>
    <p class="note">Квартира сохранится в вашем браузере (если вы вошли — в аккаунте) и попадёт в карту, рейтинг и расчёты.</p>
    <div class="form">
      ${inp('address', 'Адрес', 'text', 'ул. Пример, 10')}
      <label class="fld"><span class="fl">Населённый пункт</span>${sel('locality', LOCALITIES.map(l => [l, l]), d.locality)}</label>
      <label class="fld"><span class="fl">Рынок</span>${sel('market', [['new', 'Новостройка'], ['secondary', 'Вторичка']], d.market)}</label>
      <label class="fld"><span class="fl">Комнат</span>${sel('rooms', ROOMS.map(r => [r, r]), ROOMS.includes(d.rooms) ? d.rooms : '1-комн.')}</label>
      ${inp('area', 'Площадь, м²', 'number', '45', 'step="0.1" min="1"')}
      ${inp('price', 'Цена, ₽', 'number', '4500000', 'step="10000" min="1"')}
      ${inp('floor', 'Этаж', 'number', '', 'min="1"')}${inp('floors', 'Этажей в доме', 'number', '', 'min="1"')}
      ${inp('rent', 'Аренда, ₽/мес (если знаете)', 'number', 'оценим сами', 'step="500" min="0"')}
      ${inp('complex', 'Название ЖК (по желанию)')}
      ${inp('url', 'Ссылка на объявление (по желанию)', 'url', 'https://')}
    </div>
    <div class="place"><div class="pl">${place}</div>
      <div class="row"><button class="btn" type="button" data-b="point"><i class="fa-solid fa-location-crosshairs"></i>Указать точку</button>
      <button class="btn" type="button" data-b="poly"><i class="fa-solid fa-draw-polygon"></i>Обвести участок или дом</button></div>
      <p class="note">Для новостройки лучше обвести участок, где строится дом. Нужно минимум 3 точки, затем «Готово».</p></div>
    <div class="form-msg err" role="alert">${msg}</div>
    <div class="row end"><button class="btn" type="button" data-b="cancel">Отмена</button><button class="btn primary" type="submit">Сохранить</button></div></form>`;
  document.body.appendChild(sheet);
  const form = sheet.querySelector('form');
  sheet.addEventListener('mousedown', e => { if (e.target === sheet) { readForm(); closeSheet(); } });
  form.addEventListener('click', e => {
    const b = e.target.closest('[data-b]')?.dataset.b; if (!b) return;
    readForm();
    if (b === 'cancel') return closeSheet();
    const back = () => renderSheet();
    if (b === 'point') { closeSheet(); startDraw('point', 'Нажмите на карте место квартиры', p => { draft.point = p[0]; draft.poly = null; renderSheet(); }, back); }
    if (b === 'poly') { closeSheet(); startDraw('poly', 'Ставьте точки по углам участка или дома', p => { draft.poly = p; draft.point = ringCenter(p); renderSheet(); }, back); }
  });
  form.addEventListener('submit', e => { e.preventDefault(); readForm(); save_(); });
  sheet.querySelector('[name=address]').focus();
}
const ringCenter = r => [r.reduce((s, p) => s + p[0], 0) / r.length, r.reduce((s, p) => s + p[1], 0) / r.length];

function save_() {
  const d = draft, area = +d.area, price = +d.price;
  if (!d.address) return renderSheet('Впишите адрес.');
  if (!(area > 0)) return renderSheet('Укажите площадь.');
  if (!(price > 0)) return renderSheet('Укажите цену.');
  if (!d.point) return renderSheet('Выберите место на карте: точку или участок.');
  const f = {
    id: d.id || 'own-' + Date.now().toString(36), address: d.address, locality: d.locality, market: d.market, rooms: d.rooms, area, price,
    floor: +d.floor || 0, floors: +d.floors || 0, rent: +d.rent || 0, complex: d.complex, url: d.url, lat: d.point[0], lng: d.point[1],
    name: `${d.rooms}, ${area} м²`, source: 'Добавлено вручную', photo: '', photos: [],
  };
  const i = state.userFlats.findIndex(x => x.id === f.id);
  i >= 0 ? state.userFlats[i] = f : state.userFlats.push(f);
  if (d.poly) { state.userPolys[key(d.address)] = d.poly; save('userPolys', state.userPolys); }
  // адрес могли поменять: старый участок без квартир убираем
  if (d.id && d.oldAddress && key(d.oldAddress) !== key(d.address)) dropPolyIfUnused(d.oldAddress);
  save('userFlats', state.userFlats);
  closeSheet(); reload(f.id);
}

function dropPolyIfUnused(addr) {
  const k = key(addr);
  if (state.userPolys[k] && !D.flats.some(f => key(f.address) === k && !f.own)) { delete state.userPolys[k]; save('userPolys', state.userPolys); }
}

// ---------- действия из интерфейса ----------
actions.ownAdd = () => { draft = blank(); renderSheet(); };
actions.ownEdit = id => { const f = D.byId.get(id); if (!f?.own) return; draft = fromFlat(f); draft.oldAddress = f.address; renderSheet(); };
actions.ownDelete = id => {
  const f = D.byId.get(id); if (!f?.own || !confirm('Удалить эту квартиру?')) return;
  state.userFlats = state.userFlats.filter(u => u.id !== id); save('userFlats', state.userFlats);
  dropPolyIfUnused(f.address);
  if (state.sel?.id === id) state.sel = null;
  state.fav = state.fav.filter(x => x !== id); state.compare = state.compare.filter(x => x !== id);
  reload();
};
// свой контур дома или участка для любой квартиры (по адресу: он общий для всех квартир этого дома)
actions.ownPoly = id => {
  const f = D.byId.get(id); if (!f) return;
  startDraw('poly', 'Обведите участок или дом по углам', pts => { state.userPolys[key(f.address)] = pts; save('userPolys', state.userPolys); reload(id); }, null);
};
// править контур, который сейчас показан у квартиры (свой или найденный автоматически)
actions.ownEditPoly = id => {
  const f = D.byId.get(id); if (!f) return;
  const own = state.userPolys[key(f.address)], b = D.buildings.find(x => x.f.includes(id));
  let ring = own || b?.r; if (!ring) return actions.ownPoly(id);
  if (!own && ring.length > 3 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]) ring = ring.slice(0, -1);
  startDraw('edit', 'Двигайте точки. Кружок между точками добавляет новую, двойной клик по точке убирает её', pts => { state.userPolys[key(f.address)] = pts; save('userPolys', state.userPolys); reload(id); }, null, ring);
};
actions.ownPolyReset = id => {
  const f = D.byId.get(id); if (!f) return;
  delete state.userPolys[key(f.address)]; save('userPolys', state.userPolys); reload(id);
};
