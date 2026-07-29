"""FastAPI app: routes + templates for the Level 1 buyer app.

Kept deliberately small and server-rendered. Later steps extend this file (real
API in Step 5, agent chat in Step 6) but the Level 1 surface stays intact.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from app import agent as agent_mod
from app import services, shop
from app.auth import current_user_id, login_session, logout_session
from app.config import get_settings
from app.db import get_engine, get_session, init_db
from app.furniture_api import FurnitureAPI
from app.tools import PendingOrder, ToolContext


@dataclass
class ChatState:
    history: list[dict] = field(default_factory=list)
    display: list[dict] = field(default_factory=list)  # {"role", "text"}
    pending: PendingOrder | None = None


# Server-side chat store keyed by a per-session id (keeps big tool outputs out of
# the signed cookie). Fine for a single-process demo.
CHAT_STORE: dict[str, ChatState] = {}


def reset_chat_store() -> None:
    CHAT_STORE.clear()

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def get_api():
    """Yield a FurnitureAPI when USE_REAL_API is on, else None (Level 1 local mode)."""
    if not get_settings().use_real_api:
        yield None
        return
    api = FurnitureAPI.from_settings()
    try:
        yield api
    finally:
        api.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(get_engine()) as session:
        services.bootstrap_demo(session)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Furniture Buyer App", lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=get_settings().app_secret_key)
    register_routes(app)
    return app


def _flash(request: Request, message: str, level: str = "info") -> None:
    request.session["flash"] = {"message": message, "level": level}


def _pop_flash(request: Request) -> dict | None:
    return request.session.pop("flash", None)


def _require_user(request: Request, session: Session):
    user_id = current_user_id(request.session)
    if not user_id:
        return None
    return session.get(services.Customer, user_id)


def register_routes(app: FastAPI) -> None:
    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def home(
        request: Request,
        session: Session = Depends(get_session),
        api: FurnitureAPI | None = Depends(get_api),
    ):
        user = _require_user(request, session)
        products = shop.list_catalogue(api, session, limit=100)
        balance = shop.get_balance(api, user) if user else None
        return TEMPLATES.TemplateResponse(
            request,
            "home.html",
            {
                "products": products,
                "user": user,
                "balance": balance,
                "flash": _pop_flash(request),
            },
        )

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return TEMPLATES.TemplateResponse(
            request, "login.html", {"flash": _pop_flash(request)}
        )

    @app.post("/login")
    def login_submit(
        request: Request,
        user_id: str = Form(...),
        password: str = Form(...),
        session: Session = Depends(get_session),
    ):
        user = services.authenticate(session, user_id, password)
        if user is None:
            _flash(request, "Wrong user id or password.", "error")
            return RedirectResponse("/login", status_code=303)
        login_session(request.session, user.user_id)
        _flash(request, f"Welcome back, {user.name}.", "info")
        return RedirectResponse("/", status_code=303)

    @app.post("/logout")
    def logout(request: Request):
        logout_session(request.session)
        return RedirectResponse("/", status_code=303)

    @app.post("/buy/{item_id}")
    def buy(
        request: Request,
        item_id: str,
        quantity: int = Form(1),
        session: Session = Depends(get_session),
        api: FurnitureAPI | None = Depends(get_api),
    ):
        user = _require_user(request, session)
        if user is None:
            _flash(request, "Please log in to place an order.", "error")
            return RedirectResponse("/login", status_code=303)
        try:
            outcome = shop.place_order(api, session, user, item_id, quantity)
        except shop.ShopError as exc:
            _flash(request, str(exc), "error")
            return RedirectResponse("/", status_code=303)
        _flash(
            request,
            f"Ordered {outcome.item_id} for ${outcome.total_price:.2f}. "
            f"Balance now ${outcome.remaining_balance:.2f}.",
            "info",
        )
        return RedirectResponse("/orders", status_code=303)

    @app.get("/orders", response_class=HTMLResponse)
    def orders(
        request: Request,
        session: Session = Depends(get_session),
        api: FurnitureAPI | None = Depends(get_api),
    ):
        user = _require_user(request, session)
        if user is None:
            _flash(request, "Please log in to see your orders.", "error")
            return RedirectResponse("/login", status_code=303)
        history = shop.order_history(api, session, user)
        spent = sum(o.total_price for o in history)
        return TEMPLATES.TemplateResponse(
            request,
            "orders.html",
            {
                "user": user,
                "balance": shop.get_balance(api, user),
                "orders": history,
                "total_spent": spent,
                "flash": _pop_flash(request),
            },
        )

    # --- Step 6: agent chat -------------------------------------------------
    def _chat_state(request: Request) -> ChatState:
        sid = request.session.get("chat_sid")
        if not sid:
            sid = uuid.uuid4().hex
            request.session["chat_sid"] = sid
        return CHAT_STORE.setdefault(sid, ChatState())

    @app.get("/chat", response_class=HTMLResponse)
    def chat_page(
        request: Request,
        session: Session = Depends(get_session),
        api: FurnitureAPI | None = Depends(get_api),
    ):
        user = _require_user(request, session)
        if user is None:
            _flash(request, "Please log in to use the assistant.", "error")
            return RedirectResponse("/login", status_code=303)
        state = _chat_state(request)
        return TEMPLATES.TemplateResponse(
            request,
            "chat.html",
            {
                "user": user,
                "balance": shop.get_balance(api, user),
                "messages": state.display,
                "pending": state.pending,
                "flash": _pop_flash(request),
            },
        )

    @app.post("/chat")
    def chat_send(
        request: Request,
        message: str = Form(...),
        session: Session = Depends(get_session),
        api: FurnitureAPI | None = Depends(get_api),
    ):
        user = _require_user(request, session)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        state = _chat_state(request)
        ctx = ToolContext(api=api, session=session, user=user)
        reply, new_history = agent_mod.Agent(ctx).respond(message, state.history)
        state.history = new_history
        state.display.append({"role": "user", "text": message})
        state.display.append({"role": "assistant", "text": reply.text})
        state.pending = reply.pending_order
        return RedirectResponse("/chat", status_code=303)

    @app.post("/chat/confirm")
    def chat_confirm(
        request: Request,
        session: Session = Depends(get_session),
        api: FurnitureAPI | None = Depends(get_api),
    ):
        user = _require_user(request, session)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        state = _chat_state(request)
        if state.pending is not None:
            ctx = ToolContext(api=api, session=session, user=user)
            pending = state.pending
            state.pending = None
            try:
                outcome = agent_mod.execute_confirmed_order(ctx, pending)
                state.display.append(
                    {
                        "role": "assistant",
                        "text": (
                            f"Done — ordered {pending.quantity} x {pending.product_name} "
                            f"for ${outcome.total_price:.2f}. "
                            f"Balance now ${outcome.remaining_balance:.2f}."
                        ),
                    }
                )
            except shop.ShopError as exc:
                state.display.append({"role": "assistant", "text": str(exc)})
        return RedirectResponse("/chat", status_code=303)

    @app.post("/chat/cancel")
    def chat_cancel(request: Request, session: Session = Depends(get_session)):
        user = _require_user(request, session)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        state = _chat_state(request)
        if state.pending is not None:
            state.pending = None
            state.display.append(
                {"role": "assistant", "text": "No problem — I won't place that order."}
            )
        return RedirectResponse("/chat", status_code=303)


app = create_app()
