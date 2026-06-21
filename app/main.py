import os
from contextlib import asynccontextmanager
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import database, gmail, scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield


app = FastAPI(title="AutoBudget", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.get("/auth/login")
async def auth_login():
    flow = gmail.get_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    response = RedirectResponse(auth_url)
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax")
    return response


@app.get("/auth/callback")
async def auth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
):
    if error:
        return RedirectResponse("/?auth=denied")

    stored_state = request.cookies.get("oauth_state")
    flow = gmail.get_flow(state=stored_state)
    flow.fetch_token(code=code)
    gmail.save_credentials_from_flow(flow)

    # Initial sync right after connecting
    try:
        scheduler.sync_now()
    except Exception:
        pass

    response = RedirectResponse("/")
    response.delete_cookie("oauth_state")
    return response


@app.get("/auth/logout")
async def auth_logout():
    gmail.revoke()
    return RedirectResponse("/")


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    return {"authenticated": gmail.get_credentials() is not None}


@app.get("/api/stats")
async def api_stats():
    now = datetime.now()
    summary = database.get_monthly_summary(now.year, now.month)
    history = database.get_monthly_totals()
    return {"current_month": summary, "history": history}


@app.get("/api/transactions")
async def api_transactions(
    limit: int = 50,
    offset: int = 0,
    month: int = None,
    year: int = None,
):
    return database.get_transactions(limit=limit, offset=offset, month=month, year=year)


@app.post("/api/sync")
async def api_sync():
    if not gmail.get_credentials():
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        count = scheduler.sync_now()
        return {"new_transactions": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
