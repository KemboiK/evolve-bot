"""
Rugike Motors Support Bot (Flask) 
--------------------------------------------------------------
Purpose: AI-powered customer & seller support assistant for Rugike Motors.
- Handles buyer and seller inquiries
- Lightweight intent detection + FAQ KB
- Logs conversations and creates escalation tickets
- Optional OpenAI fallback (if OPENAI_API_KEY present)
- Syncs events to dashboard via DASHBOARD_URL
"""

from flask import Flask, request, jsonify, session
import os
import sqlite3
import re
import random
import requests
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

# optional OpenAI import
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
    # messages: chat log
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    created_at TEXT
                 )''')
    # users: basic profile (session-based)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    session_id TEXT PRIMARY KEY,
                    name TEXT,
                    email TEXT,
                    last_seen TEXT
                 )''')
    # tickets: escalations / support tickets
    c.execute('''CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    subject TEXT,
                    description TEXT,
                    status TEXT,
                    created_at TEXT,
                    updated_at TEXT
                 )''')
    # knowledge base: simple local KB of FAQs
    c.execute('''CREATE TABLE IF NOT EXISTS kb (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT,
                    answer TEXT,
                    tags TEXT
                 )''')
    conn.commit()
    conn.close()

init_db()

# seed KB if empty
def seed_kb():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM kb')
    if c.fetchone()[0] == 0:
        kb_items = [
            ("How do I list a car for sale?", "Go to Sellers > Add Listing and fill required fields (make, model, year, price, photos). We review listings within 24 hours.", "listing,sellers"),
            ("How do I contact a seller?", "Open the car listing and click 'Contact Seller' — you can send a message or request a call.", "contact,transactions"),
            ("What are seller requirements?", "Sellers must verify ID and provide vehicle ownership documents. Check Seller Policy page for full details.", "sellers,policy,verification"),
            ("How do I pay for a car?", "We currently support bank transfer and escrow payments. Follow checkout steps on the listing or contact support.", "payments,checkout"),
            ("How do I report a problem with a listing?", "Use 'Report Listing' on the car detail page or message our support through the chat to open a ticket.", "report,listing,issues")
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

# ---------------- SIMPLE INTENT DETECTION ----------------
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
    # direct keyword mapping
    for intent, patterns in INTENTS.items():
        for p in patterns:
            try:
                if re.search(p, text_l):
                    return intent
            except re.error:
                if p in text_l:
                    return intent
    # fallback heuristics
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
def ai_fallback(user_message, context=None):
    """
    If OpenAI key is present, use it as a fallback.
    Keep prompts concise and safe.
    """
    if not USE_AI:
        # simple polite fallback
        return ("Sorry — I couldn't find an exact answer. "
                "You can ask to contact support or type 'escalate' to open a ticket.")
    try:
        prompt = f"You are a helpful support assistant for an online car marketplace called Rugike Motors.\nUser: {user_message}\nAnswer concisely and professionally, include steps or ask to escalate if needed."
        res = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "You are Rugike Motors customer support assistant."},
                      {"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.2
        )
        return res.choices[0].message.content.strip()
    except Exception:
        return ("Sorry — I'm temporarily unable to fetch an AI answer. "
                "Please type 'escalate' to open a support ticket or try again later.")

# ---------------- LOGGING & DASHBOARD SYNC ----------------
def log_message(session_id, role, content):
    now = datetime.utcnow().isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)',
              (session_id, role, content, now))
    conn.commit()
    conn.close()
    # send a lightweight event to the dashboard for analytics (non-blocking)
    try:
        payload = {'sid': session_id, 'role': role, 'content': content}
        requests.post(f"{DASHBOARD_URL}/log_message", json=payload, timeout=1.5)
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
    # notify dashboard
    try:
        requests.post(f"{DASHBOARD_URL}/log_message", json={'sid': session_id, 'role': 'system', 'content': f"ticket_created:{ticket_id}"}, timeout=1.5)
    except Exception:
        pass
    return ticket_id

def list_tickets(limit=100):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, session_id, subject, status, created_at FROM tickets ORDER BY created_at DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ---------------- RESPONSE TEMPLATES & KB ----------------
RESPONSES = {
    'availability': [
        "If you'd like I can check the listing status — please provide the listing ID or the car make/model.",
        "I can look that up. Share the listing ID or the car details (make, model, year)."
    ],
    'post_listing': [
        "To post a car, go to Sellers > Add Listing and complete the form. Need a step-by-step guide?",
        "I can walk you through creating a listing now — would you like to start?"
    ],
    'contact_seller': [
        "Open the listing and click 'Contact Seller' to send a message. Want me to draft a message for you?",
        "You can message the seller directly from the listing page. If you'd like, give me a short note and I will format it."
    ],
    'pricing': [
        "Listing prices depend on year, mileage, and condition. Do you want an estimated price range? Share make/model/year.",
        "I can provide pricing guidance if you share the car details or listing ID."
    ],
    'payment': [
        "We support bank transfers and escrow payments. For high-value purchases consider using our escrow service.",
        "Payment options: bank transfer, escrow. We don't handle cash delivery — let me know which you prefer."
    ],
    'report_issue': [
        "I'm sorry to hear that. I can open a support ticket for this — please give a short description of the problem.",
        "I can report the listing and escalate this to our trust team. Do you want me to open a ticket?"
    ],
    'hours': [
        "Our customer support is available Mon-Fri 9:00-17:00 local time. For urgent matters, type 'escalate'."
    ],
    'help': [
        "I can help with listings, payments, contacting sellers, and reporting issues. What would you like to do?",
        "Tell me what you need (e.g., 'Sell my car', 'Contact seller', 'Report listing', 'Payment options')."
    ],
    'unknown': [
        "I didn't quite get that. Could you rephrase or provide the listing ID or car details?",
        "I can help with listings, payments, contacting sellers, or escalate to a human. Type 'escalate' to open a ticket."
    ]
}

# ---------------- MAIN CHAT ENDPOINT ----------------
@app.route('/message', methods=['POST'])
def message():
    data = request.json or {}
    text = (data.get('text') or '').strip()
    name = data.get('name')  # optional
    email = data.get('email')  # optional
    sid = get_session_id()

    if not text:
        return jsonify({'error': 'empty_message'}), 400

    # record user profile
    save_user_profile(sid, name=name, email=email)
    # moderation
    ok, reason = moderate_text(text), ""
    if isinstance(ok, tuple):
        ok, reason = ok
    if not ok:
        return jsonify({'error': reason}), 403

    log_message(sid, 'user', text)

    # quick command: escalate
    if text.lower().strip() in ('escalate', 'open ticket', 'human', 'agent'):
        ticket_id = create_ticket(sid, 'User requested escalation', text)
        reply = f"An escalation ticket (#{ticket_id}) has been created. Our team will reach out soon."
        log_message(sid, 'bot', reply)
        return jsonify({'reply': reply, 'ticket_id': ticket_id})

    # detect intent
    intent = detect_intent(text)
    # try knowledge base hits first
    kb_hits = search_kb(text)
    if kb_hits:
        # return most relevant KB answer + offer next actions
        answer = kb_hits[0]['answer']
        reply = f"{answer}\n\nIf that doesn't help, reply 'escalate' to open a ticket or type 'contact' to reach a human."
        log_message(sid, 'bot', reply)
        return jsonify({'reply': reply, 'source': 'kb', 'matches': kb_hits})

    # mapped intent responses
    if intent in RESPONSES:
        reply = random.choice(RESPONSES[intent])
        # if availability or pricing ask for details
        if intent in ('availability', 'pricing'):
            # prompt for listing ID
            reply += " If you have the listing ID (e.g., #1234), paste it here and I'll check."
        log_message(sid, 'bot', reply)
        return jsonify({'reply': reply, 'intent': intent})

    # fallback to AI or unknown response
    if USE_AI:
        ai_answer = ai_fallback(text)
        log_message(sid, 'bot', ai_answer)
        return jsonify({'reply': ai_answer, 'source': 'ai'})

    # generic unknown
    reply = random.choice(RESPONSES['unknown'])
    log_message(sid, 'bot', reply)
    return jsonify({'reply': reply, 'intent': 'unknown'})

# ---------------- HISTORY ----------------
@app.route('/history', methods=['GET'])
def history():
    sid = request.args.get('sid') or get_session_id()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT role, content, created_at FROM messages WHERE session_id=? ORDER BY created_at ASC', (sid,))
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ---------------- ESCALATE (manual) ----------------
@app.route('/escalate', methods=['POST'])
def escalate():
    data = request.json or {}
    sid = data.get('sid') or get_session_id()
    subject = data.get('subject', 'User escalation request')
    description = data.get('description', '')
    ticket_id = create_ticket(sid, subject, description)
    return jsonify({'ticket_id': ticket_id, 'message': 'Ticket created'})

# ---------------- TICKETS (admin) ----------------
@app.route('/tickets', methods=['GET'])
def tickets():
    key = request.headers.get('X-ADMIN-KEY') or request.args.get('admin_key')
    if key != ADMIN_KEY:
        return jsonify({'error': 'unauthorized'}), 401
    t = list_tickets()
    return jsonify(t)

# ---------------- KB SEARCH ----------------
@app.route('/kb', methods=['GET'])
def kb_search():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'no_query'}), 400
    hits = search_kb(q)
    return jsonify(hits)

# ---------------- USERS (admin) ----------------
@app.route('/users', methods=['GET'])
def users():
    key = request.headers.get('X-ADMIN-KEY') or request.args.get('admin_key')
    if key != ADMIN_KEY:
        return jsonify({'error': 'unauthorized'}), 401
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT session_id, name, email, last_seen FROM users ORDER BY last_seen DESC LIMIT 200')
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ---------------- HEALTH ----------------
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'time': datetime.utcnow().isoformat(), 'ai_enabled': USE_AI})

# ---------------- SIMPLE ADMIN: add KB item ----------------
@app.route('/admin/kb/add', methods=['POST'])
def add_kb():
    key = request.headers.get('X-ADMIN-KEY') or request.args.get('admin_key')
    if key != ADMIN_KEY:
        return jsonify({'error': 'unauthorized'}), 401
    data = request.json or {}
    q = data.get('question')
    a = data.get('answer')
    tags = data.get('tags', '')
    if not q or not a:
        return jsonify({'error': 'missing_fields'}), 400
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO kb (question, answer, tags) VALUES (?,?,?)', (q, a, tags))
    conn.commit()
    conn.close()
    return jsonify({'status': 'added'})

# ---------------- BOOT ----------------
if __name__ == "__main__":
    init_db()
    seed_kb()
    app.run(host='0.0.0.0', port=5000, debug=True)
