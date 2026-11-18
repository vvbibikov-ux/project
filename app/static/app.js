// Планировщик проектов — фронтенд
let currentProjectId = null;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) { const e = await r.json().catch(() => ({})); toast(e.error || 'Ошибка запроса'); throw new Error(r.status); }
  return r.json();
}
function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2600);
}
function fmtSize(n) { return n > 1048576 ? (n/1048576).toFixed(1)+' МБ' : n > 1024 ? (n/1024).toFixed(1)+' КБ' : n+' Б'; }

// ---------- Вкладки ----------
$('tabProjects').onclick = () => { $('viewProjects').style.display=''; $('viewAnalyzer').style.display='none';
  $('tabProjects').classList.add('active'); $('tabAnalyzer').classList.remove('active'); };
$('tabAnalyzer').onclick = () => { $('viewProjects').style.display='none'; $('viewAnalyzer').style.display='';
  $('tabAnalyzer').classList.add('active'); $('tabProjects').classList.remove('active'); runAnalysis(); };

// ---------- Проекты ----------
async function createProject() {
  const name = $('pName').value.trim();
  if (!name) return toast('Введите название проекта');
  await api('/api/projects', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ name, description: $('pDesc').value.trim() }) });
  $('pName').value = ''; $('pDesc').value = '';
  loadProjects();
}

async function deleteProject(id, name) {
  if (!confirm(`Удалить проект «${name}» со всеми задачами и файлами?`)) return;
  await api('/api/projects/'+id, { method:'DELETE' });
  loadProjects();
}

async function toggleStatus(id, status) {
  const next = status === 'active' ? 'paused' : status === 'paused' ? 'done' : 'active';
  await api('/api/projects/'+id, { method:'PUT', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ status: next }) });
  loadProjects();
}

const statusLabel = { active:'▶ активен', paused:'⏸ пауза', done:'✔ завершён' };

async function loadProjects() {
  const projects = await api('/api/projects');
  $('projectList').innerHTML = projects.map(p => `
    <div class="card project ${p.status}" id="proj-${p.id}">
      <div class="proj-head">
        <div><h2 style="margin:0">${esc(p.name)}</h2>
          <div class="badges">
            <span>${statusLabel[p.status]||p.status}</span>
            <span>📂 задач: ${p.open_tasks}</span><span>✅ готово: ${p.done_tasks}</span><span>📎 файлов: ${p.file_count}</span>
          </div></div>
        <div class="row">
          <button class="btn" onclick="toggleStatus(${p.id},'${p.status}')">Сменить статус</button>
          <button class="btn danger" onclick="deleteProject(${p.id}, '${esc(p.name)}')">Удалить</button>
        </div>
      </div>
      ${p.description ? `<p style="color:#667">${esc(p.description)}</p>` : ''}
      <div class="row"><button class="btn primary" onclick="openTaskDialog(null, ${p.id})">➕ Новая задача</button></div>
      <div id="tasks-${p.id}"><em>задачи не загружены</em></div>
    </div>`).join('') || '<div class="card">Пока нет проектов — создайте первый 🙂</div>';
  for (const p of projects) loadTasks(p.id);
}

// ---------- Задачи ----------
function openTaskDialog(task, projectId) {
  currentProjectId = projectId;
  $('tdTitle').textContent = task ? 'Редактировать задачу' : 'Новая задача';
  $('tdId').value = task ? task.id : '';
  $('tdName').value = task ? task.title : '';
  $('tdDesc').value = task ? task.description : '';
  $('tdPriority').value = task ? task.priority : 'medium';
  $('tdDue').value = task && task.due_date ? task.due_date.replace(' ', 'T') : '';
  $('taskDialog').showModal();
}
function closeTaskDialog() { $('taskDialog').close(); }

async function saveTask() {
  const id = $('tdId').value;
  const data = { title: $('tdName').value.trim(), description: $('tdDesc').value.trim(),
                 priority: $('tdPriority').value, due_date: $('tdDue').value.replace('T',' ') };
  if (!data.title) return toast('Введите название задачи');
  if (id) await api('/api/tasks/'+id, { method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data) });
  else await api('/api/tasks', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({...data, project_id: currentProjectId}) });
  closeTaskDialog();
  loadTasks(currentProjectId); loadProjectsHead();
}

async function deleteTask(id, pid) {
  if (!confirm('Удалить задачу и её файлы?')) return;
  await api('/api/tasks/'+id, { method:'DELETE' });
  loadTasks(pid); loadProjectsHead();
}

async function toggleDone(t) {
  await api('/api/tasks/'+t.id, { method:'PUT', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ status: t.status === 'done' ? 'open' : 'done' }) });
  loadTasks(t.project_id); loadProjectsHead();
}

function dueBadge(t) {
  if (!t.due_date) return '';
  const now = new Date(), due = new Date(t.due_date.replace(' ','T'));
  if (t.status === 'done') return `<span>📅 ${esc(t.due_date)}</span>`;
  if (due < now) return `<span class="${t.reminder_sent?'reminded':'overdue'}">🔔 НАПОМИНАНИЕ! ${esc(t.due_date)}</span>`;
  const hrs = (due - now)/3600000;
  if (hrs <= 72) return `<span class="soon">⏳ скоро: ${esc(t.due_date)}</span>`;
  return `<span>📅 ${esc(t.due_date)}</span>`;
}

const prioLabel = { high:'🔴 высокий', medium:'🟡 средний', low:'🟢 низкий' };

async function loadTasks(pid) {
  const box = $('tasks-'+pid); if (!box) return;
  const tasks = await api(`/api/projects/${pid}/tasks`);
  box.innerHTML = tasks.length ? tasks.map(t => `
    <div class="task ${t.status==='done'?'done-task':''}">
      <input type="checkbox" ${t.status==='done'?'checked':''} onchange='toggleDone(${JSON.stringify(t).replace(/'/g,"&#39;")})'>
      <div class="t-body">
        <div class="t-title"><b>${esc(t.title)}</b> <span class="prio-${t.priority}">${prioLabel[t.priority]}</span> ${dueBadge(t)}</div>
        ${t.description ? `<div class="t-meta">${esc(t.description)}</div>` : ''}
        <div>${(t.files||[]).map(f => `
          <span class="file-chip">📎 <a href="/files/${f.id}/download">${esc(f.original_name)}</a>
          <small>(${fmtSize(f.size)})</small>
          <a href="#" onclick="delFile(${f.id},${pid});return false">✖</a></span>`).join('')}
          <label class="file-chip" style="cursor:pointer">⬆ прикрепить файл
            <input type="file" style="display:none" onchange="uploadFile(event, ${t.id}, ${pid})"></label>
        </div>
      </div>
      <div class="row">
        <button class="btn" onclick='openTaskDialog(${JSON.stringify(t).replace(/'/g,"&#39;")}, ${pid})'>✏️</button>
        <button class="btn danger" onclick="deleteTask(${t.id}, ${pid})">🗑</button>
      </div>
    </div>`).join('') : '<em>Задач пока нет</em>';
}

async function delFile(fid, pid) { await api('/api/files/'+fid, {method:'DELETE'}); loadTasks(pid); }

async function uploadFile(ev, tid, pid) {
  const file = ev.target.files[0]; if (!file) return;
  const fd = new FormData(); fd.append('file', file);
  await api('/api/tasks/'+tid+'/files', { method:'POST', body: fd });
  toast('Файл загрушен'); loadTasks(pid);
}

async function loadProjectsHead() {
  const projects = await api('/api/projects');
  projects.forEach(p => {
    const el = document.querySelector(`#proj-${p.id} .badges`);
    if (el) el.innerHTML = `<span>${statusLabel[p.status]||p.status}</span>
      <span>📂 задач: ${p.open_tasks}</span><span>✅ готово: ${p.done_tasks}</span><span>📎 файлов: ${p.file_count}</span>`;
  });
}

// ---------- Анализатор ----------
async function runAnalysis() {
  const d = await api('/api/analyze');
  const s = d.summary;
  let html = `<div class="stat-grid">
    <div class="stat"><b>${s.projects}</b>проектов</div>
    <div class="stat"><b>${s.tasks}</b>всего задач</div>
    <div class="stat"><b>${s.open_tasks}</b>открытых</div>
    <div class="stat"><b style="color:#c0392b">${s.overdue}</b>просрочено</div>
    <div class="stat"><b>${s.files}</b>файлов (${fmtSize(s.files_size)})</div>
  </div>`;
  for (const r of d.projects) {
    html += `<h3>${esc(r.project.name)} — ${r.completion}% выполнено</h3>
      <progress value="${r.completion}" max="100" style="width:100%"></progress>
      ${r.recommendations.map(x=>`<div class="rec">💡 ${esc(x)}</div>`).join('')}`;
  }
  $('analysisResult').innerHTML = html;
}

loadProjects();
setInterval(() => { if (currentProjectId) loadTasks(currentProjectId); }, 30000); // автообновление напоминаний
