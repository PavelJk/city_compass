// вход и профиль; без сервера (статический хостинг) всё хранится локально
import { snapshot, actions } from './state.js';

export const auth = { available: null, user: null };

async function call(method, url, body) {
  try {
    const r = await fetch(url, {
      method, credentials: 'same-origin',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await r.json(); } catch { /* пустой ответ */ }
    return { ok: r.ok, status: r.status, data: data || {} };
  } catch {
    return { ok: false, status: 0, data: {} };
  }
}

// 200 — вошли, 401 — API есть, но не вошли, всё остальное — API недоступен
export async function initAuth() {
  const r = await call('GET', '/api/me');
  auth.available = r.status === 200 || r.status === 401;
  auth.user = r.ok ? r.data.user : null;
  return r.ok ? r.data.settings || {} : null;
}

const done = r => ({ ok: r.ok, message: r.data.message || (r.ok ? '' : r.status === 0 ? 'Нет связи с сервером' : 'Не получилось, попробуйте ещё раз'), data: r.data });

export async function register(email, password, name) {
  const r = await call('POST', '/api/register', { email, password, name });
  if (r.ok) auth.user = r.data.user;
  return done(r);
}
export async function login(email, password) {
  const r = await call('POST', '/api/login', { email, password });
  if (r.ok) auth.user = r.data.user;
  return done(r);
}
export async function logout() {
  await call('POST', '/api/logout');
  auth.user = null;
}
export async function updateProfile(name, color) {
  const r = await call('PUT', '/api/me', { name, color });
  if (r.ok) auth.user = r.data.user;
  return done(r);
}
export const changePassword = async (oldPw, newPw) => done(await call('PUT', '/api/password', { old: oldPw, new: newPw }));
export async function deleteAccount(password) {
  const r = await call('DELETE', '/api/me', { password });
  if (r.ok) auth.user = null;
  return done(r);
}

// отправляем настройки с задержкой, а не на каждое нажатие
let timer = null;
actions.sync = () => {
  if (!auth.user) return;
  clearTimeout(timer);
  timer = setTimeout(() => call('PUT', '/api/settings', { settings: snapshot() }), 800);
};
export const flushSync = () => call('PUT', '/api/settings', { settings: snapshot() });
