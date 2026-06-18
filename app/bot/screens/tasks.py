from .formatting import *

def render_tasks_home() -> Screen:
    return Screen(text="Tasks\nOperational work queue.", reply_markup=tasks_menu())

def render_task_list_page(
    session: Session,
    *,
    tasks: list[Task] | None = None,
    title: str = "Tasks",
    back_to: str = "tasks",
) -> Screen:
    current_tasks = tasks if tasks is not None else list_tasks(session)
    lines = [title, ""]
    buttons: list[tuple[str, str]] = []
    if not current_tasks:
        lines.append("No tasks yet.")
    for task in current_tasks[:15]:
        due = task.due_at.isoformat() if task.due_at else "No due date"
        model = task.model_brand.display_name if task.model_brand else "No model"
        assignee = _identity(task.assigned_to)
        lines.append(f"{task.id}. {_status_marker(task.status)} {task.title}")
        lines.append(f"   Status: {task.status} | Priority: {task.priority}")
        lines.append(f"   Model: {model} | Assigned: {assignee}")
        lines.append(f"   Due: {due}")
        buttons.append(_task_button(task))
    return Screen(text="\n".join(lines), reply_markup=task_list_menu(buttons, back_to=back_to))

def render_task_detail_page(session: Session, task_id: int) -> Screen:
    task = get_task(session, task_id)
    if task is None:
        return Screen(text="Task not found.", reply_markup=page_menu(back_to="tasks:list"))
    model = task.model_brand.display_name if task.model_brand else "No model"
    account = f"{task.account.platform} @{task.account.username}" if task.account else "No account"
    due = task.due_at.isoformat() if task.due_at else "No due date"
    completed = task.completed_at.isoformat() if task.completed_at else "Not completed"
    logs = task_audit_logs(session, task, limit=3)
    recent = [f"- {log.action} ({log.status})" for log in logs] or ["- No recent task events"]
    lines = [
        "Task Detail",
        "",
        f"Title: {task.title}",
        f"Description: {task.description or 'None'}",
        f"Status: {_status_marker(task.status)} {task.status}",
        f"Priority: {task.priority}",
        f"Model/Brand: {model}",
        f"Account: {account}",
        f"Assigned To: {_identity(task.assigned_to)}",
        f"Created By: {_identity(task.created_by)}",
        f"Due: {due}",
        f"Completed: {completed}",
        "",
        "Recent Events:",
        *recent,
    ]
    return Screen(text="\n".join(lines), reply_markup=task_detail_menu(task.id))

def render_task_assignment_page(session: Session, task_id: int) -> Screen:
    task = get_task(session, task_id)
    if task is None:
        return Screen(text="Task not found.", reply_markup=page_menu(back_to="tasks:list"))
    buttons = [
        (_identity(user), f"nav:task:{task.id}:assign:{user.id}")
        for user in active_users_for_assignment(session)
        if user.id != task.assigned_to_user_id
    ]
    lines = ["Reassign Task", "", f"Task: {task.title}", ""]
    if not buttons:
        lines.append("No active users available.")
    return Screen(text="\n".join(lines), reply_markup=task_user_choice_menu(task.id, buttons))

