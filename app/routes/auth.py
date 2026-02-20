from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError

from app.core.deps import clear_session, redirect, set_session
from app.core.security import verify_password, hash_password
from app.db.session import SessionLocal

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Campos possíveis de senha no seu User
PASSWORD_FIELDS = ("password_hash", "hashed_password", "senha_hash", "password", "senha")


def _import_user_model():
    """
    Tenta achar o User model sem quebrar o projeto:
    - app.db.models (se existir)
    - app.models.user (muito comum)
    - app.models (caso exporte User no __init__.py)
    """
    try:
        from app.db.models import User  # type: ignore
        return User
    except Exception:
        pass

    try:
        from app.models.user import User  # type: ignore
        return User
    except Exception:
        pass

    try:
        from app.models import User  # type: ignore
        return User
    except Exception:
        pass

    raise RuntimeError(
        "Não encontrei o model User. Procure onde está seu User: "
        "app/db/models.py ou app/models/user.py ou app/models/__init__.py"
    )


def _get_password_value(user) -> Optional[str]:
    for field in PASSWORD_FIELDS:
        if hasattr(user, field):
            val = getattr(user, field)
            if val is not None:
                return str(val)
    return None


def _get_user_id(user) -> str:
    for field in ("id", "user_id", "uid"):
        if hasattr(user, field):
            val = getattr(user, field)
            if val is not None:
                return str(val)
    raise RuntimeError("User sem campo de id (id/user_id/uid).")


# =========================
# LOGIN
# =========================
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
def login_action(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    User = _import_user_model()

    email_norm = (email or "").strip().lower()
    password_in = (password or "").strip()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email_norm).first()  # type: ignore[attr-defined]
        if not user:
            return redirect("/login", kind="error", message="Email ou senha inválidos.", request=request)

        stored_hash = _get_password_value(user)
        if not stored_hash:
            return redirect("/login", kind="error", message="Conta sem senha configurada.", request=request)

        if not verify_password(password_in, stored_hash):
            return redirect("/login", kind="error", message="Email ou senha inválidos.", request=request)

        uid = _get_user_id(user)
        resp = redirect("/app", kind="success", message="Bem-vindo(a) de volta!", request=request)
        set_session(resp, uid)
        return resp
    finally:
        db.close()


# =========================
# SIGNUP (CADASTRO)
# =========================
@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@router.post("/signup")
def signup_action(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    """
    Cadastro simples e seguro:
    - normaliza email
    - salva password_hash usando pbkdf2_sha256
    - auto-login após criar a conta (melhor UX pro SaaS)
    """
    User = _import_user_model()

    email_norm = (email or "").strip().lower()
    password_in = (password or "").strip()

    if not email_norm or not password_in:
        return redirect("/signup", kind="error", message="Preencha email e senha.", request=request)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email_norm).first()  # type: ignore[attr-defined]
        if existing:
            return redirect("/login", kind="error", message="Este email já está cadastrado. Faça login.", request=request)

        u = User(  # type: ignore[call-arg]
            email=email_norm,
            password_hash=hash_password(password_in),
            is_pro=False,
        )
        db.add(u)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return redirect("/login", kind="error", message="Este email já está cadastrado. Faça login.", request=request)

        # ✅ auto-login
        uid = _get_user_id(u)
        resp = redirect("/app", kind="success", message="Conta criada! Bem-vindo(a)!", request=request)
        set_session(resp, uid)
        return resp
    finally:
        db.close()


# =========================
# LOGOUT
# =========================
@router.get("/logout")
def logout(request: Request):
    resp = redirect("/login", kind="success", message="Você saiu da conta.", request=request)
    clear_session(resp)
    return resp
