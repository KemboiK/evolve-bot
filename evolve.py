"""
evolve.py - Rugike Motors Evolve Bot (All features)
---------------------------------------------------
Features:
- Conversation logging, moderation, and KB search
- XP, levels, achievements, daily reward
- Session summaries every N messages (uses OpenAI if enabled)
- Ratings (/rate), favorites, tags, personality modes
- Car listing assistant (/car_assist)
- Admin stats (/stats), leaderboard, tickets, analytics events
- Dashboard sync endpoints: POSTs to DASHBOARD_URL
"""

from flask import Flask, request, jsonify, session
import os, sqlite3, re, random, requests, time, json
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('BOT_SECRET_KEY', 'super-secret')
DB_PATH = os.environ.get('BOT_DB', 'rugike_support.db')
DASHBOARD_URL = os.environ.get('DASHBOARD_URL', 'http://127.0.0.1:5001')
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'admin-secret-key')
OPENAI_KEY = os.getenv('OPENAI_API_KEY')
USE_AI = bool(OPENAI_KEY)

if USE_AI:
    try:
        import openai
        openai.api_key = OPENAI_KEY
    except Exception:
        USE_AI = False

# ---------------- DB helpers ----------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # core tables
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT, role TEXT, content TEXT, created_at TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    session_id TEXT PRIMARY KEY, name TEXT, email TEXT,
                    last_seen TEXT, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
                    achievements TEXT DEFAULT '', mode TEXT DEFAULT 'friendly'
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
                    subject TEXT, description TEXT, status TEXT, created_at TEXT, updated_at TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS kb (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, answer TEXT, tags TEXT
                )''')
    # new feature tables
    c.execute('''CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
                    summary TEXT, created_at TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS ratings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
                    rating INTEGER, note TEXT, created_at TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
                    content TEXT, created_at TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
                    tag TEXT, created_at TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

# seed KB (if empty)
def seed_kb():
    conn = get_db_connection(); c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM kb'); if_empty = c.fetchone()[0]==0
    if if_empty:
        items = [
            ("How to list a car?", "Go to Sellers > Add Listing and fill required fields. Listings reviewed within 24h.", "listing,sellers"),
            ("Payment methods", "We support bank transfer and escrow. Contact support for help.", "payments"),
            ("Reporting fraud", "Use 'Report Listing' on the listing page or type 'escalate' to open a ticket.", "report,security")
        ]
        c.executemany('INSERT INTO kb (question,answer,tags) VALUES (?,?,?)', items)
        conn.commit()
    conn.close()

seed_kb()

# ---------------- utils ----------------
def get_session_id():
    sid = session.get('sid')
    if not sid:
        sid = os.urandom(16).hex()
        session['sid'] = sid
    return sid

def save_user_profile(sid, name=None, email=None):
    now = datetime.utcnow().isoformat()
    conn = get_db_connection(); c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (session_id, name, email, last_seen) VALUES (?,?,?,?)', (sid, name, email, now))
    c.execute('UPDATE users SET last_seen=? WHERE session_id=?', (now, sid))
    conn.commit(); conn.close()

def log_message(session_id, role, content):
    now = datetime.utcnow().isoformat()
    conn = get_db_connection(); c = conn.cursor()
    c.execute('INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)', (session_id, role, content, now))
    conn.commit(); conn.close()
    # send to dashboard (best-effort)
    try:
        requests.post(f"{DASHBOARD_URL}/log_message", json={'sid': session_id, 'role': role, 'content': content, 'time': now}, timeout=1.5)
    except Exception:
        pass

# ---------------- moderation ----------------
PROHIBITED_PATTERNS = [r"\bterror\b", r"\bexplosive\b", r"\bkill\b"]
def moderate_text(text):
    lowered = text.lower()
    for p in PROHIBITED_PATTERNS:
        if re.search(p, lowered):
            return False, "Potentially violent or illegal content detected."
    return True, ""

# ---------------- analytics events ----------------
def send_analytics(event_type, payload):
    payload = {'event': event_type, 'payload': payload, 'time': datetime.utcnow().isoformat()}
    try:
        requests.post(f"{DASHBOARD_URL}/analytics_event", json=payload, timeout=1.5)
    except Exception:
        pass

# ---------------- gamification ----------------
ACHIEVEMENTS = {
    'first_msg': "First Message",
    'daily': "Daily Learner",
    'level5': "Reached Level 5",
    'level10': "Reached Level 10"
}

def award_xp(session_id, amount=10):
    conn = get_db_connection(); c = conn.cursor()
    c.execute('SELECT xp, level, achievements FROM users WHERE session_id=?', (session_id,))
    row = c.fetchone()
    if row:
        xp, level, achs = row['xp'], row['level'], row['achievements'] or ''
        xp += amount
        new_level = 1 + xp // 100
        achievements = set([a for a in achs.split(',') if a]) if achs else set()
        if xp > 0 and 'First Message' not in achievements:
            achievements.add(ACHIEVEMENTS['first_msg'])
        if new_level >=5 and ACHIEVEMENTS['level5'] not in achievements:
            achievements.add(ACHIEVEMENTS['level5'])
        if new_level >=10 and ACHIEVEMENTS['level10'] not in achievements:
            achievements.add(ACHIEVEMENTS['level10'])
        c.execute('UPDATE users SET xp=?, level=?, achievements=? WHERE session_id=?', (xp, new_level, ','.join(achievements), session_id))
        conn.commit()
    conn.close()
    # notify dashboard
    send_analytics('xp_awarded', {'sid': session_id, 'amount': amount})
    return random.choice([
        "Nice progress! Keep going.",
        "Great work — XP added!",
        "You're learning — XP awarded!"
    ])

# ---------------- kb & intents ----------------
INTENTS = {
    'availability': ['available', 'still available', 'is it available'],
    'post_listing': ['list a car', 'sell my car', 'post listing'],
    'contact_seller': ['contact seller', 'message seller', 'call seller'],
    'pricing': ['price', 'cost', 'how much'],
    'payment': ['pay', 'payment', 'escrow', 'bank transfer'],
    'report_issue': ['report', 'fraud', 'scam', 'problem with listing'],
    'help': ['help', 'support', 'customer service', '?']
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
    return 'unknown'

def search_kb(query, limit=3):
    conn = get_db_connection(); c = conn.cursor()
    q = f"%{query.lower()}%"
    c.execute('SELECT question,answer FROM kb WHERE LOWER(question) LIKE ? OR LOWER(tags) LIKE ? LIMIT ?', (q,q,limit))
    rows = c.fetchall(); conn.close()
    return [{'question': r['question'], 'answer': r['answer']} for r in rows]

# ---------------- OpenAI helpers (optional) ----------------
def generate_summary_from_messages(session_id, messages_text):
    if not USE_AI:
        # simple fallback: first+last sentences
        snippet = ' '.join(messages_text.split()[:40])
        return f"Quick summary: {snippet}..."
    try:
        prompt = f"Summarize the user support conversation concisely:\n\n{messages_text}\n\nSummary:"
        res = openai.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}], max_tokens=150, temperature=0.2)
        return res.choices[0].message.content.strip()
    except Exception:
        return "(AI summary unavailable) Quick summary generated."

def ai_fallback_answer(user_message):
    if not USE_AI:
        return "Sorry — I couldn't find an exact answer. Type 'escalate' to open a ticket."
    try:
        prompt = f"You are a helpful customer support assistant for a car marketplace. Answer concisely.\nUser: {user_message}\nAnswer:"
        res = openai.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}], max_tokens=250, temperature=0.2)
        return res.choices[0].message.content.strip()
    except Exception:
        return "AI unavailable right now."

# ---------------- Car listing assistant ----------------
def car_assistant(text):
    # try to extract basic fields via regex, otherwise ask clarifying Qs or use AI
    fields = {}
    # year
    m = re.search(r'\b(19|20)\d{2}\b', text)
    if m: fields['year'] = m.group(0)
    # mileage
    m = re.search(r'(\d{1,3}(?:,\d{3})+|\d{3,7})\s*(km|miles|mi)', text.lower())
    if m: fields['mileage'] = m.group(0)
    # price
    m = re.search(r'\$\s?[\d,]+', text)
    if m: fields['price'] = m.group(0)
    if len(fields) >= 2:
        # build suggested listing
        title = f"{fields.get('year','Year Unknown')} - Suggested Listing"
        desc = " - ".join([f"{k.title()}: {v}" for k,v in fields.items()])
        return f"I extracted: {desc}. Suggested title: '{title}'. You can refine details or provide more info."
    # fallback to AI if enabled
    if USE_AI:
        return ai_fallback_answer(f"Help format a car listing from: {text}")
    return "I couldn't extract listing details. Please provide year, mileage, and price."

# ---------------- Session summary auto-trigger ----------------
SUMMARY_TRIGGER = 20  # messages per session to auto-summarize
def maybe_create_summary(session_id):
    conn = get_db_connection(); c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM messages WHERE session_id=?', (session_id,))
    count = c.fetchone()[0]
    if count and count % SUMMARY_TRIGGER == 0:
        # fetch recent messages for the session
        c.execute('SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT 200', (session_id,))
        rows = c.fetchall()
        messages_text = '\n'.join([f"{r['role']}: {r['content']}" for r in rows[::-1]])
        summary = generate_summary_from_messages(session_id, messages_text)
        now = datetime.utcnow().isoformat()
        c.execute('INSERT INTO summaries (session_id, summary, created_at) VALUES (?,?,?)', (session_id, summary, now))
        conn.commit(); conn.close()
        # send to dashboard
        try:
            requests.post(f"{DASHBOARD_URL}/session_summary", json={'sid': session_id, 'summary': summary, 'time': now}, timeout=1.5)
        except Exception:
            pass

# ---------------- Endpoints ----------------

@app.route('/message', methods=['POST'])
def message():
    data = request.json or {}
    text = (data.get('text') or '').strip()
    name = data.get('name')
    email = data.get('email')
    sid = get_session_id()
    if not text:
        return jsonify({'error':'empty_message'}), 400

    save_user_profile(sid, name, email)
    ok, reason = moderate_text(text)
    if not ok:
        log_message(sid, 'system', f'mod_block:{reason}')
        return jsonify({'error': reason}), 403

    log_message(sid, 'user', text)
    # award small XP per message
    award_xp(sid, 5)

    # commands
    if text.lower().startswith('/'):
        cmd = text.lower().split()
        if cmd[0] == '/rate':
            # format: /rate 8 optional note...
            try:
                rating = int(cmd[1]); note = ' '.join(cmd[2:]) if len(cmd)>2 else ''
                now = datetime.utcnow().isoformat()
                conn = get_db_connection(); c = conn.cursor()
                c.execute('INSERT INTO ratings (session_id, rating, note, created_at) VALUES (?,?,?,?)', (sid, rating, note, now)); conn.commit(); conn.close()
                send_analytics('rating', {'sid': sid, 'rating': rating})
                return jsonify({'reply': f"Thanks for your rating: {rating}"})
            except Exception:
                return jsonify({'error': 'usage: /rate <0-10> [note]'}), 400
        if cmd[0] == '/setmode':
            mode = cmd[1] if len(cmd)>1 else 'friendly'
            conn = get_db_connection(); c = conn.cursor()
            c.execute('UPDATE users SET mode=? WHERE session_id=?', (mode, sid)); conn.commit(); conn.close()
            return jsonify({'reply': f"Mode set to {mode}"})
        if cmd[0] == '/favorite':
            # save last bot message into favorites
            conn = get_db_connection(); c = conn.cursor()
            c.execute('SELECT content FROM messages WHERE session_id=? AND role="bot" ORDER BY id DESC LIMIT 1', (sid,))
            r = c.fetchone()
            if r:
                now = datetime.utcnow().isoformat()
                c.execute('INSERT INTO favorites (session_id, content, created_at) VALUES (?,?,?)', (sid, r['content'], now)); conn.commit(); conn.close()
                return jsonify({'reply': 'Saved last bot message to favorites.'})
            return jsonify({'error':'no bot message to save'}), 400

    # simple escalate
    if text.lower() in ('escalate', 'open ticket', 'human', 'agent'):
        ticket_id = create_ticket(sid, "User requested escalation", text)
        reply = f"Escalation ticket #{ticket_id} created. Our team will reach out shortly."
        log_message(sid, 'bot', reply)
        maybe_create_summary(sid)
        return jsonify({'reply': reply, 'ticket_id': ticket_id})

    # car assistant
    if any(k in text.lower() for k in ('listing', 'sell my', 'car details', 'price suggestion', 'car assist', 'car_assist')):
        assist = car_assistant(text)
        log_message(sid, 'bot', assist)
        maybe_create_summary(sid)
        return jsonify({'reply': assist})

    # KB search first
    kb_hits = search_kb(text)
    if kb_hits:
        answer = kb_hits[0]['answer']
        reply = f"{answer}\n\nType 'escalate' if you need further assistance."
        log_message(sid, 'bot', reply)
        maybe_create_summary(sid)
        send_analytics('kb_hit', {'sid': sid, 'query': text})
        return jsonify({'reply': reply, 'source': 'kb', 'matches': kb_hits})

    # detect intent & canned responses
    intent = detect_intent(text)
    canned = {
        'availability': "If you share the listing ID, I can check availability.",
        'post_listing': "To post, go to Sellers > Add Listing and fill the required fields.",
        'contact_seller': "Open the listing and click 'Contact Seller' to send a message.",
        'pricing': "Price depends on year, mileage, and condition — provide details for an estimate.",
        'payment': "We support bank transfer and escrow.",
        'report_issue': "I can open a ticket for this; describe the issue or type 'escalate'.",
        'help': "I can help with listings, payments, contacting sellers, or reporting issues."
    }
    if intent in canned:
        reply = canned[intent]
        log_message(sid, 'bot', reply)
        maybe_create_summary(sid)
        send_analytics('intent_response', {'sid': sid, 'intent': intent})
        return jsonify({'reply': reply, 'intent': intent})

    # fallback to AI or unknown
    if USE_AI:
        ai_answer = ai_fallback_answer(text)
        log_message(sid, 'bot', ai_answer)
        maybe_create_summary(sid)
        send_analytics('ai_response', {'sid': sid})
        return jsonify({'reply': ai_answer, 'source': 'ai'})

    # default unknown reply
    reply = "I didn't understand that. Type 'escalate' to open a ticket or ask another question."
    log_message(sid, 'bot', reply)
    maybe_create_summary(sid)
    send_analytics('unknown', {'sid': sid})
    return jsonify({'reply': reply})

# ---------------- tickets, admin, and utilities ----------------
def create_ticket(session_id, subject, description):
    now = datetime.utcnow().isoformat()
    conn = get_db_connection(); c = conn.cursor()
    c.execute('INSERT INTO tickets (session_id, subject, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)', (session_id, subject, description, 'open', now, now))
    ticket_id = c.lastrowid; conn.commit(); conn.close()
    # notify dashboard
    try:
        requests.post(f"{DASHBOARD_URL}/ticket_created", json={'sid': session_id, 'ticket_id': ticket_id, 'subject': subject, 'time': now}, timeout=1.5)
    except Exception:
        pass
    return ticket_id

@app.route('/tickets', methods=['GET'])
def tickets():
    key = request.args.get('admin_key') or request.headers.get('X-ADMIN-KEY')
    if key != ADMIN_KEY:
        return jsonify({'error':'unauthorized'}), 401
    conn = get_db_connection(); c = conn.cursor()
    c.execute('SELECT id, session_id, subject, status, created_at FROM tickets ORDER BY created_at DESC LIMIT 200')
    rows = [dict(r) for r in c.fetchall()]; conn.close()
    return jsonify(rows)

@app.route('/leaderboard', methods=['GET'])
def leaderboard():
    conn = get_db_connection(); c = conn.cursor()
    c.execute('SELECT name, xp, level FROM users ORDER BY level DESC, xp DESC LIMIT 50')
    rows = [dict(r) for r in c.fetchall()]; conn.close()
    return jsonify(rows)

@app.route('/summaries', methods=['GET'])
def summaries():
    sid = request.args.get('sid') or get_session_id()
    conn = get_db_connection(); c = conn.cursor()
    c.execute('SELECT summary, created_at FROM summaries WHERE session_id=? ORDER BY id DESC LIMIT 20', (sid,))
    rows = [dict(r) for r in c.fetchall()]; conn.close()
    return jsonify(rows)

@app.route('/favorites', methods=['GET'])
def favorites():
    sid = request.args.get('sid') or get_session_id()
    conn = get_db_connection(); c = conn.cursor()
    c.execute('SELECT content, created_at FROM favorites WHERE session_id=? ORDER BY id DESC', (sid,))
    rows = [dict(r) for r in c.fetchall()]; conn.close()
    return jsonify(rows)

@app.route('/stats', methods=['GET'])
def stats():
    key = request.args.get('admin_key') or request.headers.get('X-ADMIN-KEY')
    if key != ADMIN_KEY:
        return jsonify({'error':'unauthorized'}), 401
    conn = get_db_connection(); c = conn.cursor()
    # basic analytics
    c.execute('SELECT COUNT(*) as msgs FROM messages'); msgs = c.fetchone()['msgs']
    c.execute('SELECT COUNT(DISTINCT session_id) as sessions FROM messages'); sessions = c.fetchone()['sessions']
    c.execute('SELECT COUNT(*) FROM tickets WHERE status="open"'); open_tickets = c.fetchone()[0]
    c.execute('SELECT name, xp, level FROM users ORDER BY level DESC, xp DESC LIMIT 10'); top = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify({'messages': msgs, 'sessions': sessions, 'open_tickets': open_tickets, 'top_users': top})

# health
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status':'ok', 'time': datetime.utcnow().isoformat(), 'ai_enabled': USE_AI})

# quick helpers to read messages count (used by summary trigger on demand)
@app.route('/msg_count', methods=['GET'])
def msg_count():
    sid = request.args.get('sid') or get_session_id()
    conn = get_db_connection(); c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM messages WHERE session_id=?', (sid,))
    cnt = c.fetchone()[0]; conn.close()
    return jsonify({'count': cnt})

# ----------------- run -----------------
if __name__ == '__main__':
    init_db()
    seed_kb()
    print("Evolve Bot running on http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
