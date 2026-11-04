"""Анализатор проектов: собирает статистику и выдаёт рекомендации."""
from datetime import datetime
from database import get_conn, rows_to_list


def analyze():
    now = datetime.now()
    with get_conn() as conn:
        projects = rows_to_list(conn.execute("SELECT * FROM projects ORDER BY id"))
        tasks = rows_to_list(conn.execute("SELECT * FROM tasks"))
        files = rows_to_list(conn.execute("SELECT * FROM files"))

    def parse(dt_str):
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return None

    report = []
    for p in projects:
        pt = [t for t in tasks if t["project_id"] == p["id"]]
        open_t = [t for t in pt if t["status"] == "open"]
        done_t = [t for t in pt if t["status"] == "done"]
        overdue = [t for t in open_t
                   if parse(t["due_date"]) and parse(t["due_date"]) < now]
        upcoming = [t for t in open_t
                    if parse(t["due_date"]) and 0 <= (parse(t["due_date"]) - now).total_seconds() <= 72 * 3600]
        high = [t for t in open_t if t["priority"] == "high"]
        no_due = [t for t in open_t if not t["due_date"]]
        files_count = sum(1 for f in files
                          if any(t["id"] == f["task_id"] for t in pt))
        completion = round(100 * len(done_t) / len(pt)) if pt else 0

        # Простейшие рекомендации
        recs = []
        if not pt:
            recs.append("В проекте нет задач — добавьте первые задачи.")
        if overdue:
            recs.append(f"Просрочено задач: {len(overdue)}. Разберите их в первую очередь.")
        if high:
            recs.append(f"Высокий приоритет без внимания: {len(high)} шт.")
        if no_due:
            recs.append(f"У {len(no_due)} задач нет даты напоминания — назначьте сроки.")
        if completion >= 80 and pt:
            recs.append("Проект почти завершён — можно планировать закрытие.")

        report.append({
            "project": p,
            "total": len(pt), "open": len(open_t), "done": len(done_t),
            "overdue": len(overdue), "upcoming": len(upcoming),
            "high_priority": len(high), "files": files_count,
            "completion": completion, "recommendations": recs,
            "overdue_tasks": overdue, "upcoming_tasks": upcoming,
        })

    total_files_size = sum(f["size"] or 0 for f in files)
    summary = {
        "projects": len(projects),
        "tasks": len(tasks),
        "open_tasks": sum(1 for t in tasks if t["status"] == "open"),
        "overdue": sum(1 for r in report for _ in r["overdue_tasks"]),
        "files": len(files),
        "files_size": total_files_size,
    }
    return {"summary": summary, "projects": report}
