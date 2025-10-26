"""
Evolve Bot - starter single-file chatbot (Flask)

What it is:
- A minimal, extensible chatbot server that can be used to respond to clients in a conversational format.
- Contains safe-guards, templates, logging, session handling, reply variability and placeholders to plug an LLM (OpenAI or other).

Important ethical & safety notes:
- This code includes logging for safety:
  1) ALWAYS verify age and consent of users.
  2) Respect local laws and platform terms. Do not impersonate people where prohibited.
  3) Consider adding human moderation and opt-out reporting.

How to run:
- python3 -m venv venv && source venv/bin/activate
- pip install flask sqlalchemy jinja2 python-dotenv requests
- export/put OPENAI_API_KEY (optional) in .env
- python evolve-bot-starter.py

This file intentionally keeps the LLM call optional and uses a deterministic template fallback,
so you can test the bot without any paid API.
"""

from flask import Flask, request, jsonify, session, render_template_string
from functools import wraps
import re
import os
import random
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('BOT_SECRET_KEY', 'replace-with-secure-secret')
DB_PATH = os.environ.get('BOT_DB', 'evolve_bot.db')

# ---------------------- Basic DB (SQLite) ----------------------
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

# ---------------------- Utilities ----------------------

def log_message(session_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)',
              (session_id, role, content, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

# simple age-check placeholder - to be replaced by a proper age verification system in production
def check_age_claim(age_str):
    try:
        age = int(age_str)
        return age >= 18
    except Exception:
        return False

# Basic content moderation heuristics (very simplistic) - replace with a proper moderation API
ILLEGAL_PATTERNS = [r"\bchild\b", r"\bunderage\b", r"\bteen\b"]
PROHIBITED_PATTERNS = [r"\bkill\b", r"\bterror\b", r"\bexplosive\b"]

def moderate_text(text):
    lowered = text.lower()
    for p in ILLEGAL_PATTERNS:
        if re.search(p, lowered):
            return False, 'sexual content referencing minors detected'
    for p in PROHIBITED_PATTERNS:
        if re.search(p, lowered):
            return False, 'potential violent/illegal content detected'
    # add more checks (image requests, self-harm, exploitation, etc.)
    return True, ''

# session helper
def get_session_id():
    sid = session.get('sid')
    if not sid:
        sid = os.urandom(16).hex()
        session['sid'] = sid
    return sid

# decorator to require age verification for explicit endpoints
def require_age_verified(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('age_verified'):
            return jsonify({'error': 'age_verification_required'}), 403
        return f(*args, **kwargs)
    return decorated

# ---------------------- Reply generation ----------------------

# A small set of templates to produce varied replies. Use Jinja-style substitution for dynamic fields.
REPLY_TEMPLATES = [
    "Hey {{name}} — thanks for writing. I love hearing about your day. Tell me more: what's one small thing that made you smile today?",
    "Hi {{name}} — you're making me blush. I like that you said '{{snippet}}'. What else do you like about that?",
    "Hello {{name}}. I'm here to listen and enjoy this conversation with you. What are you craving to talk about right now?",
    "Sweet {{name}}, that sounds interesting. I enjoy deep conversations and playful moments. Want to share a secret fantasy or keep it light?",
]

SYSTEM_PROMPT = (
    "You are a compassionate, flirty, respectful conversationalist. Keep replies adult-only (>=18), avoid explicit sexual details unless the user clearly asks",
)

# Optional integration with an LLM (OpenAI shown as example) - YOU MUST install openai and set OPENAI_API_KEY
def call_llm_api(prompt, max_tokens=200):
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return None  # caller will fall back to template
    # Example using requests to call OpenAI completion endpoint (commented out - placeholder)
    # import requests
    # headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    # payload = { 'model': 'gpt-4o-mini', 'messages': [{'role':'system','content':SYSTEM_PROMPT},{'role':'user','content':prompt}], 'max_tokens': max_tokens }
    # r = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json=payload)
    # if r.status_code == 200:
    #     return r.json()['choices'][0]['message']['content']
    # else:
    #     return None
    return None


def choose_template_and_fill(user_name='Friend', user_snippet=''):
    t = random.choice(REPLY_TEMPLATES)
    rendered = render_template_string(t, name=user_name, snippet=user_snippet)
    return rendered


def generate_reply(user_message, user_name='Friend'):
    # moderation
    ok, reason = moderate_text(user_message)
    if not ok:
        return {'error': 'blocked', 'reason': reason}

    # try LLM first (optional)
    prompt = f"{SYSTEM_PROMPT}\nUser: {user_message}\nRespond as a warm adult conversational partner."
    llm_resp = call_llm_api(prompt)
    if llm_resp:
        # post-process: avoid extremely graphic language unless user requested explicit content
        return {'reply': llm_resp.strip(), 'source': 'llm'}

    # deterministic template fallback
    snippet = (user_message[:80] + '...') if len(user_message) > 80 else user_message
    reply = choose_template_and_fill(user_name, snippet)
    return {'reply': reply, 'source': 'template'}

# ---------------------- HTTP Endpoints ----------------------
@app.route('/')
def home():
    sid = get_session_id()
    return jsonify({'message': 'Evolve Bot running', 'session': sid})

@app.route('/verify_age', methods=['POST'])
def verify_age():
    data = request.json or {}
    age_claim = data.get('age') or data.get('age_claim')
    sid = get_session_id()
    if not age_claim:
        return jsonify({'error': 'age_missing'}), 400
    if check_age_claim(age_claim):
        session['age_verified'] = True
        log_message(sid, 'system', f'age_verified:{age_claim}')
        return jsonify({'ok': True})
    else:
        return jsonify({'error': 'must_be_18_plus'}), 403

@app.route('/message', methods=['POST'])
@require_age_verified
def message():
    data = request.json or {}
    text = data.get('text', '')
    user_name = data.get('name', 'Friend')
    sid = get_session_id()

    if not text:
        return jsonify({'error': 'empty_message'}), 400

    # Log user message
    log_message(sid, 'user', text)

    # generate reply
    result = generate_reply(text, user_name)
    if 'error' in result:
        log_message(sid, 'system', f'blocked_reason:{result.get("reason")}')
        return jsonify({'error': result.get('reason')}), 403

    reply_text = result['reply']
    log_message(sid, 'bot', reply_text)

    return jsonify({'reply': reply_text, 'source': result.get('source', 'template')})

@app.route('/admin/messages', methods=['GET'])
def admin_messages():
    # very simple admin listing - in production add auth
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, session_id, role, content, created_at FROM messages ORDER BY id DESC LIMIT 200')
    rows = c.fetchall()
    conn.close()
    out = [{'id':r[0],'session':r[1],'role':r[2],'content':r[3],'time':r[4]} for r in rows]
    return jsonify(out)

# ---------------------- Run ----------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
