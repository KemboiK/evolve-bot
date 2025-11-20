# evolve_dashboard.py
"""
Rugike Motors Admin Dashboard (Flask)
---------------------------------------------------
Admin console for Rugike Motors Support Bot with gamification.

Run:
  BACKEND_URL=http://127.0.0.1:5000 ADMIN_KEY=admin-secret-key python evolve_dashboard.py
"""
from flask import Flask, render_template_string, jsonify, request
import os

app = Flask(__name__)
app.secret_key = os.environ.get('BOT_SECRET_KEY', 'local-secret')

# Backend support-bot URL (evolve.py)
BACKEND_URL = os.environ.get('BACKEND_URL', 'http://127.0.0.1:5000')
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'admin-secret-key')

TEMPLATE = """ 
<!-- Keep your existing HTML/CSS as before, but add sections for leaderboard and achievements -->
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Rugike Motors — Support Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
/* ... keep your existing styles ... */
</style>
</head>
<body>
<header>
  <h1>Rugike Motors — Support Dashboard</h1>
  <div class="muted">Backend: <span id="backendUrl">{{ backend_url }}</span></div>
</header>

<div class="grid">
  <!-- Left column: quick controls + tickets + leaderboard -->
  <div>
    <div class="card">
      <div class="section-title"><strong>Quick Actions</strong><div class="muted">Admin</div></div>
      <div class="controls">
        <button onclick="refreshAll()">Refresh All</button>
        <button class="ghost" onclick="toggleAuto()">Auto: <span id="autoState">OFF</span></button>
        <button class="ghost" onclick="openNewTicket()">New Ticket</button>
      </div>
    </div>

    <div class="card" style="margin-top:14px;">
      <div class="section-title"><strong>Open Tickets</strong><span class="muted" id="ticketCount">—</span></div>
      <ul id="tickets" class="list"></ul>
    </div>

    <div class="card" style="margin-top:14px;">
      <div class="section-title"><strong>Leaderboard (Top 20)</strong></div>
      <ul id="leaderboard" class="list"></ul>
    </div>

    <div class="card" style="margin-top:14px;">
      <div class="section-title"><strong>Achievements</strong></div>
      <ul id="achievements" class="list"></ul>
    </div>
  </div>

  <!-- Right column: conversation, KB, health -->
  <div>
    <div class="card">
      <div class="section-title"><strong>Recent Conversations</strong></div>
      <select id="sessionSelect" style="width:320px" onchange="loadConversation()">
        <option value="">-- select session --</option>
      </select>
      <div id="conversation" style="max-height:360px;overflow:auto;margin-top:12px;"></div>
    </div>

    <div class="card" style="margin-top:14px;">
      <div class="section-title"><strong>Knowledge Base</strong></div>
      <input id="kbQuery" placeholder="Search KB..." />
      <button onclick="searchKB()">Search</button>
      <div id="kbResults" class="list" style="max-height:180px;margin-top:8px;"></div>
      <input id="kbQ" placeholder="Question" />
      <textarea id="kbA" rows="4" placeholder="Answer"></textarea>
      <input id="kbTags" placeholder="tags,comma,separated" />
      <button onclick="addKB()">Add KB</button>
      <div id="kbMsg" class="muted" style="margin-top:6px;"></div>
    </div>

    <div class="card" style="margin-top:14px;">
      <div class="section-title"><strong>System / Metrics</strong></div>
      <div id="health" class="badge">—</div>
      <div id="metricTickets" class="muted">Tickets: —</div>
      <div id="metricUsers" class="muted">Users: —</div>
      <pre id="eventLog">No events yet.</pre>
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

async function beFetch(path, opts={}) {
  const url = BACKEND.replace(/\\/$/,'') + path;
  opts.headers = opts.headers || {};
  if(ADMIN_KEY) opts.headers['X-ADMIN-KEY'] = ADMIN_KEY;
  try {
    const res = await fetch(url, opts);
    if(!res.ok){ pushEvent(`Error ${res.status} on ${path}`); return null; }
    return await res.json();
  } catch(e){ pushEvent(`Fetch error on ${path}: ${e}`); return null; }
}

// Refresh all panels
async function refreshAll(){
  await Promise.all([loadTickets(), loadLeaderboard(), loadUsers(), loadSessions(), loadHealth()]);
  pushEvent('Refreshed all panels');
}

// Load tickets
async function loadTickets(){
  const data = await beFetch('/tickets');
  const el = document.getElementById('tickets'); el.innerHTML = '';
  if(!data){ el.innerHTML='<li class="muted">Unable to load tickets</li>'; return; }
  document.getElementById('ticketCount').innerText = data.length + ' open';
  document.getElementById('metricTickets').innerText = 'Tickets: ' + data.length;
  for(const t of data){
    const li = document.createElement('li');
    li.innerHTML = `<strong>#${t.id}</strong> [${t.status}] ${t.subject}`;
    li.onclick=()=>alert(`Ticket #${t.id}\n${t.subject}`);
    el.appendChild(li);
  }
}

// Leaderboard
async function loadLeaderboard(){
  const data = await beFetch('/leaderboard');
  const el = document.getElementById('leaderboard'); el.innerHTML='';
  if(!data){ el.innerHTML='<li class="muted">Unable to load leaderboard</li>'; return; }
  for(const u of data.slice(0,20)){
    const li = document.createElement('li');
    li.innerHTML=`<strong>${u.name||u.session_id}</strong> - Level ${u.level} (${u.xp} XP)`;
    el.appendChild(li);
  }
}

// Load users (for conversation selection)
async function loadUsers(){
  const data = await beFetch('/users');
  if(!data) return;
  const select = document.getElementById('sessionSelect'); select.innerHTML='<option value="">-- select session --</option>';
  for(const u of data){
    const opt = document.createElement('option'); opt.value=u.session_id; opt.textContent=(u.name||u.session_id).slice(0,30)+' — '+(u.last_seen||'');
    select.appendChild(opt);
  }
  // Load achievements panel
  const achEl = document.getElementById('achievements'); achEl.innerHTML='';
  for(const u of data.slice(0,10)){ // top 10 for brevity
    const li = document.createElement('li'); li.innerText=`${u.name||u.session_id}: ${u.achievements||'—'}`;
    achEl.appendChild(li);
  }
}

// Sessions dropdown
async function loadSessions(){ await loadUsers(); }

// Conversations
async function loadConversation(){
  const sid = document.getElementById('sessionSelect').value;
  if(!sid) return;
  const rows = await beFetch('/history?sid=' + encodeURIComponent(sid));
  const wrap = document.getElementById('conversation'); wrap.innerHTML='';
  if(!rows){ wrap.innerHTML='<div class="muted">Unable to load conversation</div>'; return; }
  for(const r of rows){
    const d = document.createElement('div'); d.style.marginBottom='8px';
    d.innerHTML=`<div style="font-size:13px;color:#9aa6b2">${r.created_at}</div>
                 <div style="padding:8px;background:rgba(255,255,255,.02);border-radius:6px"><strong>${r.role}</strong>: ${r.content}</div>`;
    wrap.appendChild(d);
  }
  pushEvent('Loaded conversation for ' + sid);
}

// KB
async function searchKB(){
  const q = document.getElementById('kbQuery').value.trim(); if(!q) return;
  const data = await beFetch('/kb?q=' + encodeURIComponent(q));
  const el = document.getElementById('kbResults'); el.innerHTML='';
  if(!data || data.length===0){ el.innerHTML='<div class="muted">No KB hits</div>'; return; }
  for(const item of data){
    const div = document.createElement('div'); div.innerHTML=`<strong>${item.question}</strong><div>${item.answer}</div>`; el.appendChild(div);
  }
  pushEvent('KB search: ' + q);
}

async function addKB(){
  const q=document.getElementById('kbQ').value.trim();
  const a=document.getElementById('kbA').value.trim();
  const tags=document.getElementById('kbTags').value.trim();
  if(!q||!a){ document.getElementById('kbMsg').innerText='Q&A required'; return; }
  const res = await beFetch('/admin/kb/add',{method:'POST',body:JSON.stringify({question:q,answer:a,tags:tags}),headers:{'Content-Type':'application/json'}});
  if(res && res.status==='added'){ document.getElementById('kbMsg').innerText='Added'; pushEvent('KB article added'); } else { document.getElementById('kbMsg').innerText='Failed to add'; }
}

async function loadHealth(){
  const h = await beFetch('/health'); const el=document.getElementById('health');
  if(!h){ el.innerText='DOWN'; el.style.background='#600'; return; }
  el.innerText = h.status==='ok'?'OK':'WARN'; el.style.background = h.status==='ok'?'#072a17':'#604217';
  pushEvent('Health checked');
}

function toggleAuto(){ autoRefresh=!autoRefresh; document.getElementById('autoState').innerText=autoRefresh?'ON':'OFF'; if(autoRefresh) autoLoop(); }
async function autoLoop(){ while(autoRefresh){ await refreshAll(); await new Promise(r=>setTimeout(r,7000)); } }

// Initial load
refreshAll();
</script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(TEMPLATE, backend_url=BACKEND_URL, admin_key=ADMIN_KEY)

if __name__=="__main__":
    print("Dashboard running on http://127.0.0.1:5001 — backend:", BACKEND_URL)
    app.run(port=5001, debug=True)
