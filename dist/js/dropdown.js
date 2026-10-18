// свои выпадающие списки вместо системных select; сам select остаётся скрытым и получает значение и change,
// поэтому остальной код работает как раньше. Меню открывается поверх всего (position: fixed), закрывается по клику вне, Esc, прокрутке.
let pop = null, popFor = null;

function closePop() {
  if (!pop) return;
  pop.remove(); pop = null;
  popFor?.btn.setAttribute('aria-expanded', 'false'); popFor?.btn.classList.remove('open'); popFor = null;
}

function openPop(dd) {
  closePop();
  const { sel, btn } = dd, r = btn.getBoundingClientRect();
  pop = document.createElement('ul');
  pop.className = 'dd-pop'; pop.setAttribute('role', 'listbox');
  pop.innerHTML = [...sel.options].map((o, i) => `<li role="option" data-i="${i}" aria-selected="${i === sel.selectedIndex}" class="${i === sel.selectedIndex ? 'on' : ''}"><span>${o.textContent.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))}</span><i class="fa-solid fa-check"></i></li>`).join('');
  document.body.appendChild(pop);
  const h = Math.min(pop.scrollHeight, 300), below = innerHeight - r.bottom - 12, up = below < h && r.top > below;
  pop.style.minWidth = r.width + 'px';
  pop.style.left = Math.max(8, Math.min(r.left, innerWidth - pop.offsetWidth - 8)) + 'px';
  pop.style.top = up ? '' : r.bottom + 6 + 'px'; pop.style.bottom = up ? innerHeight - r.top + 6 + 'px' : '';
  pop.style.maxHeight = Math.max(120, up ? r.top - 16 : below) + 'px';
  pop.classList.toggle('up', up);
  popFor = dd; btn.setAttribute('aria-expanded', 'true'); btn.classList.add('open');
  pop.querySelector('.on')?.scrollIntoView({ block: 'nearest' });
  pop.addEventListener('click', e => {
    const li = e.target.closest('li'); if (!li) return;
    sel.selectedIndex = +li.dataset.i; dd.sync(); closePop();
    sel.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

function enhance(sel) {
  if (sel.dataset.dd) return;
  sel.dataset.dd = '1'; sel.hidden = true;
  const wrap = document.createElement('div'), btn = document.createElement('button');
  wrap.className = 'dd ' + (sel.className.replace('field', '').trim());
  btn.type = 'button'; btn.className = 'dd-btn'; btn.setAttribute('aria-haspopup', 'listbox'); btn.setAttribute('aria-expanded', 'false');
  btn.setAttribute('aria-label', sel.getAttribute('aria-label') || '');
  btn.innerHTML = '<span class="dd-val"></span><i class="fa-solid fa-chevron-down"></i>';
  sel.after(wrap); wrap.append(btn);
  const dd = { sel, btn, sync() { btn.querySelector('.dd-val').textContent = sel.options[sel.selectedIndex]?.textContent ?? ''; } };
  dd.sync();
  btn.addEventListener('click', e => { e.stopPropagation(); popFor === dd ? closePop() : openPop(dd); });
  btn.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const n = sel.options.length, i = Math.max(0, Math.min(n - 1, sel.selectedIndex + (e.key === 'ArrowDown' ? 1 : -1)));
      if (i !== sel.selectedIndex) { sel.selectedIndex = i; dd.sync(); sel.dispatchEvent(new Event('change', { bubbles: true })); }
    }
  });
  sel.addEventListener('change', () => dd.sync());  // значение изменили программно
}

const scan = root => root.querySelectorAll?.('select.field:not([data-dd])').forEach(enhance);
export function initDropdowns() {
  scan(document);
  new MutationObserver(ms => { for (const m of ms) m.addedNodes.forEach(n => n.nodeType === 1 && (n.matches?.('select.field') ? enhance(n) : scan(n))); })
    .observe(document.body, { childList: true, subtree: true });
  document.addEventListener('click', e => { if (pop && !pop.contains(e.target)) closePop(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && pop) { e.stopPropagation(); closePop(); } }, true);
  addEventListener('resize', closePop);
  document.addEventListener('scroll', e => { if (pop && !pop.contains(e.target)) closePop(); }, true);
}
