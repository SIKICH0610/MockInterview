"""Report emails through Microsoft Graph, sent from the school's official mailbox.

Setup (see DEPLOY.md): IT registers an app in Azure (public client flows on,
delegated Mail.Send + offline_access [+ Mail.Send.Shared for a shared mailbox]),
the server gets MI_MS_CLIENT_ID and MI_MS_TENANT_ID, and an admin connects the
mailbox once on Admin -> 发件邮箱 by signing in with a code at microsoft.com/devicelogin.
No password or client secret is stored; the refresh token is encrypted in the DB.
"""

import base64
import datetime as dt
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from cryptography.fernet import Fernet, InvalidToken

EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")
# Graph's sendMail takes attachments inline up to ~4 MB per request (base64 adds a third).
MAX_ATTACH_BYTES = 2_800_000


class MailError(Exception):
    pass


class NeedsReconnect(MailError):
    """The stored sign-in no longer works (password changed, expired, revoked)."""


# ---------- addresses / text ----------

def split_emails(text):
    """'a@x.com; B@y.com, a@x.com' -> (['a@x.com', 'B@y.com'], ['bad tokens'])."""
    good, bad, seen = [], [], set()
    for tok in re.split(r"[,;\s]+", text or ""):
        tok = tok.strip().strip("<>")
        if not tok:
            continue
        if not EMAIL_RE.match(tok):
            bad.append(tok)
            continue
        if tok.lower() not in seen:
            seen.add(tok.lower())
            good.append(tok)
    return good, bad


def fill(template, values):
    """Replace {name}-style placeholders; unknown braces are left as typed."""
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), template or "")


def default_bcc():
    return os.environ.get("MI_MAIL_BCC", "").strip()


# ---------- configuration ----------

def _cfg():
    return {
        "client_id": os.environ.get("MI_MS_CLIENT_ID", "").strip(),
        "tenant_id": os.environ.get("MI_MS_TENANT_ID", "").strip(),
        "login": os.environ.get("MI_MS_LOGIN_BASE", "https://login.microsoftonline.com").rstrip("/"),
        "graph": os.environ.get("MI_MS_GRAPH_BASE", "https://graph.microsoft.com").rstrip("/"),
    }


def is_configured():
    c = _cfg()
    return bool(c["client_id"] and c["tenant_id"])


def _scopes(sender):
    s = ["https://graph.microsoft.com/Mail.Send", "https://graph.microsoft.com/User.Read", "offline_access"]
    if sender:
        s.append("https://graph.microsoft.com/Mail.Send.Shared")
    return " ".join(s)


# ---------- token encryption ----------

def _fernet():
    from ..auth import _secret

    secret = _secret()
    if isinstance(secret, str):
        secret = secret.encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"mail-token:" + secret).digest()))


def _enc(text):
    return _fernet().encrypt(text.encode()).decode() if text else ""


def _dec(text):
    if not text:
        return ""
    try:
        return _fernet().decrypt(text.encode()).decode()
    except (InvalidToken, ValueError):
        return ""  # MI_SECRET_KEY changed -> treated as not connected


# ---------- HTTP ----------

def _request(method, url, data=None, headers=None, form=False):
    body = None
    headers = dict(headers or {})
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    except urllib.error.URLError as e:
        raise MailError(f"cannot reach Microsoft: {e.reason}") from e
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {"raw": raw[:300].decode("utf-8", "replace")}
    return status, payload


def _token_url():
    c = _cfg()
    return f"{c['login']}/{urllib.parse.quote(c['tenant_id'])}/oauth2/v2.0/token"


def _graph_error(payload):
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):
        return f"{err.get('code', '')}: {err.get('message', '')}".strip(": ")
    if isinstance(err, str):
        return f"{err}: {payload.get('error_description', '')}".split("\r\n")[0]
    return str(payload)[:300]


# ---------- the stored connection ----------

def _row(db, lock=False):
    from ..models import MailAccount

    q = db.query(MailAccount).filter_by(id=1)
    if lock:
        q = q.with_for_update()
    row = q.first()
    if row is None:
        row = MailAccount(id=1)
        db.add(row)
        db.flush()
    return row


def status(db):
    """What the admin pages show."""
    from ..models import Teacher

    row = _row(db)
    connected = bool(row.refresh_token and _dec(row.refresh_token))
    by = db.get(Teacher, row.connected_by) if row.connected_by else None
    return {
        "configured": is_configured(),
        "connected": connected,
        "account": row.account,
        "sender": row.sender,
        "from_addr": (row.sender or row.account) if connected else "",
        "connected_at": row.connected_at,
        "connected_by": by.name if by else "",
        "last_error": row.last_error or "",
    }


def start_sign_in(db, sender):
    """Begin Microsoft's sign-in-with-a-code. Returns what the admin types where."""
    if not is_configured():
        raise MailError("MI_MS_CLIENT_ID / MI_MS_TENANT_ID not set on the server")
    c = _cfg()
    st, p = _request(
        "POST",
        f"{c['login']}/{urllib.parse.quote(c['tenant_id'])}/oauth2/v2.0/devicecode",
        {"client_id": c["client_id"], "scope": _scopes(sender)},
        form=True,
    )
    if st != 200 or "device_code" not in p:
        raise MailError(_graph_error(p))
    row = _row(db, lock=True)
    row.pending_code = _enc(p["device_code"])
    row.pending_sender = sender
    row.pending_until = dt.datetime.now() + dt.timedelta(seconds=int(p.get("expires_in", 900)))
    db.commit()
    return {
        "user_code": p["user_code"],
        "verification_uri": p.get("verification_uri", "https://microsoft.com/devicelogin"),
        "interval": int(p.get("interval", 5)),
        "expires_in": int(p.get("expires_in", 900)),
    }


def poll_sign_in(db, teacher_id):
    """-> 'pending' | 'slow_down' | 'ok' | 'expired' | 'declined' | 'none', plus an error text."""
    row = _row(db, lock=True)
    code = _dec(row.pending_code)
    if not code:
        db.commit()
        return "none", ""
    if row.pending_until and row.pending_until < dt.datetime.now():
        row.pending_code = ""
        db.commit()
        return "expired", ""
    c = _cfg()
    st, p = _request(
        "POST",
        _token_url(),
        {"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "client_id": c["client_id"], "device_code": code},
        form=True,
    )
    if st != 200:
        err = p.get("error", "")
        if err in ("authorization_pending", "slow_down"):
            db.commit()
            return ("pending" if err == "authorization_pending" else "slow_down"), ""
        row.pending_code = ""
        db.commit()
        if err == "expired_token":
            return "expired", ""
        if err in ("authorization_declined", "access_denied"):
            return "declined", _graph_error(p)
        return "error", _graph_error(p)

    access = p["access_token"]
    gs, me = _request("GET", f"{c['graph']}/v1.0/me?$select=mail,userPrincipalName", headers={"Authorization": f"Bearer {access}"})
    account = (me.get("mail") or me.get("userPrincipalName") or "") if gs == 200 else ""
    row.account = account
    row.sender = row.pending_sender or ""
    row.access_token = _enc(access)
    row.refresh_token = _enc(p.get("refresh_token", ""))
    row.expires_at = dt.datetime.now() + dt.timedelta(seconds=int(p.get("expires_in", 3600)))
    row.pending_code = ""
    row.connected_by = teacher_id
    row.connected_at = dt.datetime.now()
    row.last_error = ""
    db.commit()
    if not row.refresh_token:
        return "error", "no refresh token returned (offline_access permission missing?)"
    return "ok", ""


def disconnect(db):
    row = _row(db, lock=True)
    row.access_token = row.refresh_token = row.pending_code = ""
    row.expires_at = None
    row.last_error = ""
    db.commit()


def _access_token(db):
    """A valid access token, refreshing (and storing the rotated refresh token) when needed.
    The row lock keeps two workers from refreshing at once."""
    row = _row(db, lock=True)
    access = _dec(row.access_token)
    if access and row.expires_at and row.expires_at > dt.datetime.now() + dt.timedelta(seconds=120):
        db.commit()
        return access, row.sender
    refresh = _dec(row.refresh_token)
    if not refresh:
        db.commit()
        raise NeedsReconnect("mailbox not connected")
    c = _cfg()
    st, p = _request(
        "POST",
        _token_url(),
        {"grant_type": "refresh_token", "client_id": c["client_id"], "refresh_token": refresh, "scope": _scopes(row.sender)},
        form=True,
    )
    if st != 200:
        msg = _graph_error(p)
        if p.get("error") in ("invalid_grant", "interaction_required", "invalid_client", "unauthorized_client"):
            row.access_token = row.refresh_token = ""
            row.last_error = msg
            db.commit()
            raise NeedsReconnect(msg)
        db.commit()
        raise MailError(msg)
    row.access_token = _enc(p["access_token"])
    if p.get("refresh_token"):
        row.refresh_token = _enc(p["refresh_token"])
    row.expires_at = dt.datetime.now() + dt.timedelta(seconds=int(p.get("expires_in", 3600)))
    row.last_error = ""
    db.commit()
    return p["access_token"], row.sender


def send(db, to, bcc, subject, body, attachments):
    """Sends one email from the connected mailbox. attachments: [(filename, bytes)].
    BCC recipients are hidden from the other recipients (Graph bccRecipients)."""
    if not is_configured():
        raise MailError("MI_MS_CLIENT_ID / MI_MS_TENANT_ID not set on the server")
    total = sum(len(d) for _, d in attachments)
    if total > MAX_ATTACH_BYTES:
        raise MailError(f"attachments too large ({total // 1024} KB, limit {MAX_ATTACH_BYTES // 1024} KB)")
    token, sender = _access_token(db)
    msg = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body},
        "toRecipients": [{"emailAddress": {"address": a}} for a in to],
        "bccRecipients": [{"emailAddress": {"address": a}} for a in bcc],
        "attachments": [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": name,
                "contentType": "application/pdf",
                "contentBytes": base64.b64encode(data).decode(),
            }
            for name, data in attachments
        ],
    }
    if sender:
        msg["from"] = {"emailAddress": {"address": sender}}
    c = _cfg()
    path = f"/v1.0/users/{urllib.parse.quote(sender)}/sendMail" if sender else "/v1.0/me/sendMail"
    st, p = _request(
        "POST",
        c["graph"] + path,
        {"message": msg, "saveToSentItems": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    if st not in (200, 202):
        raise MailError(f"HTTP {st} {_graph_error(p)}")


def keep_alive(db):
    """Refresh the stored sign-in now (run daily by deploy/mockinterview-mailrefresh.timer),
    so a long break between sessions never lets it expire from disuse.
    -> 'not connected' | 'refreshed'; raises NeedsReconnect / MailError."""
    if not is_configured() or not status(db)["connected"]:
        db.commit()
        return "not connected"
    row = _row(db, lock=True)
    row.expires_at = None  # force a refresh
    db.commit()
    _access_token(db)
    return "refreshed"
