"""Task management tools — CRUD on the SQLite tasks table."""

from datetime import date, datetime

from database import get_conn


def add_task(
    title: str,
    description: str = "",
    priority: str = "medium",
    due_date: str = "",
) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (title, description, priority, due_date)
            VALUES (?, ?, ?, ?)
            """,
            (title, description, priority, due_date or None),
        )
        task_id = cur.lastrowid
    return {"success": True, "task_id": task_id, "message": f"Task #{task_id} created: {title}"}


def list_tasks(
    status: str = "pending",
    priority: str = "all",
    due_today: bool = False,
) -> dict:
    conditions = []
    params: list = []

    if status != "all":
        conditions.append("status = ?")
        params.append(status)

    if priority != "all":
        conditions.append("priority = ?")
        params.append(priority)

    if due_today:
        today = date.today().isoformat()
        conditions.append("due_date = ?")
        params.append(today)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"SELECT * FROM tasks {where} ORDER BY due_date ASC, priority DESC, id ASC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    tasks = [dict(row) for row in rows]
    return {"tasks": tasks, "count": len(tasks)}


def update_task(
    task_id: int,
    title: str = "",
    description: str = "",
    priority: str = "",
    status: str = "",
    due_date: str = "",
) -> dict:
    fields, params = [], []

    if title:
        fields.append("title = ?"); params.append(title)
    if description:
        fields.append("description = ?"); params.append(description)
    if priority:
        fields.append("priority = ?"); params.append(priority)
    if status:
        fields.append("status = ?"); params.append(status)
    if due_date is not None and due_date != "":
        fields.append("due_date = ?"); params.append(due_date or None)

    if not fields:
        return {"success": False, "message": "No fields to update"}

    fields.append("updated_at = ?")
    params.append(datetime.now().isoformat(sep=" ", timespec="seconds"))
    params.append(task_id)

    with get_conn() as conn:
        conn.execute(
            f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", params
        )
    return {"success": True, "message": f"Task #{task_id} updated"}


def delete_task(task_id: int) -> dict:
    with get_conn() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return {"success": True, "message": f"Task #{task_id} deleted"}
