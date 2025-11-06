"""
Evolve Learning Bot (Flask) - V4
--------------------------------
Enhanced conversational learning assistant.
- Tracks XP, levels, and daily streaks
- Remembers user preferences
- Adds /stats, /leaderboard, /focus commands
- Includes daily challenges for bonus XP
- Detects inactive users
- Syncs messages to evolve_dashboard.py
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
    "Hey {{name}}, what would you like to learn today?",
    "Welcome back {{name}}! Ready to level up your skills?",
    "Hi {{name}}, you can try AI Intro, Python Basics or Data Science.",
    "Good to see you again {{name}}! What topic would you like to study today?",
]

def choose_template_and_fill(name):
    return render_template_string(random.choice(REPLY_TEMPLATES), name=name)

def ai_reply(user_message, name='Learner'):
    try:
        res = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful educational assistant named Evolve Bot."},
                {"role": "user", "content": user_message}
            ]
        )
        return res.choices[0].message.content
    except Exception as e:
        return f"(AI unavailable: {e})"

# ---------------- DAILY CHALLENGE ----------------
DAILY_QUESTIONS = [
    ("What is a variable in programming?", "store data"),
    ("What does HTML stand for?", "hypertext markup language"),
    ("What is the purpose of machine learning?", "make predictions"),
]

def get_daily_question():
    today = date.today().toordinal() % len(DAILY_QUESTIONS)
    return DAILY_QUESTIONS[today]

@app.route('/daily', methods=['GET'])
def daily_question():
    sid = get_session_id()
    q, _ = get_daily_question()
    return jsonify({'question': q})

@app.route('/answer', methods=['POST'])
def answer_question():
    sid = get_session_id()
    user_answer = request.json.get('answer', '').strip().lower()
    _, correct = get_daily_question()
    if correct in user_answer:
        add_xp(sid, 25)
        return jsonify({'result': ' Correct! You earned +25 XP.'})
    else:
        return jsonify({'result': ' Incorrect. Try again tomorrow.'})

# ---------------- FOCUS MODE ----------------
FOCUS_MODE = {}

@app.route('/focus', methods=['POST'])
def toggle_focus():
    sid = get_session_id()
    FOCUS_MODE[sid] = not FOCUS_MODE.get(sid, False)
    state = "enabled" if FOCUS_MODE[sid] else "disabled"
    return jsonify({'reply': f" Focus mode {state}."})

# ---------------- STREAK & LOGGING ----------------
def log_message(sid, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)',
              (sid, role, content, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    send_to_dashboard(sid, content, role)

def send_to_dashboard(sid, text, role):
    try:
        payload = {'sid': sid, 'text': text, 'role': role}
        requests.post(f"{DASHBOARD_URL}/log_message", json=payload, timeout=2)
    except:
        pass

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

# ---------------- COMMAND UTILITIES ----------------
def get_user_stats(sid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM messages WHERE session_id=? AND role="user"', (sid,))
    total_msgs = c.fetchone()[0]
    conn.close()
    streak = calculate_streak(sid)
    user = get_user(sid)
    return f" Stats for {user['name']}:\n- Level: {user['level']}\n- XP: {user['xp']}\n- Streak: {streak} days\n- Messages sent: {total_msgs}"

def get_leaderboard():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT name, level, xp FROM users ORDER BY level DESC, xp DESC LIMIT 5')
    rows = c.fetchall()
    conn.close()
    board = "\n".join([f"{i+1}. {r[0]} (Lvl {r[1]} - {r[2]} XP)" for i, r in enumerate(rows)])
    return "🏆 Top Learners:\n" + board

# ---------------- INACTIVE USERS ----------------
@app.route('/remind_inactive', methods=['GET'])
def remind_inactive():
    days_limit = int(request.args.get('days', 3))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    threshold = (datetime.utcnow() - timedelta(days=days_limit)).isoformat()
    c.execute('SELECT name, last_seen FROM users WHERE last_seen < ?', (threshold,))
    inactive = c.fetchall()
    conn.close()
    return jsonify({'inactive_users': [{'name': n, 'last_seen': l} for n, l in inactive]})

# ---------------- MESSAGE HANDLER ----------------
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

    # Focus mode
    if FOCUS_MODE.get(sid):
        if not detect_task_from_message(text)[0]:
            return jsonify({'reply': "You're in focus mode. Discuss tasks only or use /focus to exit."})

    # Commands
    if text.startswith('/'):
        cmd = text.lower()
        user = get_user(sid)
        if cmd == '/help':
            return jsonify({'reply': "Available commands: /help, /xp, /level, /streak, /reset, /stats, /leaderboard"})
        elif cmd == '/xp':
            return jsonify({'reply': f"You have {user['xp']} XP."})
        elif cmd == '/level':
            return jsonify({'reply': f"You are at level {user['level']}."})
        elif cmd == '/streak':
            streak = calculate_streak(sid)
            return jsonify({'reply': f"You have a {streak}-day learning streak."})
        elif cmd == '/stats':
            return jsonify({'reply': get_user_stats(sid)})
        elif cmd == '/leaderboard':
            return jsonify({'reply': get_leaderboard()})
        elif cmd == '/reset':
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('DELETE FROM progress WHERE session_id=?', (sid,))
            c.execute('UPDATE users SET xp=0, level=1 WHERE session_id=?', (sid,))
            conn.commit()
            conn.close()
            return jsonify({'reply': "Your progress has been reset."})

    # Normal messages
    task_id, task_key = detect_task_from_message(text)
    if task_id:
        success, msg = run_dashboard_task(task_id)
        if success:
            add_xp(sid, 50)
            reply = f" Task **{task_key.title()}** completed. {msg}"
        else:
            reply = f" There was an issue starting {task_key.title()}: {msg}"
    else:
        add_xp(sid, 10)
        reply = ai_reply(text, user_name) if USE_AI else choose_template_and_fill(user_name)

    log_message(sid, 'bot', reply)
    return jsonify({'reply': reply, 'timestamp': datetime.utcnow().isoformat()})

# ---------------- ROOT ----------------
@app.route('/')
def home():
    sid = get_session_id()
    return jsonify({'message': 'Evolve Bot V4 active', 'session': sid})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
