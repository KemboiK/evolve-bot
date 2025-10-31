"""
Evolve Dashboard (Flask) - V3
------------------------------
Simulates task completions and progress.
Adds quotes, leaderboard, and task visuals.
"""

from flask import Flask, jsonify, render_template_string
import os, random, time

app = Flask(__name__)
app.secret_key = os.environ.get('BOT_SECRET_KEY', 'local-secret')

TASKS = [
    {"id": 1, "title": "Watch AI Intro", "type": "video", "file": "static/ai_intro.mp4"},
    {"id": 2, "title": "Complete Python Basics", "type": "quiz", "file": "static/python_basics.html"},
    {"id": 3, "title": "Read Data Science Overview", "type": "article", "file": "static/data_science.html"},
]

QUOTES = [
    "“El aprendizaje nunca agota la mente.” — Leonardo da Vinci",
    "“El éxito es la suma de pequeños esfuerzos repetidos día tras día.”",
    "“Nunca es tarde para ser lo que podrías haber sido.” — George Eliot",
    "“Aprender es un tesoro que seguirá a su dueño a todas partes.” — Proverbio chino"
]

LEADERBOARD = [
    {"name": "Ana", "xp": 320, "level": 4},
    {"name": "Carlos", "xp": 270, "level": 3},
    {"name": "Lucía", "xp": 180, "level": 2},
]

PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Evolve Dashboard V3</title>
    <style>
        body { background: #111; color: #eee; font-family: Arial; padding: 20px; }
        h1 { color: #0f9; }
        .task { background: #222; padding: 15px; border-radius: 10px; margin-bottom: 15px; }
        .leaderboard { margin-top: 30px; }
        button { padding: 8px 15px; border: none; border-radius: 8px; background: #0f9; color: #111; cursor: pointer; }
        .quote { margin-top: 30px; font-style: italic; color: #9f9; }
        .bar { background: #333; border-radius: 10px; margin-top: 10px; }
        .fill { height: 10px; border-radius: 10px; background: #0f9; width: 0%; transition: width 1s; }
    </style>
</head>
<body>
    <h1>Evolve Dashboard V3</h1>
    <p>Selecciona una tarea para simular progreso.</p>

    {% for t in tasks %}
        <div class="task">
            <h3>{{t.title}}</h3>
            <button onclick="runTask({{t.id}})">Iniciar tarea</button>
            <div class="bar"><div id="bar{{t.id}}" class="fill"></div></div>
        </div>
    {% endfor %}

    <div class="leaderboard">
        <h3>🏆 Clasificación Global</h3>
        <ul>
            {% for user in leaderboard %}
                <li>{{user.name}} — Nivel {{user.level}} ({{user.xp}} XP)</li>
            {% endfor %}
        </ul>
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
        }
    </script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(PAGE_TEMPLATE, tasks=TASKS, leaderboard=LEADERBOARD)

@app.route("/run_task/<int:task_id>")
def run_task(task_id):
    task = next((t for t in TASKS if t["id"] == task_id), None)
    if not task:
        return jsonify({"error": "task_not_found"}), 404
    time.sleep(random.uniform(0.5, 1.2))
    quote = random.choice(QUOTES)
    msg = f"✅ {task['title']} completado con éxito."
    return jsonify({"status": "done", "message": msg, "quote": quote})

if __name__ == "__main__":
    os.makedirs("static", exist_ok=True)
    print("Evolve Dashboard V3 running at: http://127.0.0.1:5001")
    app.run(port=5001, debug=True)
