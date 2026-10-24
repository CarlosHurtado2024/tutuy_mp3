'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const duration = value => { const seconds = Math.floor(Number(value) || 0); return seconds ? (seconds >= 3600 ? `${Math.floor(seconds / 3600)}:${String(Math.floor(seconds % 3600 / 60)).padStart(2, '0')}` : Math.floor(seconds / 60)) + ':' + String(seconds % 60).padStart(2, '0') : '—'; };
const size = bytes => bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
const state = {page:'explorar', mode:'artist', songs:[], selected:new Set(), jobs:[], online:false, server:false, authenticated:false, local:false, searching:false, enqueueing:false, settings:{quality:192,limit:20}, jobsSignature:'', statusBusy:false};
try { Object.assign(state.settings, JSON.parse(localStorage.getItem('tutuy-preferences') || '{}')); } catch {}
if (![128,192,320].includes(Number(state.settings.quality))) state.settings.quality = 192;
if (![10,20,40].includes(Number(state.settings.limit))) state.settings.limit = 20;

async function api(path, data, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeout || 12000);
  try {
    const response = await fetch(`/api${path}`, {method:data === undefined ? 'GET' : 'POST', credentials:'same-origin', cache:'no-store', headers:data === undefined ? {} : {'Content-Type':'application/json'}, body:data === undefined ? undefined : JSON.stringify(data), signal:controller.signal});
    let result;
    try { result = await response.json(); } catch { throw new Error('La app respondió de forma inesperada. Vuelve a abrirla.'); }
    if (!response.ok) {
      if (response.status === 401 && path !== '/connect') requireConnection();
      throw Object.assign(new Error(result.error || 'No se pudo completar la solicitud.'), {status:response.status});
    }
    state.server = true;
    return result;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('La plataforma está tardando demasiado. Inténtalo de nuevo.');
    if (error instanceof TypeError) { state.server = false; paintConnection(); throw new Error('No hay conexión con Tutuy. Comprueba que esté abierto en el computador y que ambos dispositivos estén en la misma red.'); }
    throw error;
  } finally { clearTimeout(timeout); }
}

function toast(message, error = false) {
  const element = document.createElement('div');
  element.className = `toast${error ? ' error' : ''}`;
  element.textContent = message;
  $('#toast-area').append(element);
  setTimeout(() => element.remove(), error ? 9000 : 5000);
}

function requireConnection() {
  state.authenticated = false;
  state.online = false;
  if (!$('#connect-dialog').open) {
    $$('dialog[open]').forEach(dialog => dialog.close());
    $('#connect-dialog').showModal();
  }
  paintConnection();
}

function paintConnection() {
  const label = $('#connection-label');
  const dot = $('#connection .status-dot');
  const banner = $('#network-banner');
  const connected = state.server && state.authenticated;
  label.textContent = !connected ? 'Sin conexión con la app' : state.online ? 'Conexión a Internet' : 'Sin Internet';
  dot.className = `status-dot${connected && state.online ? '' : ' offline'}`;
  banner.hidden = connected && state.online;
  banner.textContent = !connected ? 'No hay conexión con Tutuy. Mantén la app abierta en el computador y conecta tus dispositivos a la misma red.' : 'El computador no tiene conexión a Internet. Puedes escuchar los MP3 terminados. Conéctalo para buscar o descargar.';
  updateSelection();
}

async function checkStatus(force = false) {
  if (!state.authenticated || state.statusBusy) return;
  state.statusBusy = true;
  try {
    const data = await api(`/status${force ? '?refresh=1' : ''}`, undefined, {timeout:16000});
    state.online = data.online;
    state.local = data.local;
    $('#music-folder').textContent = data.music_folder;
    $$('.open-folder').forEach(button => button.hidden = !data.local);
    $('#shutdown-button').hidden = !data.local;
    if (!data.youtube_runtime && !state.warnedRuntime) { state.warnedRuntime = true; toast('Falta el motor JavaScript de YouTube. Consulta el archivo README para configurarlo.', true); }
  } catch (error) {
    if (!error.status) state.server = false;
  } finally { state.statusBusy = false; paintConnection(); }
}

function page(name) {
  if (!['explorar','descargas','biblioteca'].includes(name)) name = 'explorar';
  state.page = name;
  $$('.page').forEach(element => element.hidden = element.id !== `page-${name}`);
  $$('[data-page]').forEach(button => { button.classList.toggle('active', button.dataset.page === name); button.setAttribute('aria-current', button.dataset.page === name ? 'page' : 'false'); });
  $('#page-crumb').textContent = {explorar:'Explorar',descargas:'Descargas',biblioteca:'Mi biblioteca'}[name];
  if (!location.hash.startsWith('#key=')) history.replaceState(null, '', `#${name}`);
  updateSelection();
  if (name !== 'explorar') pollJobs();
  window.scrollTo({top:0, behavior:'instant'});
}

function setMode(mode) {
  state.mode = mode;
  $$('.search-tab').forEach(button => { const active = button.dataset.mode === mode; button.classList.toggle('active', active); button.setAttribute('aria-selected', String(active)); });
  const input = $('#search-input');
  input.placeholder = {artist:'Nombre del artista o de la canción…', genre:'Salsa, rock, vallenato, jazz…', url:'https://www.youtube.com/watch?v=…'}[mode];
  input.setAttribute('aria-label', {artist:'Artista o canción',genre:'Género musical',url:'Enlace público de audio, video o lista'}[mode]);
  input.type = mode === 'url' ? 'url' : 'search';
  $('#provider').parentElement.hidden = mode === 'url';
  $('#search-hint').textContent = mode === 'url' ? 'Pega un enlace público de una plataforma compatible. Las listas se muestran hasta el límite elegido.' : mode === 'genre' ? 'El género se utiliza como término para encontrar música en la plataforma.' : 'Busca primero. Después elige las canciones que quieras descargar.';
}

function art(song) {
  return `<span class="song-art">${icon('music')}${song.thumbnail && /^https:\/\//.test(song.thumbnail) ? `<img src="${escapeHTML(song.thumbnail)}" loading="lazy" referrerpolicy="no-referrer" alt="">` : ''}</span>`;
}

function visibleSongs() {
  const query = $('#filter-results').value.trim().toLocaleLowerCase('es');
  const songs = state.songs.filter(song => `${song.title} ${song.artist}`.toLocaleLowerCase('es').includes(query));
  const sort = $('#sort-results').value;
  if (sort === 'title') songs.sort((a,b) => a.title.localeCompare(b.title, 'es'));
  if (sort === 'duration') songs.sort((a,b) => (a.duration || Infinity) - (b.duration || Infinity));
  return songs;
}

function renderSongs() {
  const songs = visibleSongs();
  $('#results-toolbar').hidden = state.songs.length === 0;
  $('#results-list').innerHTML = songs.map(song => `<div class="song-row${state.selected.has(song.id) ? ' selected' : ''}" data-id="${song.id}"><label class="song-select"><input type="checkbox" class="song-check" value="${song.id}" aria-label="Seleccionar ${escapeHTML(song.title)}" ${state.selected.has(song.id) ? 'checked' : ''}>${art(song)}<span class="song-info"><strong>${escapeHTML(song.title)}</strong><small>${escapeHTML(song.artist)} <span class="platform-tag">${escapeHTML(song.platform)}</span></small></span></label><span class="duration">${duration(song.duration)}</span><a class="icon-button row-source" href="${escapeHTML(song.url)}" target="_blank" rel="noopener noreferrer" title="Ver en la plataforma" aria-label="Ver ${escapeHTML(song.title)} en la plataforma">${icon('external')}</a></div>`).join('');
  if (!songs.length && state.songs.length) $('#results-list').innerHTML = `<div class="empty-state"><strong>Ninguna canción coincide con el filtro.</strong><p>Prueba con otra palabra.</p></div>`;
  updateSelection();
}

function updateSelection() {
  const count = state.selected.size;
  const shown = visibleSongs();
  const selectedVisible = shown.filter(song => state.selected.has(song.id)).length;
  $('#select-all').checked = shown.length > 0 && selectedVisible === shown.length;
  $('#select-all').indeterminate = selectedVisible > 0 && selectedVisible < shown.length;
  $('#selection-count').textContent = `${count} ${count === 1 ? 'canción seleccionada' : 'canciones seleccionadas'}`;
  const qualityText = `MP3 · ${state.settings.quality} kbps`;
  $('#selection-quality').textContent = qualityText;
  $('#quality-hint').textContent = qualityText;
  $('#selection-bar').hidden = count === 0 || state.page !== 'explorar';
  document.body.classList.toggle('has-selection', count > 0 && state.page === 'explorar');
  $('#download-selected').disabled = !count || !state.online || !state.server || state.enqueueing || !state.authenticated;
  $('#download-selected span').textContent = state.enqueueing ? 'Preparando…' : 'Descargar selección';
}

async function search(event) {
  event?.preventDefault();
  if (state.searching) return;
  const query = $('#search-input').value.trim();
  if (query.length < 2) return;
  if (!state.authenticated) { requireConnection(); return; }
  state.searching = true;
  state.songs = [];
  state.selected.clear();
  $('#filter-results').value = '';
  $('#results-section').hidden = false;
  $('#results-description').textContent = `Buscando «${query}»`;
  $('#search-error').hidden = true;
  $('#results-list').innerHTML = '';
  $('#results-loading').hidden = false;
  $('#results-toolbar').hidden = true;
  $('#search-button').disabled = true;
  $('#search-button span').textContent = 'Buscando…';
  updateSelection();
  try {
    const data = await api('/search', {query, mode:state.mode, provider:$('#provider').value, limit:Number(state.settings.limit)}, {timeout:180000});
    state.online = true;
    state.songs = data.songs;
    $('#results-description').textContent = `${data.songs.length} ${data.songs.length === 1 ? 'resultado' : 'resultados'} para «${query}» · Selecciona tus favoritos`;
    renderSongs();
    if (!data.songs.length) $('#results-list').innerHTML = `<div class="empty-state">${icon('search')}<strong>No encontramos canciones esta vez.</strong><p>Prueba con otro artista, otra plataforma o un enlace directo.</p></div>`;
  } catch (error) {
    $('#search-error').textContent = error.message;
    $('#search-error').hidden = false;
    $('#results-description').textContent = 'Puedes cambiar la búsqueda e intentarlo de nuevo.';
    if (error.status === 503) state.online = false;
  } finally {
    state.searching = false;
    $('#results-loading').hidden = true;
    $('#search-button').disabled = false;
    $('#search-button span').textContent = 'Buscar música';
    paintConnection();
  }
}

async function downloadSelection() {
  if (state.enqueueing || !state.selected.size) return;
  state.enqueueing = true;
  updateSelection();
  try {
    const data = await api('/downloads', {ids:[...state.selected],quality:Number(state.settings.quality)}, {timeout:18000});
    toast(`${data.ids.length} ${data.ids.length === 1 ? 'canción añadida' : 'canciones añadidas'} a tus descargas.`);
    state.selected.clear();
    renderSongs();
    page('descargas');
  } catch (error) {
    toast(error.message, true);
    if (error.status === 503) { state.online = false; paintConnection(); }
  } finally { state.enqueueing = false; updateSelection(); }
}

const statusLabels = {queued:'En cola',downloading:'Descargando',converting:'Convirtiendo a MP3',completed:'Listo para escuchar',error:'No se pudo descargar',cancelled:'Cancelada'};
function jobRow(job, library = false) {
  const completed = job.status === 'completed';
  const active = ['queued','downloading','converting'].includes(job.status);
  const failed = ['error','cancelled'].includes(job.status);
  const details = library ? `<span class="duration">${duration(job.duration)}<br>${size(job.size)}</span>` : `<div class="job-detail"><div class="job-status ${job.status}">${completed ? icon('check') : ''}${statusLabels[job.status] || 'En espera'}</div>${active ? `<div class="progress-track" role="progressbar" aria-label="Progreso de ${escapeHTML(job.title)}" aria-valuenow="${Math.round(job.progress)}" aria-valuemin="0" aria-valuemax="100"><div class="progress-fill" style="width:${Math.min(100,Math.max(0,Number(job.progress)||0))}%"></div></div><div class="job-transfer">${Math.round(job.progress)}% ${job.speed ? `· ${size(job.speed)}/s` : ''} ${job.eta ? `· ${duration(job.eta)} restantes` : ''}</div>` : completed ? `<span class="job-transfer">MP3 · ${job.quality} kbps · ${size(job.size)}</span>` : ''}</div>`;
  return `<div class="song-row job-row" data-id="${job.id}">${art(job)}<div class="song-info"><strong>${escapeHTML(job.title)}</strong><small>${escapeHTML(job.artist)} <span class="platform-tag">${escapeHTML(job.platform)}</span></small>${job.status === 'error' ? `<p class="job-error">${escapeHTML(job.error)}</p>` : ''}</div>${details}<div class="row-actions">${completed ? `<button class="icon-button" data-action="play" data-id="${job.id}" title="Escuchar" aria-label="Escuchar ${escapeHTML(job.title)}">${icon('play')}</button><a class="icon-button" href="/api/downloads/${job.id}/file?save=1" title="Guardar MP3 en este dispositivo" aria-label="Guardar ${escapeHTML(job.title)} en este dispositivo" download>${icon('download')}</a>` : active ? `<button class="icon-button" data-action="cancel" data-id="${job.id}" title="Cancelar descarga" aria-label="Cancelar ${escapeHTML(job.title)}">${icon('close')}</button>` : failed ? `<button class="icon-button" data-action="retry" data-id="${job.id}" title="Reintentar" aria-label="Reintentar ${escapeHTML(job.title)}">${icon('retry')}</button>` : ''}</div></div>`;
}

function empty(title, copy, symbol = 'music', action = false) {
  return `<div class="empty-state">${icon(symbol)}<strong>${title}</strong><p>${copy}</p>${action ? '<button class="primary" data-page="explorar">Encontrar mi música</button>' : ''}</div>`;
}

function renderJobs() {
  const counts = {active:0,completed:0,failed:0};
  state.jobs.forEach(job => { if (job.status === 'completed') counts.completed++; else if (['error','cancelled'].includes(job.status)) counts.failed++; else counts.active++; });
  $('#download-stats').innerHTML = `<div class="stat"><strong>${counts.active}</strong><small>En progreso o en cola</small></div><div class="stat"><strong>${counts.completed}</strong><small>MP3 terminados</small></div><div class="stat"><strong>${counts.failed}</strong><small>Por reintentar</small></div>`;
  $('#queue-badge').textContent = counts.active;
  $('#queue-badge').hidden = !counts.active;
  $('#downloads-list').innerHTML = state.jobs.length ? state.jobs.map(job => jobRow(job)).join('') : empty('Aquí empieza tu colección.', 'Busca tu música favorita y añade canciones. El progreso aparecerá aquí.', 'download', true);
  renderLibrary();
}

function renderLibrary() {
  const filter = $('#library-filter').value.trim().toLocaleLowerCase('es');
  const all = state.jobs.filter(job => job.status === 'completed');
  const songs = all.filter(job => `${job.title} ${job.artist}`.toLocaleLowerCase('es').includes(filter));
  $('#library-count').textContent = `${all.length} ${all.length === 1 ? 'canción' : 'canciones'} · ${size(all.reduce((sum,job) => sum + job.size, 0))}`;
  $('#library-list').innerHTML = songs.length ? songs.map(job => jobRow(job,true)).join('') : filter && all.length ? empty('No hay coincidencias.', 'Prueba otro nombre de canción o artista.', 'search') : empty('Tus favoritos tendrán un lugar aquí.', 'Los MP3 que termines de descargar estarán listos para escuchar y guardar en todos tus dispositivos.', 'library', true);
}

let polling = false;
async function pollJobs() {
  if (!state.authenticated || polling) return;
  polling = true;
  try {
    const data = await api('/downloads');
    const signature = JSON.stringify(data.jobs);
    if (signature !== state.jobsSignature) {
      const previous = new Map(state.jobs.map(job => [job.id,job.status]));
      data.jobs.forEach(job => { if (job.status === 'completed' && previous.has(job.id) && previous.get(job.id) !== 'completed') toast(`MP3 listo: ${job.title}`); });
      state.jobs = data.jobs;
      state.jobsSignature = signature;
      renderJobs();
    }
  } catch (error) { if (!error.status) paintConnection(); }
  finally { polling = false; }
}

async function jobAction(event) {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const {action,id} = button.dataset;
  if (action === 'play') {
    const job = state.jobs.find(item => item.id === id);
    $('#player-title').textContent = job.title;
    $('#player-artist').textContent = job.artist;
    $('#audio').src = `/api/downloads/${id}/file`;
    $('#player').hidden = false;
    document.body.classList.add('has-player');
    try { await $('#audio').play(); } catch { toast('Pulsa reproducir para escuchar el archivo.'); }
    return;
  }
  button.disabled = true;
  try { await api(`/downloads/${id}/${action}`, {}, {timeout:18000}); await pollJobs(); }
  catch (error) { toast(error.message,true); button.disabled = false; }
}

async function showPair() {
  if (!state.local) { toast('Abre «Conectar dispositivo» desde Tutuy en el computador principal.'); return; }
  $('#pair-content').innerHTML = '<span class="spinner"></span>';
  $('#pair-dialog').showModal();
  try {
    const data = await api('/pair');
    if (!data.urls.length) { $('#pair-content').innerHTML = '<p class="field-help">No se encontró una dirección de red. Conecta el computador a Wi-Fi y abre esta ventana de nuevo.</p>'; return; }
    const renderQR = url => {
      const base = url.split('/#')[0];
      $('#pair-content').innerHTML = `<img src="/api/qr?address=${encodeURIComponent(base)}" alt="Código QR para conectar tu celular"><code>${escapeHTML(base)}</code>${data.urls.length > 1 ? `<select id="pair-address" aria-label="Dirección de red">${data.urls.map(item => `<option value="${escapeHTML(item)}"${item === url ? ' selected' : ''}>${escapeHTML(item.split('/#')[0])}</option>`).join('')}</select>` : ''}<button class="secondary" id="copy-pair-link">${icon('link')}Copiar enlace completo</button>`;
      $('#pair-address')?.addEventListener('change', event => renderQR(event.target.value));
      $('#copy-pair-link').addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(url); toast('Enlace copiado. Ábrelo en tu celular.'); }
        catch { const input = document.createElement('input'); input.value = url; $('#pair-content').append(input); input.select(); toast('Selecciona y copia el enlace que aparece debajo del código.'); }
      });
    };
    renderQR(data.urls[0]);
  } catch (error) { $('#pair-content').textContent = error.message; }
}

function settings() { $('#settings-dialog').showModal(); }
function saveSettings() {
  state.settings.quality = Number($('#quality').value);
  state.settings.limit = Number($('#result-limit').value);
  try { localStorage.setItem('tutuy-preferences', JSON.stringify(state.settings)); } catch {}
  updateSelection();
}

async function connect(key) {
  await api('/connect',{key});
  state.authenticated = true;
  if ($('#connect-dialog').open) $('#connect-dialog').close();
  await Promise.allSettled([checkStatus(),pollJobs()]);
}

document.addEventListener('click', event => {
  const navigation = event.target.closest('[data-page]');
  if (navigation) page(navigation.dataset.page);
  const close = event.target.closest('.close-dialog');
  if (close) close.closest('dialog').close();
});
$$('.search-tab').forEach(button => button.addEventListener('click', () => { if (state.searching) return; setMode(button.dataset.mode); $('#search-input').value = ''; $('#search-input').focus(); }));
$('#search-form').addEventListener('submit',search);
$('#genres').addEventListener('click', event => { const button = event.target.closest('[data-genre]'); if (!button || state.searching) return; setMode('genre'); $('#search-input').value = button.dataset.genre; search(); $('#results-section').scrollIntoView({behavior:'smooth',block:'start'}); });
$('#results-list').addEventListener('change', event => { if (!event.target.matches('.song-check')) return; const {value,checked} = event.target; if (checked) state.selected.add(value); else state.selected.delete(value); event.target.closest('.song-row').classList.toggle('selected', checked); updateSelection(); });
$('#select-all').addEventListener('change', event => { visibleSongs().forEach(song => event.target.checked ? state.selected.add(song.id) : state.selected.delete(song.id)); renderSongs(); });
$('#filter-results').addEventListener('input',renderSongs);
$('#sort-results').addEventListener('change',renderSongs);
$('#clear-selection').addEventListener('click', () => { state.selected.clear(); renderSongs(); });
$('#clear-results').addEventListener('click', () => { if (state.searching) return; state.songs = []; state.selected.clear(); $('#results-section').hidden = true; $('#search-input').value = ''; updateSelection(); });
$('#download-selected').addEventListener('click',downloadSelection);
$('#downloads-list').addEventListener('click',jobAction);
$('#library-list').addEventListener('click',jobAction);
$('#library-filter').addEventListener('input',renderLibrary);
$('#settings-button').addEventListener('click',settings);
$('#avatar-button').addEventListener('click',settings);
$('#quality').value = state.settings.quality;
$('#result-limit').value = state.settings.limit;
$('#quality').addEventListener('change',saveSettings);
$('#result-limit').addEventListener('change',saveSettings);
$('#pair-button').addEventListener('click',showPair);
$('#help-button').addEventListener('click',() => $('#help-dialog').showModal());
// Also expose pairing on small screens, where the sidebar becomes bottom navigation.
const pairMobile = document.createElement('button'); pairMobile.id = 'pair-mobile-button'; pairMobile.className = 'secondary full'; pairMobile.innerHTML = `${icon('phone')}Conectar otro dispositivo`; pairMobile.addEventListener('click', () => { $('#settings-dialog').close(); showPair(); }); $('#settings-dialog .setting-folder').after(pairMobile);
$('#connection').addEventListener('click', () => { if (!state.authenticated) requireConnection(); else checkStatus(true); });
$$('.open-folder').forEach(button => button.addEventListener('click', async () => { try { await api('/open-folder',{}); } catch (error) { toast(error.message,true); } }));
$('#close-player').addEventListener('click',() => { $('#audio').pause(); $('#audio').removeAttribute('src'); $('#player').hidden = true; document.body.classList.remove('has-player'); });
$('#audio').addEventListener('error',() => toast('No se pudo abrir el MP3. Comprueba si sigue en la carpeta Música y si hay conexión con la app.',true));
$('#shutdown-button').addEventListener('click',async () => {
  if (!confirm('¿Cerrar Tutuy MP3? Las descargas en curso se cancelarán y el celular se desconectará.')) return;
  try { await api('/shutdown',{}); $('#settings-dialog').close(); state.server = false; state.authenticated = false; paintConnection(); toast('Tutuy se cerró. Puedes cerrar esta ventana.'); }
  catch (error) { toast(error.message,true); }
});
$('#connect-form').addEventListener('submit',async event => {
  event.preventDefault();
  let value = $('#connection-key').value.trim();
  try { if (value.includes('#')) value = new URLSearchParams(value.slice(value.indexOf('#') + 1)).get('key') || value; await connect(value); }
  catch (error) { $('#connect-error').textContent = error.message; }
});
document.addEventListener('keydown',event => { if (event.key === '/' && !event.ctrlKey && !event.metaKey && !['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName) && !document.querySelector('dialog[open]')) { event.preventDefault(); page('explorar'); $('#search-input').focus(); } });
window.addEventListener('online', () => checkStatus(true));
window.addEventListener('offline', () => { state.server = false; paintConnection(); });
window.addEventListener('hashchange', () => { if (!location.hash.startsWith('#key=')) page(location.hash.slice(1)); });
document.addEventListener('visibilitychange', () => { if (!document.hidden) { checkStatus(); pollJobs(); } });

async function boot() {
  renderJobs();
  updateSelection();
  // A static deployment can show the interface before a persistent API is linked.
  // Do not confuse that setup state with missing Internet or a wrong pairing key.
  try {
    const deployment = await fetch('/deployment.json', {cache:'no-store'});
    if (deployment.ok && (await deployment.json()).mode === 'hosted') {
      const health = await fetch('/api/health', {cache:'no-store'});
      let service = null;
      if (health.ok) { try { service = await health.json(); } catch {} }
      if (!service?.ready || service.app !== 'Tutuy MP3') {
        $('#connection-label').textContent = 'Motor de descargas pendiente';
        $('#connection .status-dot').className = 'status-dot offline';
        $('#network-banner').hidden = false;
        $('#network-banner').textContent = 'Esta versión web aún no está conectada al servidor de descargas. Puedes usar la app portable mientras se completa la conexión.';
        $('#search-button').disabled = true;
        $('#search-input').disabled = true;
        $('#provider').disabled = true;
        $$('#genres button').forEach(button => button.disabled = true);
        $$('.open-folder').forEach(button => button.hidden = true);
        $('#shutdown-button').hidden = true;
        page(location.hash.slice(1));
        return;
      }
    }
  } catch { /* The local desktop server has no hosted deployment descriptor. */ }
  const params = new URLSearchParams(location.hash.slice(1));
  const key = params.get('key');
  if (key) {
    history.replaceState(null,'',location.pathname + '#explorar');
    try { await connect(key); } catch (error) { requireConnection(); $('#connect-error').textContent = error.message; }
  } else {
    try { const data = await api('/status', undefined, {timeout:16000}); state.authenticated = true; state.online = data.online; state.local = data.local; $('#music-folder').textContent = data.music_folder; await Promise.allSettled([checkStatus(),pollJobs()]); }
    catch { requireConnection(); }
  }
  page(key ? 'explorar' : location.hash.slice(1));
  paintConnection();
  setInterval(() => { if (!document.hidden) pollJobs(); },2500);
  setInterval(() => { if (!document.hidden) checkStatus(); },15000);
  if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => {});
}
boot();
