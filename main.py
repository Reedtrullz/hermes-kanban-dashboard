import os, sqlite3, time, uuid
from pathlib import Path
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
PROPOSALS_DB = HERMES_HOME / "proposals.db"
PROFILES_DIR = HERMES_HOME / "profiles"

PROPOSAL_STATUSES = ["draft", "review", "approved", "implemented", "rejected"]
PROPOSAL_LABELS = {
    "draft": "Draft", "review": "In Review", "approved": "Approved",
    "implemented": "Done", "rejected": "Rejected",
}

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["PROPOSAL_LABELS"] = PROPOSAL_LABELS


def get_profiles() -> list[str]:
    if PROFILES_DIR.is_dir():
        return sorted(d.name for d in PROFILES_DIR.iterdir() if d.is_dir() and (d / "config.yaml").exists())
    return []


def _init_db():
    db = sqlite3.connect(str(PROPOSALS_DB))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'draft', author TEXT NOT NULL DEFAULT 'user', board TEXT NOT NULL DEFAULT 'default', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS proposal_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT NOT NULL, author TEXT NOT NULL, body TEXT NOT NULL, created_at INTEGER NOT NULL)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_prop_status ON proposals(status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_pc_proposal ON proposal_comments(proposal_id, created_at)")
    db.commit(); db.close()
_init_db()

app = FastAPI(title="Hermes Proposals")


# ═══════════════════════════════════════════════════════════
#  PAGES
# ═══════════════════════════════════════════════════════════

@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse("/proposals", status_code=302)


@app.get("/proposals", response_class=HTMLResponse)
async def proposals_list(request: Request):
    db = sqlite3.connect(str(PROPOSALS_DB)); db.row_factory = sqlite3.Row
    try:
        rows = db.execute("SELECT * FROM proposals ORDER BY updated_at DESC LIMIT 50").fetchall()
    finally: db.close()
    return templates.TemplateResponse(request=request, name="proposals_list.html", context={"proposals": [dict(r) for r in rows], "profiles": get_profiles()})


@app.get("/proposals/{proposal_id}", response_class=HTMLResponse)
async def proposal_detail(request: Request, proposal_id: str):
    db = sqlite3.connect(str(PROPOSALS_DB)); db.row_factory = sqlite3.Row
    try:
        p = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if not p: return HTMLResponse("<h2>Not found</h2>", status_code=404)
        comments = db.execute("SELECT * FROM proposal_comments WHERE proposal_id=? ORDER BY created_at ASC", (proposal_id,)).fetchall()
    finally: db.close()
    return templates.TemplateResponse(request=request, name="proposal_detail.html", context={"proposal": dict(p), "comments": [dict(c) for c in comments], "profiles": get_profiles()})


# ═══════════════════════════════════════════════════════════
#  API
# ═══════════════════════════════════════════════════════════

@app.post("/api/proposals")
async def create_proposal(title: str = Form(...), body: str = Form(""), board: str = Form("default")):
    pid = f"p_{uuid.uuid4().hex[:10]}"; now = int(time.time())
    db = sqlite3.connect(str(PROPOSALS_DB))
    try:
        db.execute("INSERT INTO proposals (id,title,body,status,board,created_at,updated_at) VALUES (?,?,?,'draft',?,?,?)", (pid, title, body, board, now, now))
        db.commit()
    finally: db.close()
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
    finally: db.close()
    return {"ok": True}


@app.post("/api/proposals/{proposal_id}/comments")
async def add_proposal_comment(proposal_id: str, body: str = Form(...), author: str = Form("agent")):
    now = int(time.time())
    db = sqlite3.connect(str(PROPOSALS_DB))
    try:
        db.execute("INSERT INTO proposal_comments (proposal_id,author,body,created_at) VALUES (?,?,?,?)", (proposal_id, author, body, now))
        db.execute("UPDATE proposals SET updated_at=? WHERE id=?", (now, proposal_id))
        db.commit()
    finally: db.close()
    return {"ok": True}


@app.get("/api/proposals")
async def api_proposals_list():
    db = sqlite3.connect(str(PROPOSALS_DB)); db.row_factory = sqlite3.Row
    try: return [dict(r) for r in db.execute("SELECT * FROM proposals ORDER BY updated_at DESC LIMIT 50").fetchall()]
    finally: db.close()


@app.get("/api/proposals/{proposal_id}")
async def api_proposal_detail(proposal_id: str):
    db = sqlite3.connect(str(PROPOSALS_DB)); db.row_factory = sqlite3.Row
    try:
        p = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if not p: return JSONResponse({"error": "not found"}, status_code=404)
        comments = db.execute("SELECT * FROM proposal_comments WHERE proposal_id=? ORDER BY created_at ASC", (proposal_id,)).fetchall()
        result = dict(p); result["comments"] = [dict(c) for c in comments]
        return result
    finally: db.close()
