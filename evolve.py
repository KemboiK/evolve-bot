"""
Evolve Learning Bot (Flask)
---------------------------

Purpose:
- Conversational assistant that helps manage and complete learning tasks.
- Can talk naturally, log all messages, and trigger your local dashboard tasks.
- Modular, safe, and extendable with LLM or external APIs.

How it works:
- Listens to chat input from the user.
- Detects keywords for tasks like “Python Basics” or “AI Intro”.
- Calls the dashboard (running separately on localhost) to simulate the task.
- Replies with confirmation and encouragement messages.

Run this separately from evolve_dashboard.py
"""

from flask import Flask, request, jsonify, session, render_template_string
from functools import wraps
import re
import os
import random
import sqlite3
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('BOT_SECRET_KEY', 'replace-with-secure-secret')
DB_PATH = os.environ.get('BOT_DB', 'evolve_bot.db')

# ---------------------- CONFIG ----------------------
DASHBOARD_URL = "http://127.0.0.1:5001"  # URL of evolve_dashboard.py

# Known tasks to detect by name or keyword
TASK_MAP = {
    "ai intro": 1,
    "python basics": 2,
    "data science": 3,
}

# ---------------------- Database ----------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    created_at TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

def log_message(session_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)',
              (session_id, role, content, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

# ---------------------- Session Helpers ----------------------
def get_session_id():
    sid = session.get('sid')
    if not sid:
        sid = os.urandom(16).hex()
        session['sid'] = sid
    return sid

# ---------------------- Moderation ----------------------
ILLEGAL_PATTERNS = [r"\bchild\b", r"\bunderage\b", r"\bteen\b"]
PROHIBITED_PATTERNS = [r"\bkill\b", r"\bterror\b", r"\bexplosive\b"]

def moderate_text(text):
    lowered = text.lower()
    for p in ILLEGAL_PATTERNS:
        if re.search(p, lowered):
            return False, 'content referencing minors detected'
    for p in PROHIBITED_PATTERNS:
        if re.search(p, lowered):
            return False, 'potentially violent/illegal content detected'
    return True, ''

# ---------------------- Reply Templates ----------------------
REPLY_TEMPLATES = [
    "Hi {{name}}, what task are you focusing on today?",
    "Hello {{name}}! Need a hand starting your next lesson?",
    "Hey {{name}}, ready to keep learning? You can try: AI Intro, Python Basics, or Data Science Overview.",
    "Nice to see you {{name}}! What topic do you want me to help you with?",
]

SYSTEM_PROMPT = (
    "You are Evolve Bot — a smart, polite, task-oriented educational assistant. "
    "You help users learn, track progress, and complete educational tasks. "
    "Avoid personal or unrelated topics. Focus on productivity and growth."
)

# ---------------------- Core Logic ----------------------
def detect_task_from_message(text):
    text = text.lower()
    for key, tid in TASK_MAP.items():
        if key in text:
            return tid, key
    return None, None

def run_dashboard_task(task_id):
    """Call evolve_dashboard.py to simulate running a task."""
    try:
        res = requests.get(f"{DASHBOARD_URL}/run_task/{task_id}", timeout=5)
        if res.status_code == 200:
            data = res.json()
            return True, data.get("message", "Task completed.")
        else:
            return False, "Dashboard did not respond properly."
    except Exception as e:
        return False, f"Dashboard not reachable ({e})."

def choose_template_and_fill(user_name='Learner'):
    t = random.choice(REPLY_TEMPLATES)
    return render_template_string(t, name=user_name)

def generate_reply(user_message, user_name='Learner'):
    ok, reason = moderate_text(user_message)
    if not ok:
        return {'error': 'blocked', 'reason': reason}

    task_id, task_key = detect_task_from_message(user_message)
    if task_id:
        success, msg = run_dashboard_task(task_id)
        if success:
            reply = f"✅ I’ve just completed the **{task_key.title()}** task for you! {msg}"
        else:
            reply = f"⚠️ I tried to start the **{task_key.title()}** task, but there was a problem: {msg}"
    else:
        reply = choose_template_and_fill(user_name)

    return {'reply': reply, 'source': 'template'}

# ---------------------- Routes ----------------------
@app.route('/')
def home():
    sid = get_session_id()
    return jsonify({'message': 'Evolve Learning Bot active', 'session': sid})

@app.route('/message', methods=['POST'])
def message():
    data = request.json or {}
    text = data.get('text', '')
    user_name = data.get('name', 'Learner')
    sid = get_session_id()

    if not text.strip():
        return jsonify({'error': 'empty_message'}), 400

    log_message(sid, 'user', text)
    result = generate_reply(text, user_name)

    if 'error' in result:
        log_message(sid, 'system', f'blocked_reason:{result.get("reason")}')
        return jsonify({'error': result.get('reason')}), 403

    reply_text = result['reply']
    log_message(sid, 'bot', reply_text)
    return jsonify({'reply': reply_text, 'source': result.get('source', 'template')})

@app.route('/admin/messages')
def admin_messages():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, session_id, role, content, created_at FROM messages ORDER BY id DESC LIMIT 100')
    rows = c.fetchall()
    conn.close()
    return jsonify([{'id':r[0],'session':r[1],'role':r[2],'content':r[3],'time':r[4]} for r in rows])

# ---------------------- Main ----------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
