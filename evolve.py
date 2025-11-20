"""
Rugike Motors Evolve Bot + Dashboard (Flask)
--------------------------------------------------------------
Purpose: AI-powered support bot with gamification for Rugike Motors.
- Handles buyer & seller inquiries
- Tracks XP, levels, achievements
- Motivational quotes
- Daily reward system
- Logs conversations and creates tickets
- Optional OpenAI fallback (if OPENAI_API_KEY present)
- Syncs events to dashboard via DASHBOARD_URL
"""

from flask import Flask, request, jsonify, session, render_template_string
import os, sqlite3, re, random, requests, time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# ---------------- INIT ----------------
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('BOT_SECRET_KEY', 'replace-with-secure-secret')

DB_PATH = os.environ.get('BOT_DB', 'rugike_support.db')
DASHBOARD_URL = os.environ.get('DASHBOARD_URL', 'http://127.0.0.1:5001')
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'admin-secret-key')
USE_AI = bool(os.getenv('OPENAI_API_KEY'))

# Optional OpenAI import
try:
    if USE_AI:
        import openai
        openai.api_key = os.getenv('OPENAI_API_KEY')
except Exception:
    USE_AI = False

# ---------------- DB SETUP ----------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # messages log
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    created_at TEXT
                 )''')
    # users
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    session_id TEXT PRIMARY KEY,
                    name TEXT,
                    email TEXT,
                    last_seen TEXT,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    achievements TEXT DEFAULT ''
                 )''')
    # tickets
    c.execute('''CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    subject TEXT,
                    description TEXT,
                    status TEXT,
                    created_at TEXT,
                    updated_at TEXT
                 )''')
    # knowledge base
    c.execute('''CREATE TABLE IF NOT EXISTS kb (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT,
                    answer TEXT,
                    tags TEXT
                 )''')
    conn.commit()
    conn.close()

init_db()

# ---------------- KB SEED ----------------
def seed_kb():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM kb')
    if c.fetchone()[0] == 0:
        kb_items = [
            ("How do I list a car for sale?", "Go to Sellers > Add Listing and fill required fields. Listings reviewed within 24h.", "listing,sellers"),
            ("How do I contact a seller?", "Open the car listing and click 'Contact Seller' to send a message or request a call.", "contact,transactions"),
            ("What are seller requirements?", "Sellers must verify ID and provide vehicle ownership documents.", "sellers,policy,verification"),
            ("How do I pay for a car?", "We support bank transfer and escrow payments.", "payments,checkout"),
            ("How do I report a problem with a listing?", "Use 'Report Listing' or message support to open a ticket.", "report,listing,issues")
        ]
        c.executemany('INSERT INTO kb (question, answer, tags) VALUES (?,?,?)', kb_items)
        conn.commit()
    conn.close()

seed_kb()

# ---------------- SESSIONS ----------------
def get_session_id():
    sid = session.get('sid')
    if not sid:
        sid = os.urandom(16).hex()
        session['sid'] = sid
    return sid

def save_user_profile(sid, name=None, email=None):
    now = datetime.utcnow().isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (session_id, name, email, last_seen) VALUES (?,?,?,?)', (sid, name, email, now))
    c.execute('UPDATE users SET last_seen=? WHERE session_id=?', (now, sid))
    conn.commit()
    conn.close()

# ---------------- MODERATION ----------------
PROHIBITED_PATTERNS = [r"\bterror\b", r"\bexplosive\b", r"\bkill\b"]
def moderate_text(text):
    lowered = text.lower()
    for p in PROHIBITED_PATTERNS:
        if re.search(p, lowered):
            return False, "Potentially violent or illegal content detected."
    return True, ""

# ---------------- INTENT DETECTION ----------------
INTENTS = {
    'availability': ['available', 'is .* available', 'still available', 'is it available'],
    'post_listing': ['list a car', 'sell my car', 'post listing', 'how to sell'],
    'contact_seller': ['contact seller', 'message seller', 'call seller', 'reach seller'],
    'pricing': ['price', 'cost', 'how much', 'asking price'],
    'payment': ['pay', 'payment', 'checkout', 'escrow', 'bank transfer'],
    'report_issue': ['report', 'fraud', 'scam', 'problem with listing', 'not working'],
    'hours': ['opening hours', 'hours', 'when are you open'],
    'help': ['help', 'support', 'customer service', 'questions']
}

def detect_intent(text):
    text_l = text.lower()
    for intent, patterns in INTENTS.items():
        for p in patterns:
            try:
                if re.search(p, text_l):
                    return intent
            except re.error:
                if p in text_l:
                    return intent
    if '?' in text:
        return 'help'
    return 'unknown'

# ---------------- KB SEARCH ----------------
def search_kb(query, limit=3):
    conn = get_db_connection()
    c = conn.cursor()
    q = f"%{query.lower()}%"
    c.execute('SELECT question,answer FROM kb WHERE LOWER(question) LIKE ? OR LOWER(tags) LIKE ? LIMIT ?', (q, q, limit))
    rows = c.fetchall()
    conn.close()
    return [{"question": r[0], "answer": r[1]} for r in rows]

# ---------------- AI FALLBACK ----------------
def ai_fallback(user_message):
    if not USE_AI:
        return "Sorry — I couldn't find an exact answer. Type 'escalate' to open a ticket."
    try:
        prompt = f"You are a helpful support assistant for Rugike Motors.\nUser: {user_message}\nAnswer concisely."
        res = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "You are Rugike Motors customer support assistant."},
                      {"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.2
        )
        return res.choices[0].message.content.strip()
    except Exception:
        return "Sorry — AI unavailable. Type 'escalate' to open a ticket."

# ---------------- LOGGING & DASHBOARD SYNC ----------------
def log_message(session_id, role, content):
    now = datetime.utcnow().isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)',
              (session_id, role, content, now))
    conn.commit()
    conn.close()
    try:
        requests.post(f"{DASHBOARD_URL}/log_message", json={'sid': session_id, 'role': role, 'content': content}, timeout=1.5)
    except Exception:
        pass

# ---------------- TICKET MANAGEMENT ----------------
def create_ticket(session_id, subject, description):
    now = datetime.utcnow().isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO tickets (session_id, subject, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)',
              (session_id, subject, description, 'open', now, now))
    ticket_id = c.lastrowid
    conn.commit()
    conn.close()
    try:
        requests.post(f"{DASHBOARD_URL}/log_message", json={'sid': session_id, 'role': 'system', 'content': f"ticket_created:{ticket_id}"}, timeout=1.5)
    except Exception:
        pass
    return ticket_id

# ---------------- GAMIFICATION ----------------
QUOTES = [
    "“Learning never exhausts the mind.” — Leonardo da Vinci",
    "“Success is the sum of small efforts repeated day in and day out.” — Robert Collier",
    "“Never stop learning, because life never stops teaching.”",
    "“A little progress each day adds up to big results.”"
]

ACHIEVEMENTS = {
    'first_message': "First Message Sent",
    'daily_login': "Daily Dedication",
    'level_5': "Level 5 Achieved",
    'level_10': "Level 10 Achieved"
}

def award_xp(session_id, amount=10):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT xp, level, achievements FROM users WHERE session_id=?', (session_id,))
    row = c.fetchone()
    if row:
        xp, level, ach = row['xp'], row['level'], row['achievements'].split(',') if row['achievements'] else []
        xp += amount
        level = 1 + xp // 100
        # Award achievements
        if xp > 0 and ACHIEVEMENTS['first_message'] not in ach:
            ach.append(ACHIEVEMENTS['first_message'])
        if level >= 5 and ACHIEVEMENTS['level_5'] not in ach:
            ach.append(ACHIEVEMENTS['level_5'])
        if level >= 10 and ACHIEVEMENTS['level_10'] not in ach:
            ach.append(ACHIEVEMENTS['level_10'])
        c.execute('UPDATE users SET xp=?, level=?, achievements=? WHERE session_id=?',
                  (xp, level, ','.join(ach), session_id))
        conn.commit()
    conn.close()
    return random.choice(QUOTES)

# ---------------- RESPONSES ----------------
RESPONSES = {
    'availability': ["I can check the listing if you provide the ID or car details."],
    'post_listing': ["To post a car, go to Sellers > Add Listing and complete the form."],
    'contact_seller': ["Message the seller directly from the listing page."],
    'pricing': ["Listing prices depend on year, mileage, and condition."],
    'payment': ["We support bank transfer and escrow payments."],
    'report_issue': ["I can open a support ticket for this — please describe the problem."],
    'hours': ["Customer support is available Mon-Fri 9:00-17:00."],
    'help': ["I can help with listings, payments, contacting sellers, or reporting issues."],
    'unknown': ["I didn't understand that. You can type 'escalate' to open a ticket."]
}

# ---------------- CHAT ENDPOINT ----------------
@app.route('/message', methods=['POST'])
def message():
    data = request.json or {}
    text = (data.get('text') or '').strip()
    name = data.get('name')
    email = data.get('email')
    sid = get_session_id()
    if not text:
        return jsonify({'error': 'empty_message'}), 400

    save_user_profile(sid, name, email)

    ok, reason = moderate_text(text)
    if not ok:
        return jsonify({'error': reason}), 403

    log_message(sid, 'user', text)
    award_quote = award_xp(sid)

    if text.lower() in ('escalate', 'open ticket', 'human', 'agent'):
        ticket_id = create_ticket(sid, 'User requested escalation', text)
        reply = f"Escalation ticket #{ticket_id} created. Our team will reach out soon."
        log_message(sid, 'bot', reply)
        return jsonify({'reply': reply, 'ticket_id': ticket_id, 'quote': award_quote})

    intent = detect_intent(text)
    kb_hits = search_kb(text)
    if kb_hits:
        answer = kb_hits[0]['answer']
        reply = f"{answer}\n\nType 'escalate' if you need further assistance."
        log_message(sid, 'bot', reply)
        return jsonify({'reply': reply, 'source': 'kb', 'matches': kb_hits, 'quote': award_quote})

    if intent in RESPONSES:
        reply = random.choice(RESPONSES[intent])
        log_message(sid, 'bot', reply)
        return jsonify({'reply': reply, 'intent': intent, 'quote': award_quote})

    if USE_AI:
        ai_answer = ai_fallback(text)
        log_message(sid, 'bot', ai_answer)
        return jsonify({'reply': ai_answer, 'source': 'ai', 'quote': award_quote})

    reply = random.choice(RESPONSES['unknown'])
    log_message(sid, 'bot', reply)
    return jsonify({'reply': reply, 'intent': 'unknown', 'quote': award_quote})

# ---------------- DASHBOARD ENDPOINTS ----------------
@app.route('/leaderboard', methods=['GET'])
def leaderboard():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT name, xp, level, achievements FROM users ORDER BY level DESC, xp DESC LIMIT 50')
    rows = c.fetchall()
    conn.close()
    board = [dict(r) for r in rows]
    return jsonify(board)

@app.route('/daily_reward', methods=['POST'])
def daily_reward():
    sid = get_session_id()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT last_seen FROM users WHERE session_id=?', (sid,))
    row = c.fetchone()
    now = datetime.utcnow()
    # naive 24h reward
    last = datetime.fromisoformat(row['last_seen']) if row else now - timedelta(days=1)
    if now - last >= timedelta(hours=24):
        award_xp(sid, 20)
        message = "You received 20 bonus XP!"
    else:
        message = "Daily reward already claimed. Try again later."
    conn.close()
    return jsonify({'message': message})

@app.route('/achievements', methods=['GET'])
def achievements():
    sid = get_session_id()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT achievements FROM users WHERE session_id=?', (sid,))
    row = c.fetchone()
    conn.close()
    ach_list = row['achievements'].split(',') if row and row['achievements'] else []
    return jsonify(ach_list)

# ---------------- OTHER ADMIN ENDPOINTS ----------------
@app.route('/tickets', methods=['GET'])
def tickets():
    key = request.headers.get('X-ADMIN-KEY') or request.args.get('admin_key')
    if key != ADMIN_KEY:
        return jsonify({'error': 'unauthorized'}), 401
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, session_id, subject, status, created_at FROM tickets ORDER BY created_at DESC LIMIT 100')
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/users', methods=['GET'])
def users():
    key = request.headers.get('X-ADMIN-KEY') or request.args.get('admin_key')
    if key != ADMIN_KEY:
        return jsonify({'error': 'unauthorized'}), 401
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT session_id, name, email, last_seen, xp, level, achievements FROM users ORDER BY last_seen DESC LIMIT 200')
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ---------------- HEALTH ----------------
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'time': datetime.utcnow().isoformat(), 'ai_enabled': USE_AI})

# ---------------- BOOT ----------------
if __name__ == "__main__":
    init_db()
    seed_kb()
    app.run(host='0.0.0.0', port=5000, debug=True)
