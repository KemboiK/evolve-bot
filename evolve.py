"""
Evolve Learning Bot (Flask) - V3
--------------------------------
Enhanced conversational learning assistant.
- Tracks XP, levels, and daily streaks
- Remembers user preferences
- Uses slash commands for stats and reset
- Connects with evolve_dashboard.py for local tasks
"""

from flask import Flask, request, jsonify, session, render_template_string
import re, os, random, sqlite3, requests
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# ---------------- INIT ----------------
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('BOT_SECRET_KEY', 'replace-with-secure-secret')
DB_PATH = os.environ.get('BOT_DB', 'evolve_bot.db')

DASHBOARD_URL = "http://127.0.0.1:5001"
USE_AI = os.getenv("USE_AI", "false").lower() == "true"

try:
    import openai
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if OPENAI_API_KEY:
        openai.api_key = OPENAI_API_KEY
except ImportError:
    USE_AI = False

# ---------------- DB SETUP ----------------
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
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    session_id TEXT PRIMARY KEY,
                    name TEXT,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    focus_area TEXT,
                    last_seen TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

# ---------------- HELPERS ----------------
def get_session_id():
    sid = session.get('sid')
    if not sid:
        sid = os.urandom(16).hex()
        session['sid'] = sid
    return sid

def get_user(sid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT name, xp, level, focus_area, last_seen FROM users WHERE session_id=?', (sid,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'name': row[0], 'xp': row[1], 'level': row[2], 'focus': row[3], 'last_seen': row[4]}
    return None

def save_user(sid, name="Learner", focus=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (session_id, name, focus_area, last_seen) VALUES (?,?,?,?)',
              (sid, name, focus, datetime.utcnow().isoformat()))
    c.execute('UPDATE users SET last_seen=? WHERE session_id=?', (datetime.utcnow().isoformat(), sid))
    conn.commit()
    conn.close()

def add_xp(sid, amount):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT xp, level FROM users WHERE session_id=?', (sid,))
    row = c.fetchone()
    if row:
        xp, level = row
        xp += amount
        if xp >= level * 100:
            level += 1
            xp = 0
        c.execute('UPDATE users SET xp=?, level=?, last_seen=? WHERE session_id=?',
                  (xp, level, datetime.utcnow().isoformat(), sid))
    conn.commit()
    conn.close()

# ---------------- MODERATION ----------------
ILLEGAL_PATTERNS = [r"\bchild\b", r"\bunderage\b"]
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

# ---------------- TASK MAP ----------------
TASK_MAP = {"ai intro": 1, "python basics": 2, "data science": 3}

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
            return True, res.json().get("message", "Task done.")
        return False, "Dashboard error."
    except Exception as e:
        return False, str(e)

# ---------------- AI OR TEMPLATE ----------------
REPLY_TEMPLATES = [
    "Hola {{name}}, ¿en qué tarea quieres trabajar hoy?",
    "¡Bienvenido de nuevo {{name}}! ¿Listo para aprender algo nuevo?",
    "Hey {{name}}, puedes probar con AI Intro, Python Basics o Data Science.",
    "¡Qué gusto verte {{name}}! ¿Qué tema te gustaría estudiar hoy?",
]

def choose_template_and_fill(name):
    return render_template_string(random.choice(REPLY_TEMPLATES), name=name)

def ai_reply(user_message, name='Learner'):
    try:
        res = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un asistente educativo llamado Evolve Bot."},
                {"role": "user", "content": user_message}
            ]
        )
        return res.choices[0].message.content
    except Exception as e:
        return f"(AI no disponible: {e})"

# ---------------- MESSAGE FLOW ----------------
@app.route('/message', methods=['POST'])
def message():
    data = request.json or {}
    text = data.get('text', '').strip()
    user_name = data.get('name', 'Learner')
    sid = get_session_id()

    if not text:
        return jsonify({'error': 'empty_message'}), 400

    save_user(sid, user_name)

    ok, reason = moderate_text(text)
    if not ok:
        return jsonify({'error': reason}), 403

    # Commands
    if text.startswith('/'):
        cmd = text.lower()
        user = get_user(sid)
        if cmd == '/help':
            return jsonify({'reply': "Comandos disponibles: /help, /xp, /level, /streak, /reset"})
        elif cmd == '/xp':
            return jsonify({'reply': f"Tienes {user['xp']} XP acumulados."})
        elif cmd == '/level':
            return jsonify({'reply': f"Estás en el nivel {user['level']}."})
        elif cmd == '/streak':
            streak = calculate_streak(sid)
            return jsonify({'reply': f"Llevas una racha de {streak} días seguidos aprendiendo."})
        elif cmd == '/reset':
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('DELETE FROM progress WHERE session_id=?', (sid,))
            c.execute('UPDATE users SET xp=0, level=1 WHERE session_id=?', (sid,))
            conn.commit()
            conn.close()
            return jsonify({'reply': "Tu progreso ha sido reiniciado."})

    # Normal messages
    task_id, task_key = detect_task_from_message(text)
    if task_id:
        success, msg = run_dashboard_task(task_id)
        if success:
            add_xp(sid, 50)
            reply = f"✅ Tarea **{task_key.title()}** completada. {msg}"
        else:
            reply = f"⚠️ Hubo un problema al iniciar {task_key.title()}: {msg}"
    else:
        add_xp(sid, 10)
        reply = ai_reply(text, user_name) if USE_AI else choose_template_and_fill(user_name)

    log_message(sid, 'bot', reply)
    return jsonify({'reply': reply, 'timestamp': datetime.utcnow().isoformat()})

# ---------------- STREAK & LOGGING ----------------
def log_message(sid, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)',
              (sid, role, content, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def calculate_streak(sid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT DISTINCT DATE(created_at) FROM messages WHERE session_id=? AND role="user"', (sid,))
    days = sorted([row[0] for row in c.fetchall()])
    conn.close()
    if not days:
        return 0
    streak = 1
    for i in range(len(days)-1, 0, -1):
        if (datetime.fromisoformat(days[i]) - datetime.fromisoformat(days[i-1])).days == 1:
            streak += 1
        else:
            break
    return streak

@app.route('/')
def home():
    sid = get_session_id()
    return jsonify({'message': 'Evolve Bot V3 active', 'session': sid})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
