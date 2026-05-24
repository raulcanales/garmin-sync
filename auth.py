import asyncio
import logging
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from garminconnect import Garmin
from pydantic import BaseModel, Field
import asyncpg

import db
import garmin_client
from garmin_client import LoginStatus
from users import UserConfig, validate_nickname, validate_user_id

logger = logging.getLogger(__name__)

MFA_TTL = timedelta(minutes=10)


@dataclass
class PendingMfa:
    user_id: str
    client: Garmin
    token_dir: str
    expires_at: datetime


_pending_mfa: dict[str, PendingMfa] = {}


class RegisterUserBody(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=32)
    nickname: str = Field(..., min_length=1, max_length=64)
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1)


class LoginUserBody(BaseModel):
    password: str = Field(..., min_length=1)
    mfa_code: str | None = None
    login_id: str | None = None


class MfaCompleteBody(BaseModel):
    login_id: str
    mfa_code: str = Field(..., min_length=1)


def _cleanup_expired_mfa() -> None:
    now = datetime.now(timezone.utc)
    expired = [key for key, item in _pending_mfa.items() if item.expires_at <= now]
    for key in expired:
        pending = _pending_mfa.pop(key, None)
        if pending is not None:
            shutil.rmtree(pending.token_dir, ignore_errors=True)


def _user_public(user: UserConfig) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "nickname": user.nickname,
        "email": user.email,
        "logged_in": user.tokens is not None,
    }


async def list_users_public() -> list[dict[str, object]]:
    users = await db.list_users()
    return [_user_public(user) for user in users]


async def register_and_login(body: RegisterUserBody) -> dict[str, object]:
    _cleanup_expired_mfa()
    try:
        user_id = validate_user_id(body.user_id)
        nickname = validate_nickname(body.nickname)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    existing = await db.get_user(user_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"user_id already exists: {user_id}")

    email = body.email.strip().lower()
    try:
        user = await db.create_user(user_id, nickname, email)
    except asyncpg.UniqueViolationError as e:
        if "users_email_idx" in str(e):
            raise HTTPException(status_code=409, detail="email already registered") from e
        raise HTTPException(status_code=409, detail=f"user_id already exists: {user_id}") from e

    try:
        return await _login_user(user, body.password)
    except HTTPException as e:
        if e.status_code == 401:
            refreshed = await db.get_user(user_id)
            if refreshed is not None and refreshed.tokens is None:
                await db.delete_user(user_id)
        raise


async def login_existing_user(user_id: str, body: LoginUserBody) -> dict[str, object]:
    _cleanup_expired_mfa()
    if body.login_id:
        return await complete_mfa(body.login_id, body.mfa_code or "")

    user = await db.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"unknown user_id: {user_id}")
    return await _login_user(user, body.password)


async def complete_mfa(login_id: str, mfa_code: str) -> dict[str, object]:
    _cleanup_expired_mfa()
    pending = _pending_mfa.pop(login_id, None)
    if pending is None:
        raise HTTPException(status_code=400, detail="login expired or invalid login_id")
    if not mfa_code.strip():
        _pending_mfa[login_id] = pending
        raise HTTPException(status_code=400, detail="mfa_code is required")

    result = await asyncio.to_thread(
        garmin_client.finish_garmin_login, pending.client, pending.token_dir, mfa_code
    )
    if result.status != LoginStatus.SUCCESS or not result.tokens:
        raise HTTPException(status_code=401, detail=result.error or "MFA login failed")

    try:
        await db.save_user_tokens(pending.user_id, result.tokens)
    except Exception as e:
        logger.exception("failed to save tokens after MFA for %s", pending.user_id)
        raise HTTPException(status_code=500, detail=f"MFA ok but token save failed: {e}") from e
    logger.info("saved Garmin tokens after MFA for user=%s", pending.user_id)
    user = await db.get_user(pending.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user disappeared during login")
    return {"status": "logged_in", **_user_public(user)}


async def delete_user(user_id: str) -> dict[str, object]:
    deleted = await db.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"unknown user_id: {user_id}")
    return {"status": "deleted", "user_id": user_id}


async def _login_user(user: UserConfig, password: str) -> dict[str, object]:
    client, token_dir, result = await asyncio.to_thread(
        garmin_client.start_garmin_login, user.email, password
    )
    if result.status == LoginStatus.MFA_REQUIRED:
        login_id = uuid.uuid4().hex
        _pending_mfa[login_id] = PendingMfa(
            user_id=user.user_id,
            client=client,
            token_dir=token_dir,
            expires_at=datetime.now(timezone.utc) + MFA_TTL,
        )
        return {
            "status": "mfa_required",
            "login_id": login_id,
            "user_id": user.user_id,
            "message": "Check your email for the Garmin MFA code, then POST the code.",
        }
    if result.status != LoginStatus.SUCCESS or not result.tokens:
        raise HTTPException(status_code=401, detail=result.error or "login failed")

    try:
        await db.save_user_tokens(user.user_id, result.tokens)
    except Exception as e:
        logger.exception("failed to save tokens for %s", user.user_id)
        raise HTTPException(status_code=500, detail=f"login ok but token save failed: {e}") from e
    logger.info("saved Garmin tokens for user=%s", user.user_id)
    refreshed = await db.get_user(user.user_id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="user disappeared during login")
    return {"status": "logged_in", **_user_public(refreshed)}


LOGIN_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Garmin Sync — Login</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    body { max-width: 32rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }
    h1 { font-size: 1.4rem; margin-bottom: 0.25rem; }
    p.sub { opacity: 0.8; margin-top: 0; }
    form { display: grid; gap: 0.75rem; margin-top: 1.5rem; }
    label { display: grid; gap: 0.25rem; font-size: 0.9rem; }
    input { padding: 0.55rem 0.65rem; font-size: 1rem; border: 1px solid #8884; border-radius: 6px; }
    button { padding: 0.65rem 1rem; font-size: 1rem; border: 0; border-radius: 6px; cursor: pointer; }
    .primary { background: #0077cc; color: #fff; }
    .hidden { display: none; }
    .msg { margin-top: 1rem; padding: 0.75rem; border-radius: 6px; }
    .ok { background: #1a7f3722; }
    .err { background: #b0002022; }
    code { font-size: 0.85em; }
  </style>
</head>
<body>
  <h1>Garmin Sync</h1>
  <p class="sub">Register an account or refresh Garmin tokens. Passwords are not stored.</p>

        <form id="login-form">
    <label>User id <small>(slug for sync API, e.g. <code>raal</code>)</small>
      <input name="user_id" required pattern="[a-z0-9][a-z0-9_-]{0,30}[a-z0-9]|[a-z0-9]" autocomplete="username">
    </label>
    <label>Nickname <small>(display name)</small>
      <input name="nickname" required maxlength="64" autocomplete="nickname">
    </label>
    <label>Garmin email
      <input name="email" type="email" required autocomplete="email">
    </label>
    <label>Garmin password
      <input name="password" type="password" required autocomplete="current-password">
    </label>
    <label id="mfa-wrap" class="hidden">MFA code from email
      <input name="mfa_code" inputmode="numeric" autocomplete="one-time-code">
    </label>
    <button type="submit" class="primary" id="submit-btn">Log in</button>
  </form>
  <div id="msg" class="msg hidden"></div>
  <script>
    const form = document.getElementById('login-form');
    const msg = document.getElementById('msg');
    const mfaWrap = document.getElementById('mfa-wrap');
    const submitBtn = document.getElementById('submit-btn');
    let loginId = null;
    let userId = null;

    function showMessage(text, ok) {
      msg.textContent = text;
      msg.className = 'msg ' + (ok ? 'ok' : 'err');
      msg.classList.remove('hidden');
    }

    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      submitBtn.disabled = true;
      const data = new FormData(form);
      userId = String(data.get('user_id') || '').trim().toLowerCase();
      const payload = {
        user_id: userId,
        nickname: String(data.get('nickname') || '').trim(),
        email: String(data.get('email') || '').trim(),
        password: String(data.get('password') || ''),
      };
      const mfaCode = String(data.get('mfa_code') || '').trim();
      try {
        let res;
        if (loginId) {
          res = await fetch('/users/' + encodeURIComponent(userId) + '/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: payload.password, login_id: loginId, mfa_code: mfaCode }),
          });
        } else {
          res = await fetch('/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          if (res.status === 409) {
            res = await fetch('/users/' + encodeURIComponent(userId) + '/login', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ password: payload.password }),
            });
          }
        }
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || JSON.stringify(body));
        if (body.status === 'mfa_required') {
          loginId = body.login_id;
          mfaWrap.classList.remove('hidden');
          submitBtn.textContent = 'Submit MFA code';
          showMessage('Enter the MFA code from your email.', true);
          return;
        }
        showMessage('Logged in as ' + body.nickname + ' (' + body.user_id + '). You can close this page.', true);
        loginId = null;
      } catch (err) {
        showMessage(String(err.message || err), false);
      } finally {
        submitBtn.disabled = false;
      }
    });
  </script>
</body>
</html>"""


def login_page() -> HTMLResponse:
    return HTMLResponse(LOGIN_PAGE)
