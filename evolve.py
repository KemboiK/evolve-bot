"""
Evolve Learning Bot (Flask) - V2
--------------------------------

Purpose:
- Conversational assistant that helps manage and complete learning tasks.
- Can talk naturally, log all messages, and trigger your local dashboard tasks.
- Now supports AI replies, progress tracking, streaks, and slash commands.

Run this separately from evolve_dashboard.py
"""

from flask import Flask, request, jsonify, session, render_template_string
import re, os, random, sqlite3, requests
from datetime import datetime
from dotenv import load_dotenv

# ---------------------- INIT ----------------------
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('BOT_SECRET_KEY', 'replace-with-secure-secret')
DB_PATH = os.environ.get('BOT_DB', 'evolve_bot.db')

DASHBOARD_URL = "http://127.0.0.1:5001"  # evolve_dashboard.py
USE_AI = os.getenv("USE_AI", "false").lower() == "true"

# ---------------------- OPTIONAL AI ----------------------
try:
    import openai
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if OPENAI_API_KEY:
        openai.api_key = OPENAI_API_KEY
except ImportError:
    USE_AI = False

# ---------------------- TASK MAP ----------------------
TASK_MAP = {
    "ai intro": 1,
    "python basics": 2,
    "data science": 3,
}

# ---------------------- DB SETUP ----------------------
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
    c.execute('''CREATE TABLE IF NOT EXISTS progress (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT,
                    task_name TEXT,
                    progress INTEGER DEFAULT 0,
                    last_updated TEXT
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

def update_progress(session_id, task_name, progress=100):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO progress (session_id, task_name, progress, last_updated) VALUES (?,?,?,?)',
              (session_id, task_name, progress, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

# ---------------------- HELPERS ----------------------
def get_session_id():
    sid = session.get('sid')
    if not sid:
        sid = os.urandom(16).hex()
        session['sid'] = sid
    return sid

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

# ---------------------- REPLIES ----------------------
REPLY_TEMPLATES = [
    "Hi {{name}}, what task are you focusing on today?",
    "Hello {{name}}! Need a hand starting your next lesson?",
    "Hey {{name}}, ready to keep learning? You can try: AI Intro, Python Basics or Data Science Overview.",
    "Nice to see you {{name}}! What topic do you want me to help you with?",
]

SYSTEM_PROMPT = (
    "You are Evolve Bot, a polite and task-oriented learning assistant. "
    "Help users learn, track progress, and complete educational tasks. "
    "Avoid unrelated topics. Focus on productivity and growth."
)

# ---------------------- CORE ----------------------
def detect_task_from_message(text):
    text = text.lower()
    for key, tid in TASK_MAP.items():
        if key in text:
            return tid, key
    return None, None

def run_dashboard_task(task_id):
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

def ai_reply(user_message, user_name='Learner'):
    try:
        res = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        )
        return res.choices[0].message.content
    except Exception as e:
        return f"(AI unavailable: {e})"

def generate_reply(user_message, user_name='Learner'):
    ok, reason = moderate_text(user_message)
    if not ok:
        return {'error': 'blocked', 'reason': reason}

    sid = get_session_id()

    # Slash commands
    if user_message.strip().startswith('/'):
        cmd = user_message.strip().lower()
        if cmd == '/help':
            return {'reply': "Commands: /help, /stats, /reset", 'source': 'system'}
        elif cmd == '/stats':
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM messages WHERE session_id=? AND role="user"', (sid,))
            count = c.fetchone()[0]
            conn.close()
            return {'reply': f"You’ve sent {count} messages so far!", 'source': 'system'}
        elif cmd == '/reset':
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('DELETE FROM progress WHERE session_id=?', (sid,))
            conn.commit()
            conn.close()
            return {'reply': "Your progress has been reset.", 'source': 'system'}

    # Normal flow
    task_id, task_key = detect_task_from_message(user_message)
    if task_id:
        success, msg = run_dashboard_task(task_id)
        if success:
            update_progress(sid, task_key)
            reply = f"✅ I’ve completed **{task_key.title()}** for you! {msg}"
        else:
            reply = f"⚠️ Tried starting **{task_key.title()}**, but there was a problem: {msg}"
    else:
        reply = ai_reply(user_message, user_name) if USE_AI else choose_template_and_fill(user_name)

    return {'reply': reply, 'source': 'ai' if USE_AI else 'template'}

# ---------------------- ROUTES ----------------------
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

@app.route('/progress')
def progress():
    sid = get_session_id()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT task_name, progress, last_updated FROM progress WHERE session_id=?', (sid,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return jsonify({'message': 'No progress yet.'})
    return jsonify([{'task': r[0], 'progress': r[1], 'last_updated': r[2]} for r in rows])

@app.route('/streak')
def streak():
    sid = get_session_id()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT DISTINCT DATE(created_at) FROM messages WHERE session_id=? AND role="user"', (sid,))
    days = sorted([row[0] for row in c.fetchall()])
    conn.close()
    streak = 0
    for i in range(len(days)-1, 0, -1):
        d1 = datetime.fromisoformat(days[i])
        d0 = datetime.fromisoformat(days[i-1])
        if (d1 - d0).days == 1:
            streak += 1
        else:
            break
    return jsonify({'streak_days': streak + 1 if days else 0})

@app.route('/admin/messages')
def admin_messages():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, session_id, role, content, created_at FROM messages ORDER BY id DESC LIMIT 100')
    rows = c.fetchall()
    conn.close()
    return jsonify([{'id':r[0],'session':r[1],'role':r[2],'content':r[3],'time':r[4]} for r in rows])

# ---------------------- MAIN ----------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
