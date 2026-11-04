"""Планировщик проектов: Flask-приложение с задачами, напоминаниями, файлами и анализатором."""
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory, abort

import analyzer
from database import get_conn, init_db, rows_to_list

UPLOAD_DIR = Path(__file__).parent / "data" / "uploads"
app = Flask(__name__)
init_db()


# ---------- Напоминания: фоновый поток ----------
def reminder_worker():
    """Каждые 30 секунд проверяет задачи с наступившим сроком и помечает напоминание."""
    while True:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            with get_conn() as conn:
                conn.execute(
                    "UPDATE tasks SET reminder_sent=1 WHERE due_date<=? AND reminder_sent=0 AND status='open'",
                    (now,))
        except Exception:
            pass
        time.sleep(30)


threading.Thread(target=reminder_worker, daemon=True).start()


# ---------- Страницы ----------
@app.route("/")
def index():
    return render_template("index.html")


# ---------- Проекты ----------
@app.route("/api/projects", methods=["GET"])
def list_projects():
    with get_conn() as conn:
        projects = rows_to_list(conn.execute("""
            SELECT p.*,
              (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.status='open') AS open_tasks,
              (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.status='done') AS done_tasks,
              (SELECT COUNT(*) FROM tasks t JOIN files f ON f.task_id=t.id WHERE t.project_id=p.id) AS file_count
            FROM projects p ORDER BY p.id"""))
    return jsonify(projects)


@app.route("/api/projects", methods=["POST"])
def create_project():
    d = request.get_json(force=True)
    if not d.get("name", "").strip():
        return jsonify({"error": "Название обязательно"}), 400
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO projects(name, description, status) VALUES(?,?,?)",
                           (d["name"].strip(), d.get("description", ""), d.get("status", "active")))
        row = conn.execute("SELECT * FROM projects WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/projects/<int:pid>", methods=["PUT"])
def update_project(pid):
    d = request.get_json(force=True)
    with get_conn() as conn:
        conn.execute("UPDATE projects SET name=?, description=?, status=? WHERE id=?",
                     (d.get("name", ""), d.get("description", ""), d.get("status", "active"), pid))
    return jsonify({"ok": True})


@app.route("/api/projects/<int:pid>", methods=["DELETE"])
def delete_project(pid):
    with get_conn() as conn:
        task_ids = [r["id"] for r in conn.execute("SELECT id FROM tasks WHERE project_id=?", (pid,))]
        for tid in task_ids:
            for f in conn.execute("SELECT stored_name FROM files WHERE task_id=?", (tid,)):
                (UPLOAD_DIR / f["stored_name"]).unlink(missing_ok=True)
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    return jsonify({"ok": True})


# ---------- Задачи ----------
@app.route("/api/projects/<int:pid>/tasks", methods=["GET"])
def list_tasks(pid):
    with get_conn() as conn:
        tasks = rows_to_list(conn.execute(
            "SELECT * FROM tasks WHERE project_id=? ORDER BY status, COALESCE(due_date,'9999'), id DESC", (pid,)))
        for t in tasks:
            t["files"] = rows_to_list(conn.execute("SELECT id, original_name, size FROM files WHERE task_id=?", (t["id"],)))
    return jsonify(tasks)


@app.route("/api/tasks", methods=["POST"])
def create_task():
    d = request.get_json(force=True)
    if not d.get("title", "").strip() or not d.get("project_id"):
        return jsonify({"error": "title и project_id обязательны"}), 400
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tasks(project_id, title, description, priority, due_date) VALUES(?,?,?,?,?)",
            (d["project_id"], d["title"].strip(), d.get("description", ""),
             d.get("priority", "medium"), d.get("due_date") or None))
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/tasks/<int:tid>", methods=["PUT"])
def update_task(tid):
    d = request.get_json(force=True)
    with get_conn() as conn:
        old = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if not old:
            abort(404)
        conn.execute(
            """UPDATE tasks SET title=?, description=?, priority=?, due_date=?, status=?,
               reminder_sent=CASE WHEN ?!=COALESCE(due_date,'') THEN 0 ELSE reminder_sent END,
               completed_at=CASE WHEN ?='done' AND status!='done' THEN datetime('now','localtime') ELSE completed_at END
               WHERE id=?""",
            (d.get("title", old["title"]), d.get("description", old["description"]),
             d.get("priority", old["priority"]), d.get("due_date") or None,
             d.get("status", old["status"]), d.get("due_date") or "", d.get("status", old["status"]), tid))
    return jsonify({"ok": True})


@app.route("/api/tasks/<int:tid>", methods=["DELETE"])
def delete_task(tid):
    with get_conn() as conn:
        for f in conn.execute("SELECT stored_name FROM files WHERE task_id=?", (tid,)):
            (UPLOAD_DIR / f["stored_name"]).unlink(missing_ok=True)
        conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
    return jsonify({"ok": True})


# ---------- Файлы при задачах ----------
@app.route("/api/tasks/<int:tid>/files", methods=["POST"])
def upload_file(tid):
    if "file" not in request.files:
        return jsonify({"error": "Файл не передан"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Пустое имя файла"}), 400
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(f.filename).suffix[:10]
    stored = f"{uuid.uuid4().hex}{ext}"
    f.save(UPLOAD_DIR / stored)
    size = (UPLOAD_DIR / stored).stat().st_size
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO files(task_id, original_name, stored_name, size) VALUES(?,?,?,?)",
                           (tid, f.filename, stored, size))
        row = conn.execute("SELECT id, original_name, size FROM files WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/files/<int:fid>/download")
def download_file(fid):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone()
    if not row:
        abort(404)
    return send_from_directory(UPLOAD_DIR, row["stored_name"], as_attachment=True,
                               download_name=row["original_name"])


@app.route("/api/files/<int:fid>", methods=["DELETE"])
def delete_file(fid):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone()
        if row:
            (UPLOAD_DIR / row["stored_name"]).unlink(missing_ok=True)
            conn.execute("DELETE FROM files WHERE id=?", (fid,))
    return jsonify({"ok": True})


# ---------- Анализатор ----------
@app.route("/api/analyze")
def analyze_api():
    return jsonify(analyzer.analyze())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
