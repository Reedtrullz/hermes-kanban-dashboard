import os
import sqlite3
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
KANBAN_DIR = HERMES_HOME / "kanban" / "boards"
DEFAULT_DB = HERMES_HOME / "kanban.db"
PROPOSALS_DB = HERMES_HOME / "proposals.db"
PROFILES_DIR = HERMES_HOME / "profiles"

PROPOSAL_STATUSES = ["draft", "review", "approved", "implemented", "rejected"]
PROPOSAL_LABELS = {
    "draft": "Draft", "review": "In Review", "approved": "Approved",
    "implemented": "Done", "rejected": "Rejected",
}

COLUMNS = ["todo", "ready", "in_progress", "blocked", "done", "archived"]
STATUS_LABELS = {
    "todo": "Todo", "ready": "Ready", "in_progress": "In Progress",
    "blocked": "Blocked", "done": "Done", "archived": "Archived",
}

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["STATUS_LABELS"] = STATUS_LABELS
templates.env.globals["COLUMNS"] = COLUMNS
templates.env.globals["PROPOSAL_LABELS"] = PROPOSAL_LABELS


# ── DB helpers ──────────────────────────────────────────────

def get_db_path(board: str) -> Path:
    if board == "default":
        return DEFAULT_DB
    return KANBAN_DIR / board / "kanban.db"


def list_boards() -> list[dict]:
    boards = [{"slug": "default", "name": "Default", "db": str(DEFAULT_DB)}]
    if KANBAN_DIR.is_dir():
        for d in sorted(KANBAN_DIR.iterdir()):
            if d.is_dir() and (d / "kanban.db").exists():
                boards.append({"slug": d.name, "name": d.name.replace("-", " ").title(), "db": str(d / "kanban.db")})
    return boards


def get_assignees() -> list[str]:
    assignees = []
    if PROFILES_DIR.is_dir():
        assignees = sorted(d.name for d in PROFILES_DIR.iterdir() if d.is_dir() and (d / "config.yaml").exists())
    return assignees


def get_db(board: str = "default") -> sqlite3.Connection:
    db = sqlite3.connect(str(get_db_path(board)))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def task_row(task) -> dict:
    status = task["status"]
    if status == "running":
        status = "in_progress"
    return {
        "id": task["id"], "title": task["title"], "body": task["body"] or "",
        "assignee": task["assignee"] or "", "status": status,
        "priority": task["priority"] or 0, "created_at": task["created_at"],
        "started_at": task["started_at"], "completed_at": task["completed_at"],
        "tenant": task["tenant"] or "", "consecutive_failures": task["consecutive_failures"] or 0,
        "current_run_id": task["current_run_id"], "skills": task["skills"],
    }


def get_board_context(db, board: str):
    tasks_by_status = {}
    for col in COLUMNS:
        if col == "in_progress":
            rows = db.execute("SELECT * FROM tasks WHERE status IN ('in_progress', 'running') ORDER BY priority DESC, created_at DESC").fetchall()
        else:
            rows = db.execute("SELECT * FROM tasks WHERE status = ? ORDER BY priority DESC, created_at DESC", (col,)).fetchall()
        tasks_by_status[col] = [task_row(r) for r in rows]
    profile_assignees = get_assignees()
    db_assignees = [r[0] for r in db.execute("SELECT DISTINCT assignee FROM tasks WHERE assignee IS NOT NULL AND assignee != ''").fetchall()]
    all_assignees = sorted(set(profile_assignees + db_assignees))
    return tasks_by_status, all_assignees


# ── Init proposals DB ──────────────────────────────────────

def _init_proposals_db():
    db = sqlite3.connect(str(PROPOSALS_DB))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'draft', author TEXT NOT NULL DEFAULT 'user', board TEXT NOT NULL DEFAULT 'default', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS proposal_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT NOT NULL, author TEXT NOT NULL, body TEXT NOT NULL, created_at INTEGER NOT NULL)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_prop_status ON proposals(status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_pc_proposal ON proposal_comments(proposal_id, created_at)")
    db.commit()
    db.close()

_init_proposals_db()


# ── App ────────────────────────────────────────────────────

app = FastAPI(title="Hermes Dashboard")


# ═══════════════════════════════════════════════════════════
#  PROPOSALS
# ═══════════════════════════════════════════════════════════

@app.get("/proposals", response_class=HTMLResponse)
async def proposals_list(request: Request):
    db = sqlite3.connect(str(PROPOSALS_DB)); db.row_factory = sqlite3.Row
    try:
        rows = db.execute("SELECT * FROM proposals ORDER BY updated_at DESC LIMIT 50").fetchall()
    finally:
        db.close()
    return templates.TemplateResponse(request=request, name="proposals_list.html", context={"proposals": [dict(r) for r in rows]})


@app.get("/proposals/{proposal_id}", response_class=HTMLResponse)
async def proposal_detail(request: Request, proposal_id: str):
    db = sqlite3.connect(str(PROPOSALS_DB)); db.row_factory = sqlite3.Row
    try:
        p = db.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if not p: return HTMLResponse("<h2>Not found</h2>", status_code=404)
        comments = db.execute("SELECT * FROM proposal_comments WHERE proposal_id = ? ORDER BY created_at ASC", (proposal_id,)).fetchall()
    finally:
        db.close()
    return templates.TemplateResponse(request=request, name="proposal_detail.html", context={"proposal": dict(p), "comments": [dict(c) for c in comments]})


@app.post("/api/proposals")
async def create_proposal(title: str = Form(...), body: str = Form(""), board: str = Form("default")):
    pid = f"p_{uuid.uuid4().hex[:10]}"; now = int(time.time())
    db = sqlite3.connect(str(PROPOSALS_DB))
    try:
        db.execute("INSERT INTO proposals (id, title, body, status, board, created_at, updated_at) VALUES (?, ?, ?, 'draft', ?, ?, ?)", (pid, title, body, board, now, now))
        db.commit()
    finally:
        db.close()
    return {"ok": True, "id": pid}


@app.patch("/api/proposals/{proposal_id}/status")
async def update_proposal_status(proposal_id: str, status: str = Form(...)):
    if status not in PROPOSAL_STATUSES:
        return JSONResponse({"error": f"invalid status: {status}"}, status_code=400)
    now = int(time.time())
    db = sqlite3.connect(str(PROPOSALS_DB))
    try:
        db.execute("UPDATE proposals SET status=?, updated_at=? WHERE id=?", (status, now, proposal_id))
        db.commit()
    finally:
        db.close()
    return {"ok": True}


@app.post("/api/proposals/{proposal_id}/comments")
async def add_proposal_comment(proposal_id: str, body: str = Form(...), author: str = Form("agent")):
    now = int(time.time())
    db = sqlite3.connect(str(PROPOSALS_DB))
    try:
        db.execute("INSERT INTO proposal_comments (proposal_id, author, body, created_at) VALUES (?,?,?,?)", (proposal_id, author, body, now))
        db.execute("UPDATE proposals SET updated_at=? WHERE id=?", (now, proposal_id))
        db.commit()
    finally:
        db.close()
    return {"ok": True}


@app.get("/api/proposals")
async def api_proposals_list():
    db = sqlite3.connect(str(PROPOSALS_DB)); db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute("SELECT * FROM proposals ORDER BY updated_at DESC LIMIT 50").fetchall()]
    finally:
        db.close()


@app.get("/api/proposals/{proposal_id}")
async def api_proposal_detail(proposal_id: str):
    db = sqlite3.connect(str(PROPOSALS_DB)); db.row_factory = sqlite3.Row
    try:
        p = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if not p: return JSONResponse({"error": "not found"}, status_code=404)
        comments = db.execute("SELECT * FROM proposal_comments WHERE proposal_id=? ORDER BY created_at ASC", (proposal_id,)).fetchall()
        result = dict(p); result["comments"] = [dict(c) for c in comments]
        return result
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
#  BOARD
# ═══════════════════════════════════════════════════════════

@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse("/board/default", status_code=302)


@app.get("/board/{board}", response_class=HTMLResponse)
async def board_view(request: Request, board: str, fragment: bool = False):
    db_path = get_db_path(board)
    if not db_path.exists(): return HTMLResponse(f"<h2>Board '{board}' not found</h2>", status_code=404)
    db = get_db(board)
    try:
        tasks_by_status, assignees = get_board_context(db, board)
    finally:
        db.close()
    boards = list_boards()
    tmpl = "_board.html" if fragment else "index.html"
    return templates.TemplateResponse(request=request, name=tmpl, context={"board": board, "boards": boards, "tasks_by_status": tasks_by_status, "assignees": assignees})


# ═══════════════════════════════════════════════════════════
#  REST API
# ═══════════════════════════════════════════════════════════

@app.get("/api/boards")
async def api_list_boards(): return list_boards()


@app.get("/api/tasks")
async def list_tasks(status: str | None = None, board: str = "default"):
    db = get_db(board)
    try:
        if status:
            if status == "in_progress":
                rows = db.execute("SELECT * FROM tasks WHERE status IN ('in_progress','running') ORDER BY priority DESC, created_at DESC").fetchall()
            else:
                rows = db.execute("SELECT * FROM tasks WHERE status=? ORDER BY priority DESC, created_at DESC", (status,)).fetchall()
        else:
            rows = db.execute("SELECT * FROM tasks ORDER BY priority DESC, created_at DESC").fetchall()
        return [task_row(r) for r in rows]
    finally:
        db.close()


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str, board: str = "default"):
    db = get_db(board)
    try:
        task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task: return JSONResponse({"error": "not found"}, status_code=404)
        comments = db.execute("SELECT * FROM task_comments WHERE task_id=? ORDER BY created_at ASC", (task_id,)).fetchall()
        runs = db.execute("SELECT * FROM task_runs WHERE task_id=? ORDER BY started_at DESC", (task_id,)).fetchall()
        parents = [r[0] for r in db.execute("SELECT parent_id FROM task_links WHERE child_id=?", (task_id,)).fetchall()]
        children = [r[0] for r in db.execute("SELECT child_id FROM task_links WHERE parent_id=?", (task_id,)).fetchall()]
        result = task_row(task)
        result["comments"] = [dict(c) for c in comments]
        result["runs"] = [dict(r) for r in runs]
        result["parents"] = parents; result["children"] = children
        return result
    finally:
        db.close()


@app.post("/api/tasks")
async def create_task(title: str = Form(...), body: str = Form(""), assignee: str = Form(""), priority: int = Form(0), board: str = Form("default")):
    task_id = f"t_{uuid.uuid4().hex[:12]}"; now = int(time.time())
    db = get_db(board)
    try:
        db.execute("INSERT INTO tasks (id,title,body,assignee,status,priority,created_at) VALUES (?,?,?,?,'todo',?,?)", (task_id, title, body, assignee, priority, now))
        db.commit()
    finally:
        db.close()
    return await _task_card_html(task_id, board)


@app.patch("/api/tasks/{task_id}/status")
async def update_status(task_id: str, status: str = Form(...), board: str = Form("default")):
    if status not in COLUMNS: return JSONResponse({"error": f"invalid status: {status}"}, status_code=400)
    db = get_db(board)
    try:
        now = int(time.time())
        db.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
        if status == "in_progress": db.execute("UPDATE tasks SET started_at=? WHERE id=?", (now, task_id))
        elif status == "done": db.execute("UPDATE tasks SET completed_at=? WHERE id=?", (now, task_id))
        db.commit()
    finally:
        db.close()
    return await _task_card_html(task_id, board)


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str, board: str = "default"):
    db = get_db(board)
    try:
        db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        db.execute("DELETE FROM task_links WHERE parent_id=? OR child_id=?", (task_id, task_id))
        db.execute("DELETE FROM task_comments WHERE task_id=?", (task_id,))
        db.commit()
    finally:
        db.close()
    return {"ok": True}


@app.post("/api/tasks/{task_id}/comments")
async def add_comment(task_id: str, body: str = Form(...), author: str = Form("web"), board: str = Form("default")):
    now = int(time.time())
    db = get_db(board)
    try:
        db.execute("INSERT INTO task_comments (task_id,author,body,created_at) VALUES (?,?,?,?)", (task_id, author, body, now))
        db.commit()
    finally:
        db.close()
    return {"ok": True}


async def _task_card_html(task_id: str, board: str):
    db = get_db(board)
    try:
        task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task: return HTMLResponse("", status_code=404)
        t = task_row(task)
        from fastapi import Request as _Request
        return templates.TemplateResponse(request=_Request({"type": "http", "method": "GET", "path": "/", "headers": []}), name="_task_card.html", context={"task": t, "board": board})
    finally:
        db.close()
