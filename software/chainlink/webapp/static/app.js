const $ = (id) => document.getElementById(id);
let state = null;
let selected = new Set();
let noticeTimer;

async function api(path, body) {
  const options = body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Splitflap-Request': '1'}, body: JSON.stringify(body)};
  const response = await fetch('/api/' + path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
function notify(message) {
  $('notice').textContent = message;
  $('notice').hidden = !message;
  clearTimeout(noticeTimer);
  if (message) noticeTimer = setTimeout(() => { $('notice').hidden = true; }, 8000);
}
async function command(path, body = {}) {
  try { await api(path, body); await update(); } catch (error) { notify(error.message); }
}
async function ports() {
  try {
    const available = await api('ports');
    const previous = $('ports').value;
    $('ports').replaceChildren();
    if (!available.length) $('ports').add(new Option('No ports found', ''));
    available.forEach(port => $('ports').add(new Option(`${port.device} - ${port.description}`, port.device)));
    if (available.some(port => port.device === previous)) $('ports').value = previous;
  } catch (error) { notify(error.message); }
}
function cell(row, text, className = '') {
  const item = row.insertCell();
  item.textContent = text;
  item.className = className;
  return item;
}
function renderModules() {
  const body = $('modules');
  body.replaceChildren();
  const modules = state.modules;
  selected = new Set([...selected].filter(index => index < modules.length));
  if (!modules.length) {
    const row = body.insertRow();
    const item = cell(row, 'Connect a device to see drum status.', 'empty');
    item.colSpan = 8;
  }
  modules.forEach(module => {
    const row = body.insertRow();
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox'; checkbox.checked = selected.has(module.index);
    checkbox.setAttribute('aria-label', `Select drum ${module.index + 1}`);
    checkbox.addEventListener('change', () => { checkbox.checked ? selected.add(module.index) : selected.delete(module.index); renderControls(); });
    row.insertCell().append(checkbox);
    cell(row, String(module.index + 1).padStart(2, '0'));
    const character = state.alphabet && state.alphabet[module.flap_index];
    cell(row, character === ' ' ? '\u2423' : (character || '?'), 'flap');
    cell(row, module.state.replaceAll('_', ' '), module.state === 'NORMAL' ? 'state-normal' : 'state-error');
    cell(row, module.moving ? 'Moving' : 'Stopped');
    cell(row, module.home_state ? 'Active' : 'Inactive');
    cell(row, module.count_missed_home);
    cell(row, module.count_unexpected_home);
  });
}
function renderList(id, entries, render) {
  const list = $(id); list.replaceChildren();
  if (!entries.length) { const item = document.createElement('li'); item.className = 'empty'; item.textContent = 'Nothing to report.'; list.append(item); return; }
  [...entries].reverse().forEach(entry => { const item = document.createElement('li'); render(item, entry); list.append(item); });
}
function renderControls() {
  if (!state) return;
  const ready = state && state.connection === 'ready' && !state.stale;
  const connected = state && ['connecting', 'ready'].includes(state.connection);
  $('connect').hidden = connected; $('disconnect').hidden = !connected;
  $('connect').disabled = connected || !$('ports').value;
  $('ports').disabled = connected; $('refresh-ports').disabled = connected;
  ['message', 'send', 'clear', 'request-state'].forEach(id => { $(id).disabled = !ready; });
  ['home', 'offset-tenth', 'offset-half', 'offset-set'].forEach(id => { $(id).disabled = !ready || !selected.size || state.busy; });
  $('save-offsets').disabled = !ready || state.busy || state.modules.some(module => module.moving || module.state === 'LOOK_FOR_HOME');
  $('select-all').disabled = !ready || !state.modules.length;
  $('select-all').checked = state.modules.length > 0 && selected.size === state.modules.length;
  $('select-all').indeterminate = selected.size > 0 && selected.size < state.modules.length;
  $('selection-count').textContent = selected.size;
  $('character-count').textContent = `${$('message').value.length} / ${state.modules.length || '--'}`;
}
async function update() {
  try {
    state = await api('status');
    $('firmware-warning').hidden = state.connection !== 'ready';
    $('connection-label').textContent = state.stale && state.connection === 'ready' ? 'Status stale' : state.connection.charAt(0).toUpperCase() + state.connection.slice(1);
    $('connection-dot').className = 'dot ' + (state.stale && state.connection === 'ready' ? 'error' : state.connection);
    $('port-name').textContent = state.port || 'Not connected';
    $('module-count').textContent = state.modules.length || '--';
    $('loopback').textContent = state.loopbacks_ok === null ? '--' : state.loopbacks_ok ? 'OK' : 'Fault';
    $('last-update').textContent = state.updated_at ? new Date(state.updated_at * 1000).toLocaleTimeString() : '--';
    $('firmware').textContent = state.build ? `${state.build.git_hash || 'Unknown'} / v${state.protocol_version}` : '--';
    $('alphabet').textContent = state.alphabet ? `Available: ${state.alphabet.replace(' ', '\u2423 ')}` : 'Available characters appear when connected.';
    if (state.error && $('notice').textContent !== state.error) notify(state.error);
    renderModules(); renderControls();
    renderList('operations', state.operations, (item, entry) => { const label = document.createElement('strong'); label.textContent = `${entry.label}: ${entry.status}`; item.append(label); if (entry.detail) { const detail = document.createElement('span'); detail.textContent = entry.detail; item.append(detail); } });
    renderList('logs', state.logs, (item, entry) => { item.textContent = `${new Date(entry.time * 1000).toLocaleTimeString()}  ${entry.message}`; });
    const lastSave = [...state.operations].reverse().find(item => item.label === 'Save offsets');
    $('save-status').textContent = lastSave ? `Save: ${lastSave.status}${lastSave.detail ? ' - ' + lastSave.detail : ''}` : 'Offsets are saved only while all drums are stopped.';
  } catch (error) { $('connection-label').textContent = 'Server unavailable'; $('connection-dot').className = 'dot error'; notify(error.message); }
}
$('refresh-ports').addEventListener('click', ports);
$('ports').addEventListener('change', renderControls);
$('connect').addEventListener('click', () => command('connect', {port: $('ports').value}));
$('disconnect').addEventListener('click', async () => { await command('disconnect'); selected.clear(); await ports(); });
$('message-form').addEventListener('submit', event => { event.preventDefault(); command('display', {text: $('message').value}); });
$('message').addEventListener('input', renderControls);
$('clear').addEventListener('click', () => command('clear'));
$('request-state').addEventListener('click', () => command('state/request'));
$('select-all').addEventListener('change', event => { selected = new Set(event.target.checked ? state.modules.map(module => module.index) : []); renderModules(); renderControls(); });
$('home').addEventListener('click', () => { if (confirm('Re-home selected drums? This clears their error counters.')) command('home', {modules: [...selected]}); });
for (const adjustment of ['tenth', 'half', 'set']) $('offset-' + adjustment).addEventListener('click', () => { if (adjustment !== 'set' || confirm('Set the selected drums\' offset to their current position?')) command('offset', {modules: [...selected], adjustment}); });
$('save-offsets').addEventListener('click', () => { if (confirm('Save offsets for all drums, including any with errors?')) command('offset/save'); });
ports().then(update);
setInterval(update, 1000);