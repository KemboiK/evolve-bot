# evolve_dashboard.py
"""
Rugike Motors Admin Dashboard (Flask)
---------------------------------------------------
Admin console for Rugike Motors Support Bot.

Run:
  BACKEND_URL=http://127.0.0.1:5000 ADMIN_KEY=admin-secret-key python evolve_dashboard.py

The dashboard calls the support bot's endpoints (history, tickets, kb, users).
"""
from flask import Flask, render_template_string, jsonify, request
import os

app = Flask(__name__)
app.secret_key = os.environ.get('BOT_SECRET_KEY', 'local-secret')

# Backend support-bot URL (evolve.py)
BACKEND_URL = os.environ.get('BACKEND_URL', 'http://127.0.0.1:5000')
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'admin-secret-key')

TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Rugike Motors — Support Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
  :root{
    --bg:#0d1117; --card:#161b22; --accent:#00d084; --muted:#9aa6b2; --text:#e6edf3;
  }
  body{margin:0;font-family:Inter, Arial, sans-serif;background:var(--bg);color:var(--text);padding:20px;}
  header{display:flex;align-items:center;gap:16px;margin-bottom:18px;}
  h1{margin:0;color:var(--accent);font-size:20px;}
  .grid{display:grid;grid-template-columns:320px 1fr;gap:18px;}
  .card{background:var(--card);border-radius:10px;padding:14px;box-shadow:0 6px 18px rgba(0,0,0,.5);}
  .small-row{display:flex;gap:8px;align-items:center;}
  button{background:var(--accent);color:#0d1117;border:none;padding:8px 10px;border-radius:8px;cursor:pointer;font-weight:600;}
  button.ghost{background:transparent;border:1px solid rgba(255,255,255,.06);color:var(--text);}
  input,textarea,select{width:100%;padding:8px;border-radius:8px;border:1px solid rgba(255,255,255,.06);background:transparent;color:var(--text);margin-top:8px}
  .list{max-height:420px;overflow:auto;margin-top:10px;padding-right:6px;}
  li{list-style:none;padding:8px;border-bottom:1px dashed rgba(255,255,255,.03);}
  .muted{color:var(--muted);font-size:13px;}
  .row{display:flex;gap:8px;align-items:center;}
  .badge{background:#072a17;color:var(--accent);padding:6px 8px;border-radius:8px;font-weight:700}
  .section-title{display:flex;justify-content:space-between;align-items:center;}
  pre{white-space:pre-wrap;background:#071317;padding:10px;border-radius:8px;border:1px solid rgba(255,255,255,.03);color:var(--text)}
  .controls{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
</style>
</head>
<body>
<header>
  <h1>Rugike Motors — Support Dashboard</h1>
  <div class="muted">Backend: <span id="backendUrl">{{ backend_url }}</span></div>
</header>

<div class="grid">
  <!-- Left column: quick controls + tickets -->
  <div>
    <div class="card">
      <div class="section-title">
        <div><strong>Quick Actions</strong></div>
        <div class="muted">Admin</div>
      </div>

      <div class="controls">
        <button onclick="refreshAll()">Refresh All</button>
        <button class="ghost" onclick="toggleAuto()">Auto: <span id="autoState">OFF</span></button>
        <button class="ghost" onclick="openNewTicket()">New Ticket</button>
      </div>

      <div style="margin-top:12px;">
        <div class="muted">Search KB</div>
        <div style="display:flex;gap:8px;margin-top:8px">
          <input id="kbQuery" placeholder="eg. how to list a car" />
          <button onclick="searchKB()">Search</button>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:14px;">
      <div class="section-title"><strong>Open Tickets</strong><span class="muted" id="ticketCount">—</span></div>
      <ul id="tickets" class="list"></ul>
    </div>

    <div class="card" style="margin-top:14px;">
      <div class="section-title"><strong>Active Users</strong><span class="muted" id="userCount">—</span></div>
      <ul id="users" class="list"></ul>
    </div>
  </div>

  <!-- Right column: details -->
  <div>
    <div class="card">
      <div class="section-title">
        <strong>Recent Conversations</strong>
        <div class="muted">Choose session</div>
      </div>

      <div style="display:flex;gap:8px;margin-top:12px;">
        <select id="sessionSelect" style="width:320px" onchange="loadConversation()">
          <option value="">-- select session --</option>
        </select>
        <button class="ghost" onclick="loadConversation()">Load</button>
      </div>

      <div style="margin-top:12px;">
        <div id="conversation" style="max-height:360px;overflow:auto;padding:8px;border-radius:8px;background:#071317;border:1px solid rgba(255,255,255,.02)"></div>
      </div>
    </div>

    <div class="card" style="margin-top:14px;">
      <div class="section-title">
        <strong>Knowledge Base</strong>
        <div class="muted">Search & add</div>
      </div>

      <div style="margin-top:12px;display:flex;gap:12px;">
        <div style="flex:1">
          <div class="muted">Results</div>
          <div id="kbResults" class="list" style="max-height:180px"></div>
        </div>
        <div style="width:320px">
          <div class="muted">Add KB Article</div>
          <input id="kbQ" placeholder="Question (short)" />
          <textarea id="kbA" rows="6" placeholder="Answer (detailed)"></textarea>
          <input id="kbTags" placeholder="tags,comma,separated" />
          <div style="display:flex;gap:8px;margin-top:8px">
            <button onclick="addKB()">Add KB</button>
            <button class="ghost" onclick="clearKBForm()">Clear</button>
          </div>
          <div id="kbMsg" style="margin-top:8px" class="muted"></div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:14px;">
      <div class="section-title">
        <strong>System / Metrics</strong>
        <div class="muted">Status & events</div>
      </div>
      <div style="display:flex;gap:16px;margin-top:12px;align-items:center;">
        <div>
          <div class="muted">Backend Health</div>
          <div id="health" class="badge">—</div>
        </div>
        <div>
          <div class="muted">Tickets</div>
          <div id="metricTickets" class="muted">—</div>
        </div>
        <div>
          <div class="muted">Users</div>
          <div id="metricUsers" class="muted">—</div>
        </div>
      </div>

      <div style="margin-top:12px;">
        <div class="muted">Event Log (recent)</div>
        <pre id="eventLog">No events yet.</pre>
      </div>
    </div>

  </div>
</div>

<script>
const BACKEND = "{{ backend_url }}";
const ADMIN_KEY = "{{ admin_key }}";
let autoRefresh = false;
let eventLog = [];

function pushEvent(msg){
  const ts = new Date().toLocaleString();
  eventLog.unshift(`[${ts}] ${msg}`);
  if(eventLog.length>50) eventLog.pop();
  document.getElementById('eventLog').innerText = eventLog.join('\\n');
}

// Generic fetch helper with admin key if needed
async function beFetch(path, opts={}){
  const url = BACKEND.replace(/\\/$/,'') + path;
  opts.headers = opts.headers || {};
  // attach admin key if present for admin routes
  if(ADMIN_KEY) opts.headers['X-ADMIN-KEY'] = ADMIN_KEY;
  const res = await fetch(url, opts);
  if(!res.ok) {
    pushEvent(`Error ${res.status} on ${path}`);
    return null;
  }
  return res.json();
}

// Refresh all main pieces
async function refreshAll(){
  await Promise.all([loadTickets(), loadUsers(), loadSessions(), loadHealth()]);
  pushEvent('Refreshed all panels');
}

// Load tickets (admin)
async function loadTickets(){
  const data = await beFetch('/tickets');
  const el = document.getElementById('tickets');
  el.innerHTML = '';
  if(!data){ el.innerHTML = '<li class="muted">Unable to load tickets</li>'; return; }
  document.getElementById('ticketCount').innerText = data.length + ' open';
  document.getElementById('metricTickets').innerText = data.length;
  for(const t of data){
    const li = document.createElement('li');
    li.innerHTML = `<strong>#${t.id}</strong> <span class="muted">[${t.status}]</span><div class="muted">${t.subject}</div><div class="muted">${t.created_at}</div>`;
    li.onclick = ()=> loadTicketDetail(t.id);
    el.appendChild(li);
  }
  pushEvent('Loaded tickets');
}

// Load users (admin)
async function loadUsers(){
  const data = await beFetch('/users');
  const el = document.getElementById('users');
  el.innerHTML = '';
  if(!data){ el.innerHTML = '<li class="muted">Unable to load users</li>'; return; }
  document.getElementById('userCount').innerText = data.length;
  document.getElementById('metricUsers').innerText = data.length;
  for(const u of data){
    const li = document.createElement('li');
    li.innerHTML = `<strong>${u.name||'(anonymous)'}</strong><div class="muted">${u.email||''} — last seen ${u.last_seen||'N/A'}</div>`;
    li.onclick = ()=> loadConversationFor(u.session_id);
    el.appendChild(li);
  }
  pushEvent('Loaded users');
}

// Load session list from backend's /leaderboard_json or users (we use users)
async function loadSessions(){
  const users = await beFetch('/users');
  const select = document.getElementById('sessionSelect');
  select.innerHTML = '<option value="">-- select session --</option>';
  if(!users) return;
  for(const u of users){
    const opt = document.createElement('option');
    opt.value = u.session_id;
    opt.textContent = (u.name||u.session_id).slice(0,30) + ' — ' + (u.last_seen||'');
    select.appendChild(opt);
  }
  pushEvent('Loaded session list');
}

// Load conversation for selected session
async function loadConversation(){
  const sid = document.getElementById('sessionSelect').value;
  if(!sid) { document.getElementById('conversation').innerHTML = '<div class="muted">Select a session to view conversation</div>'; return; }
  await loadConversationFor(sid);
}

async function loadConversationFor(sid){
  const rows = await beFetch('/history?sid=' + encodeURIComponent(sid));
  const wrap = document.getElementById('conversation');
  if(!rows){ wrap.innerHTML = '<div class="muted">Unable to load conversation</div>'; return; }
  wrap.innerHTML = '';
  for(const r of rows){
    const d = document.createElement('div');
    d.style.marginBottom = '8px';
    d.innerHTML = `<div style="font-size:13px;color:var(--muted)">${r.created_at}</div>
                   <div style="padding:8px;border-radius:8px;background:rgba(255,255,255,.02);margin-top:6px">
                    <strong>${r.role}</strong>: ${escapeHtml(r.content)}
                   </div>`;
    wrap.appendChild(d);
  }
  pushEvent('Loaded conversation for ' + sid);
}

// Ticket detail via backend tickets list (basic)
async function loadTicketDetail(id){
  const tickets = await beFetch('/tickets');
  const t = (tickets||[]).find(x=>x.id===id);
  if(!t) { alert('Ticket not found'); return; }
  alert(`Ticket #${t.id}\\nSubject: ${t.subject}\\nStatus: ${t.status}\\nCreated: ${t.created_at}`);
}

// KB search & add
async function searchKB(){
  const q = document.getElementById('kbQuery').value.trim();
  if(!q) { alert('Enter a query'); return; }
  const data = await beFetch('/kb?q=' + encodeURIComponent(q));
  const el = document.getElementById('kbResults');
  el.innerHTML = '';
  if(!data || data.length===0) {
    el.innerHTML = '<div class="muted">No KB hits</div>';
    pushEvent('KB search: no results for ' + q);
    return;
  }
  for(const item of data){
    const li = document.createElement('div');
    li.style.padding='8px';
    li.innerHTML = `<strong>${escapeHtml(item.question)}</strong><div class="muted">${escapeHtml(item.answer)}</div>`;
    el.appendChild(li);
  }
  pushEvent('KB search results for: ' + q);
}

async function addKB(){
  const q = document.getElementById('kbQ').value.trim();
  const a = document.getElementById('kbA').value.trim();
  const tags = document.getElementById('kbTags').value.trim();
  if(!q || !a){ document.getElementById('kbMsg').innerText='Question and answer required.'; return; }
  const res = await beFetch('/admin/kb/add', {method:'POST', body: JSON.stringify({question:q,answer:a,tags:tags}), headers: {'Content-Type':'application/json'}});
  if(res && res.status==='added'){ document.getElementById('kbMsg').innerText='Added.'; clearKBForm(); pushEvent('KB article added.'); } else { document.getElementById('kbMsg').innerText='Failed to add.'; }
}

function clearKBForm(){ document.getElementById('kbQ').value=''; document.getElementById('kbA').value=''; document.getElementById('kbTags').value=''; document.getElementById('kbMsg').innerText=''; }

// New ticket flow (quick)
async function openNewTicket(){
  const subj = prompt('Ticket subject (short):','User request');
  if(!subj) return;
  const desc = prompt('Description:','Please describe the issue.');
  if(desc===null) return;
  // create via /escalate
  const res = await beFetch('/escalate', {method:'POST', body: JSON.stringify({subject: subj, description: desc}), headers: {'Content-Type':'application/json'}});
  if(res && res.ticket_id){ alert('Created ticket #' + res.ticket_id); refreshAll(); pushEvent('Created ticket #' + res.ticket_id); }
  else alert('Failed to create ticket');
}

async function loadHealth(){
  const h = await beFetch('/health');
  if(!h){ document.getElementById('health').innerText = 'DOWN'; document.getElementById('health').style.background = '#600'; return; }
  document.getElementById('health').innerText = h.status === 'ok' ? 'OK' : 'WARN';
  document.getElementById('health').style.background = h.status === 'ok' ? '#072a17' : '#604217';
  pushEvent('Health: ' + JSON.stringify(h));
}

function toggleAuto(){
  autoRefresh = !autoRefresh;
  document.getElementById('autoState').innerText = autoRefresh ? 'ON' : 'OFF';
  if(autoRefresh) autoLoop();
}

async function autoLoop(){
  while(autoRefresh){
    await refreshAll();
    await new Promise(r=>setTimeout(r, 7000));
  }
}

function escapeHtml(s){ if(!s) return ''; return s.replace(/[&<>"']/g, (m)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',\"'\":'&#39;'}[m])); }

// initial load
refreshAll();
</script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(TEMPLATE, backend_url=BACKEND_URL, admin_key=ADMIN_KEY)

# Simple proxy endpoints (optional) — helpful if you prefer same-origin calls
@app.route("/api/tickets")
def proxy_tickets():
    # pass through to backend tickets (admin)
    import requests, json
    url = BACKEND_URL.rstrip("/") + "/tickets"
    headers = {}
    if ADMIN_KEY:
        headers['X-ADMIN-KEY'] = ADMIN_KEY
    try:
        r = requests.get(url, headers=headers, timeout=3)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error":"backend_unreachable","detail":str(e)}), 502

if __name__ == "__main__":
    print("Rugike Motors Dashboard running on http://127.0.0.1:5001 — backend:", BACKEND_URL)
    app.run(port=5001, debug=True)
