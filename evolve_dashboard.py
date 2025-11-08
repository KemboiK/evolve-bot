"""
Evolve Dashboard (Flask) - V4 Synced
-------------------------------------
Enhanced dashboard synced with Evolve Learning Bot.
- Simulates interactive tasks
- Displays rotating motivational quotes
- Dynamic leaderboard with XP rewards
- Daily reward system
- Achievement popups
"""

from flask import Flask, jsonify, render_template_string
import os, random, time

app = Flask(__name__)
app.secret_key = os.environ.get('BOT_SECRET_KEY', 'local-secret')

# ---------------- TASKS ----------------
TASKS = [
    {"id": 1, "title": "Watch AI Intro", "type": "video", "file": "static/ai_intro.mp4"},
    {"id": 2, "title": "Complete Python Basics", "type": "quiz", "file": "static/python_basics.html"},
    {"id": 3, "title": "Read Data Science Overview", "type": "article", "file": "static/data_science.html"},
    {"id": 4, "title": "Take General Knowledge Quiz", "type": "quiz", "file": "static/general_quiz.html"},
]

# ---------------- QUOTES ----------------
QUOTES = [
    "“Learning never exhausts the mind.” — Leonardo da Vinci",
    "“Success is the sum of small efforts repeated day in and day out.” — Robert Collier",
    "“Never stop learning, because life never stops teaching.”",
    "“Education is the most powerful weapon you can use to change the world.” — Nelson Mandela",
    "“Curiosity is the wick in the candle of learning.” — William Arthur Ward",
    "“Knowledge grows when shared.”",
    "“A little progress each day adds up to big results.”"
]

# ---------------- LEADERBOARD ----------------
LEADERBOARD = [
    {"name": "Ana", "xp": 520, "level": 6, "achievements": ["Fast Learner"]},
    {"name": "Carlos", "xp": 400, "level": 5, "achievements": ["Consistent"]},
    {"name": "Lucía", "xp": 290, "level": 3, "achievements": []},
    {"name": "Devon", "xp": 230, "level": 3, "achievements": []},
]

# ---------------- HTML TEMPLATE ----------------
PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Evolve Dashboard V4</title>
    <style>
        body { background: #0d1117; color: #e6edf3; font-family: Arial, sans-serif; padding: 25px; }
        h1 { color: #00d084; }
        .task { background: #161b22; padding: 15px; border-radius: 10px; margin-bottom: 15px; box-shadow: 0 0 10px #0f3; }
        .leaderboard { margin-top: 30px; background: #161b22; padding: 15px; border-radius: 10px; }
        button { padding: 8px 15px; border: none; border-radius: 8px; background: #00d084; color: #0d1117; cursor: pointer; font-weight: bold; }
        .quote { margin-top: 30px; font-style: italic; color: #7ee787; }
        .bar { background: #21262d; border-radius: 10px; margin-top: 10px; }
        .fill { height: 10px; border-radius: 10px; background: #00d084; width: 0%; transition: width 1s; }
        a { color: #58a6ff; text-decoration: none; }
        .daily-reward { background: #0a3622; color: #00ffb3; padding: 10px; border-radius: 8px; margin-top: 25px; }
        .reward-btn { background: #00ffb3; color: #0d1117; padding: 8px 14px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }
        .achievement { background: #111; color: #ffd700; padding: 8px; border-radius: 8px; margin-top: 10px; display: inline-block; }
    </style>
</head>
<body>
    <h1>🚀 Evolve Dashboard V4</h1>
    <p>Select a task below to simulate learning progress.</p>

    {% for t in tasks %}
        <div class="task">
            <h3>{{t.title}}</h3>
            <p>Type: {{t.type | capitalize}}</p>
            {% if t.file %}
                <p><a href="{{t.file}}" target="_blank">Open resource</a></p>
            {% endif %}
            <button onclick="runTask({{t.id}})">Start Task</button>
            <div class="bar"><div id="bar{{t.id}}" class="fill"></div></div>
        </div>
    {% endfor %}

    <div class="leaderboard">
        <h3>🏆 Global Leaderboard</h3>
        <ul id="leaderboard">
            {% for user in leaderboard %}
                <li>{{user.name}} — Level {{user.level}} ({{user.xp}} XP)
                    {% if user.achievements %}
                        <div>
                            {% for a in user.achievements %}
                                <span class="achievement">🏅 {{a}}</span>
                            {% endfor %}
                        </div>
                    {% endif %}
                </li>
            {% endfor %}
        </ul>
    </div>

    <div class="daily-reward">
        <h4>🎁 Daily Reward</h4>
        <p>Claim 20 bonus XP once every day!</p>
        <button class="reward-btn" onclick="claimReward()">Claim Reward</button>
    </div>

    <div id="quote" class="quote"></div>

    <script>
        async function runTask(id) {
            const bar = document.getElementById("bar"+id);
            bar.style.width = "0%";
            const res = await fetch(`/run_task/${id}`);
            const data = await res.json();
            bar.style.width = "100%";
            alert(data.message);
            document.getElementById("quote").innerText = data.quote;
            refreshLeaderboard();
        }

        async function claimReward() {
            const res = await fetch('/claim_reward');
            const data = await res.json();
            alert(data.message);
            refreshLeaderboard();
        }

        async function refreshLeaderboard() {
            const res = await fetch('/leaderboard');
            const data = await res.json();
            const ul = document.getElementById('leaderboard');
            ul.innerHTML = '';
            data.forEach(u => {
                const li = document.createElement('li');
                li.innerHTML = `${u.name} — Level ${u.level} (${u.xp} XP)` +
                    (u.achievements.length ? '<div>' + u.achievements.map(a => `<span class="achievement">🏅 ${a}</span>`).join(' ') + '</div>' : '');
                ul.appendChild(li);
            });
        }
    </script>
</body>
</html>
"""

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return render_template_string(PAGE_TEMPLATE, tasks=TASKS, leaderboard=LEADERBOARD)

@app.route("/run_task/<int:task_id>")
def run_task(task_id):
    task = next((t for t in TASKS if t["id"] == task_id), None)
    if not task:
        return jsonify({"error": "task_not_found"}), 404

    time.sleep(random.uniform(0.6, 1.5))
    quote = random.choice(QUOTES)
    msg = f"✅ {task['title']} completed successfully!"

    # Give XP + check for new achievements
    user = random.choice(LEADERBOARD)
    gained = random.randint(10, 25)
    user["xp"] += gained
    if user["xp"] > 500 and "Level Master" not in user["achievements"]:
        user["achievements"].append("Level Master")
    if len(user["achievements"]) >= 3 and "Elite Learner" not in user["achievements"]:
        user["achievements"].append("Elite Learner")

    return jsonify({"status": "done", "message": msg, "quote": quote})

@app.route("/claim_reward")
def claim_reward():
    lucky_user = random.choice(LEADERBOARD)
    bonus = 20
    lucky_user["xp"] += bonus
    if bonus >= 20 and "Daily Dedication" not in lucky_user["achievements"]:
        lucky_user["achievements"].append("Daily Dedication")
    return jsonify({"message": f"{lucky_user['name']} claimed {bonus} bonus XP!"})

@app.route("/leaderboard")
def get_leaderboard():
    sorted_board = sorted(LEADERBOARD, key=lambda x: (-x['level'], -x['xp']))
    return jsonify(sorted_board)

# ---------------- MAIN ----------------
if __name__ == "__main__":
    os.makedirs("static", exist_ok=True)
    print("Evolve Dashboard V4 synced running at: http://127.0.0.1:5001")
    app.run(port=5001, debug=True)
