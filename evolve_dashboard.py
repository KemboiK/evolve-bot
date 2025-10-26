"""
Evolve Bot + Local Dashboard Demo

Safe local-only simulation of tasks and automation.
No external website interactions — only local HTML, Flask routes, and mock data.
"""

from flask import Flask, jsonify, render_template_string, request
import os
import time
import random

app = Flask(__name__)
app.secret_key = os.environ.get('BOT_SECRET_KEY', 'local-secret')

# ---------------- MOCK TASK DATA ----------------
TASKS = [
    {"id": 1, "title": "Watch AI Intro", "type": "video", "file": "static/ai_intro.mp4"},
    {"id": 2, "title": "Complete Python Basics", "type": "quiz", "file": "static/python_basics.html"},
    {"id": 3, "title": "Read Data Science Overview", "type": "article", "file": "static/data_science.html"},
]

# ---------------- HTML TEMPLATE ----------------
PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Evolve Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; background: #111; color: #eee; padding: 20px; }
        h1 { color: #0f9; }
        .task { background: #222; padding: 15px; border-radius: 10px; margin-bottom: 10px; }
        button { padding: 8px 12px; border: none; border-radius: 8px; background: #0f9; color: #111; cursor: pointer; }
        video { width: 100%; max-width: 500px; margin-top: 15px; display: none; }
    </style>
</head>
<body>
    <h1>🧠 Evolve Bot Dashboard</h1>
    <p>Click a task to simulate watching, reading, or completing.</p>
    {% for t in tasks %}
        <div class="task">
            <h3>{{t.title}}</h3>
            <button onclick="runTask({{t.id}})">Run Task</button>
            {% if t.type == 'video' %}
                <video id="vid{{t.id}}" controls>
                    <source src="{{t.file}}" type="video/mp4">
                </video>
            {% endif %}
        </div>
    {% endfor %}

    <script>
        async function runTask(id) {
            const res = await fetch(`/run_task/${id}`);
            const data = await res.json();
            alert(data.message);
            const vid = document.getElementById("vid"+id);
            if (vid) vid.style.display = "block";
        }
    </script>
</body>
</html>
"""

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return render_template_string(PAGE_TEMPLATE, tasks=TASKS)

@app.route("/run_task/<int:task_id>")
def run_task(task_id):
    task = next((t for t in TASKS if t["id"] == task_id), None)
    if not task:
        return jsonify({"error": "task_not_found"}), 404

    # Simulate doing the task
    time.sleep(random.uniform(0.5, 1.5))
    msg = f"✅ Task '{task['title']}' completed successfully!"
    print(msg)
    return jsonify({"status": "done", "message": msg})

# ---------------- MAIN ----------------
if __name__ == "__main__":
    os.makedirs("static", exist_ok=True)
    print("Evolve Bot Dashboard running at: http://127.0.0.1:5000")
    app.run(debug=True)
