"""
Evolve Learning Bot (Flask) - V5
--------------------------------
Enhanced conversational learning assistant.
New in V5:
- Achievements system (badges) stored in DB and synced to dashboard
- Motivational quotes and /quote command
- Smart XP scaling based on streaks and difficulty
- Admin-only /cleanup_inactive route to prune long-inactive users
- Event log sync for achievements and level-ups
- New command: /achievements
- Minor UX improvements and safer admin protection via ADMIN_KEY env var
"""

from flask import Flask, request, jsonify, session, render_template_string, abort
import re
import os
import random
import sqlite3
import requests
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# ---------------- INIT ----------------
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('BOT_SECRET_KEY', 'replace-with-secure-secret')
DB_PATH = os.environ.get('BOT_DB', 'evolve_bot.db')
DASHBOARD_URL = os.environ.get('DASHBOARD_URL', 'http://127.0.0.1:5001')
USE_AI = os.getenv("USE_AI", "false").lower() == "true"
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'admin-secret-key')  # provide via env for admin endpoints

try:
    import openai
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if OPENAI_API_KEY:
        openai.api_key = OPENAI_API_KEY
except Exception:
    USE_AI = False

# ---------------- DB SETUP ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # messages
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    created_at TEXT
                )''')
    # progress
    c.execute('''CREATE TABLE IF NOT EXISTS progress (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT,
                    task_name TEXT,
                    progress INTEGER DEFAULT 0,
                    last_updated TEXT
                )''')
    # users
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    session_id TEXT PRIMARY KEY,
                    name TEXT,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    focus_area TEXT,
                    last_seen TEXT
                )''')
    # achievements master list
    c.execute('''CREATE TABLE IF NOT EXISTS achievements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE,
                    title TEXT,
                    description TEXT
                )''')
    # user achievements mapping
    c.execute('''CREATE TABLE IF NOT EXISTS user_achievements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    achievement_key TEXT,
                    unlocked_at TEXT,
                    UNIQUE(session_id, achievement_key)
                )''')
    conn.commit()
    conn.close()

init_db()

# ---------------- ACHIEVEMENTS SETUP ----------------
ACHIEVEMENT_DEFINITIONS = {
    "first_xp": ("First Steps", "Earn your first XP."),
    "level_5": ("Rising Star", "Reach level 5."),
    "streak_7": ("Weekly Streak", "Study 7 days in a row."),
    "first_task": ("Task Complete", "Complete your first learning task."),
    "century_xp": ("100 XP Club", "Accumulate 100 total XP.")
}

def seed_achievements():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for key, (title, desc) in ACHIEVEMENT_DEFINITIONS.items():
        c.execute('INSERT OR IGNORE INTO achievements (key, title, description) VALUES (?,?,?)', (key, title, desc))
    conn.commit()
    conn.close()

seed_achievements()

# ---------------- HELPERS ----------------
def get_session_id():
    sid = session.get('sid')
    if not sid:
        sid = os.urandom(16).hex()
        session['sid'] = sid
    return sid

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def get_user(sid):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT name, xp, level, focus_area, last_seen FROM users WHERE session_id=?', (sid,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'name': row[0], 'xp': row[1], 'level': row[2], 'focus': row[3], 'last_seen': row[4]}
    return None

def save_user(sid, name="Learner", focus=None):
    now = datetime.utcnow().isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (session_id, name, focus_area, last_seen) VALUES (?,?,?,?)',
              (sid, name, focus, now))
    c.execute('UPDATE users SET last_seen=? WHERE session_id=?', (now, sid))
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

# ---------------- QUOTES ----------------
QUOTES = [
    "Learning never exhausts the mind. — Leonardo da Vinci",
    "Success is the sum of small efforts repeated day in and day out. — Robert Collier",
    "Never stop learning, because life never stops teaching.",
    "Education is the most powerful weapon you can use to change the world. — Nelson Mandela",
    "Curiosity is the wick in the candle of learning. — William Arthur Ward"
]

# ---------------- STREAK CALC & MESSAGE LOGGING ----------------
def log_message(sid, role, content):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)',
              (sid, role, content, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    # also send to dashboard for analytics
    send_to_dashboard(sid, content, role)

def send_to_dashboard(sid, text, role):
    try:
        payload = {'sid': sid, 'text': text, 'role': role}
        requests.post(f"{DASHBOARD_URL}/log_message", json=payload, timeout=2)
    except Exception:
        # dashboard offline or unreachable - ignore
        pass

def calculate_streak(sid):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT DISTINCT DATE(created_at) FROM messages WHERE session_id=? AND role="user"', (sid,))
    rows = c.fetchall()
    conn.close()
    days = sorted([r[0] for r in rows])
    if not days:
        return 0
    # parse dates and calculate consecutive backward streak
    streak = 1
    for i in range(len(days)-1, 0, -1):
        d_cur = datetime.fromisoformat(days[i])
        d_prev = datetime.fromisoformat(days[i-1])
        if (d_cur - d_prev).days == 1:
            streak += 1
        else:
            break
    return streak

# ---------------- SMART XP & ACHIEVEMENTS ----------------
def add_xp(sid, amount, reason=""):
    """
    Smart XP:
    - Base amount passed in
    - Streak multiplier: +10% per consecutive day up to +50%
    - Trigger achievements on milestones
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT xp, level FROM users WHERE session_id=?', (sid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    xp, level = row
    streak = calculate_streak(sid)
    streak_multiplier = 1.0 + min(streak * 0.10, 0.50)  # up to +50%
    gained = int(amount * streak_multiplier)
    xp += gained

    level_ups = 0
    while xp >= level * 100:
        xp -= level * 100
        level += 1
        level_ups += 1

    now = datetime.utcnow().isoformat()
    c.execute('UPDATE users SET xp=?, level=?, last_seen=? WHERE session_id=?', (xp, level, now, sid))
    conn.commit()
    conn.close()

    # Log event and check achievements
    event_text = f"XP +{gained} ({amount} base, streak x{streak_multiplier:.2f})"
    if reason:
        event_text += f" - {reason}"
    log_message(sid, 'system', event_text)

    if level_ups > 0:
        send_to_dashboard(sid, f"level_up:{level}", "system")
    check_and_unlock_achievements(sid)

def get_total_xp_for_user(sid):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT xp, level FROM users WHERE session_id=?', (sid,))
    row = c.fetchone()
    conn.close()
    if not row:
        return 0
    xp, level = row
    # estimate total xp including previous levels (approx)
    # total = xp + sum_{i=1 to level-1} (i * 100)
    total = xp + sum(i * 100 for i in range(1, level))
    return total

def check_and_unlock_achievements(sid):
    """
    Evaluate achievement rules for user and unlock any that apply.
    """
    user = get_user(sid)
    if not user:
        return
    unlocked = []
    total_xp = get_total_xp_for_user(sid)
    streak = calculate_streak(sid)
    conn = get_db_connection()
    c = conn.cursor()

    # simple rules
    rules = [
        ("first_xp", lambda u: total_xp >= 1),
        ("century_xp", lambda u: total_xp >= 100),
        ("level_5", lambda u: u['level'] >= 5),
        ("streak_7", lambda u: streak >= 7),
    ]

    # first_task: check messages for a dashboard-run success or progress entry
    c.execute('SELECT COUNT(*) FROM progress WHERE session_id=?', (sid,))
    progress_count = c.fetchone()[0]
    if progress_count > 0:
        rules.append(("first_task", lambda u: True))

    for key, rule in rules:
        try:
            c.execute('SELECT 1 FROM user_achievements WHERE session_id=? AND achievement_key=?', (sid, key))
            if c.fetchone():
                continue  # already unlocked
            if rule(user):
                now = datetime.utcnow().isoformat()
                c.execute('INSERT OR IGNORE INTO user_achievements (session_id, achievement_key, unlocked_at) VALUES (?,?,?)',
                          (sid, key, now))
                conn.commit()
                unlocked.append(key)
                # notify dashboard about achievement
                send_to_dashboard(sid, f"achievement_unlocked:{key}", "system")
                log_message(sid, 'system', f"Achievement unlocked: {key}")
        except Exception:
            continue
    conn.close()
    return unlocked

def get_user_achievements(sid):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT achievement_key, unlocked_at FROM user_achievements WHERE session_id=?', (sid,))
    rows = c.fetchall()
    conn.close()
    result = []
    for key, at in rows:
        title = ACHIEVEMENT_DEFINITIONS.get(key, (key, ""))[0]
        result.append({'key': key, 'title': title, 'unlocked_at': at})
    return result

# ---------------- DAILY CHALLENGE ----------------
DAILY_QUESTIONS = [
    ("What is a variable in programming?", "store"),
    ("What does HTML stand for?", "hypertext"),
    ("What is the purpose of machine learning?", "predic"),
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
    user_answer = (request.json or {}).get('answer', '').strip().lower()
    _, correct = get_daily_question()
    if correct in user_answer:
        add_xp(sid, 25, reason="daily_challenge_correct")
        return jsonify({'result': 'Correct! You earned +25 XP.'})
    else:
        return jsonify({'result': 'Incorrect. Try again tomorrow.'})

# ---------------- FOCUS MODE ----------------
FOCUS_MODE = {}

@app.route('/focus', methods=['POST'])
def toggle_focus():
    sid = get_session_id()
    FOCUS_MODE[sid] = not FOCUS_MODE.get(sid, False)
    state = "enabled" if FOCUS_MODE[sid] else "disabled"
    return jsonify({'reply': f"Focus mode {state}."})

# ---------------- COMMAND UTILITIES ----------------
def get_user_stats(sid):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM messages WHERE session_id=? AND role="user"', (sid,))
    total_msgs = c.fetchone()[0]
    conn.close()
    streak = calculate_streak(sid)
    user = get_user(sid)
    return f"Stats for {user['name']}:\n- Level: {user['level']}\n- XP: {user['xp']}\n- Streak: {streak} days\n- Messages sent: {total_msgs}"

def get_leaderboard():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT name, level, xp FROM users ORDER BY level DESC, xp DESC LIMIT 10')
    rows = c.fetchall()
    conn.close()
    board = "\n".join([f"{i+1}. {r[0]} (Lvl {r[1]} - {r[2]} XP)" for i, r in enumerate(rows)])
    return "🏆 Top Learners:\n" + board

# ---------------- INACTIVE USERS ----------------
@app.route('/remind_inactive', methods=['GET'])
def remind_inactive():
    days_limit = int(request.args.get('days', 3))
    conn = get_db_connection()
    c = conn.cursor()
    threshold = (datetime.utcnow() - timedelta(days=days_limit)).isoformat()
    c.execute('SELECT session_id, name, last_seen FROM users WHERE last_seen < ?', (threshold,))
    inactive = c.fetchall()
    conn.close()
    return jsonify({'inactive_users': [{'session_id': s, 'name': n, 'last_seen': l} for s, n, l in inactive]})

@app.route('/cleanup_inactive', methods=['POST'])
def cleanup_inactive():
    # Admin-protected: require ADMIN_KEY in header or query param
    provided = request.headers.get('X-ADMIN-KEY') or request.args.get('admin_key')
    if provided != ADMIN_KEY:
        return jsonify({'error': 'unauthorized'}), 401
    days_limit = int(request.json.get('days', 30))
    threshold = (datetime.utcnow() - timedelta(days=days_limit)).isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    # delete messages, progress, user_achievements, and user record
    c.execute('SELECT session_id FROM users WHERE last_seen < ?', (threshold,))
    old_users = [r[0] for r in c.fetchall()]
    for sid in old_users:
        c.execute('DELETE FROM messages WHERE session_id=?', (sid,))
        c.execute('DELETE FROM progress WHERE session_id=?', (sid,))
        c.execute('DELETE FROM user_achievements WHERE session_id=?', (sid,))
        c.execute('DELETE FROM users WHERE session_id=?', (sid,))
    conn.commit()
    conn.close()
    return jsonify({'deleted_users': len(old_users)})

# ---------------- MESSAGE HANDLER ----------------
@app.route('/message', methods=['POST'])
def message():
    data = request.json or {}
    text = (data.get('text') or '').strip()
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
            return jsonify({'reply': "Available commands: /help, /xp, /level, /streak, /reset, /stats, /leaderboard, /achievements, /quote"})
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
        elif cmd == '/achievements':
            ach = get_user_achievements(sid)
            if not ach:
                return jsonify({'reply': "No achievements unlocked yet. Keep learning!"})
            lines = [f"- {a['title']} (unlocked at {a['unlocked_at']})" for a in ach]
            return jsonify({'reply': "Your achievements:\n" + "\n".join(lines)})
        elif cmd == '/quote':
            return jsonify({'reply': random.choice(QUOTES)})
        elif cmd == '/reset':
            conn = get_db_connection()
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
            # scale XP by task difficulty (simple heuristic: quiz=40, video=30, article=20)
            difficulty_lookup = {1: 30, 2: 40, 3: 20}
            base = difficulty_lookup.get(task_id, 25)
            add_xp(sid, base, reason=f"task:{task_key}")
            # mark progress (simple)
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('INSERT INTO progress (session_id, task_name, progress, last_updated) VALUES (?,?,?,?)',
                      (sid, task_key, 100, datetime.utcnow().isoformat()))
            conn.commit()
            conn.close()
            reply = f"Task {task_key.title()} completed. {msg}"
        else:
            reply = f"There was an issue starting {task_key.title()}: {msg}"
    else:
        # casual interaction earns small XP
        add_xp(sid, 10, reason="message_interaction")
        reply = ai_reply(text, user_name) if USE_AI else choose_template_and_fill(user_name)

    log_message(sid, 'bot', reply)
    return jsonify({'reply': reply, 'timestamp': datetime.utcnow().isoformat()})

# ---------------- ROOT ----------------
@app.route('/')
def home():
    sid = get_session_id()
    return jsonify({'message': 'Evolve Bot V5 active', 'session': sid})

# ---------------- ADMIN: quick user list ----------------
@app.route('/users', methods=['GET'])
def list_users():
    provided = request.headers.get('X-ADMIN-KEY') or request.args.get('admin_key')
    if provided != ADMIN_KEY:
        return jsonify({'error': 'unauthorized'}), 401
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT session_id, name, xp, level, last_seen FROM users ORDER BY last_seen DESC')
    rows = c.fetchall()
    conn.close()
    return jsonify([{'session_id': r[0], 'name': r[1], 'xp': r[2], 'level': r[3], 'last_seen': r[4]} for r in rows])

# ---------------- MAIN ----------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
