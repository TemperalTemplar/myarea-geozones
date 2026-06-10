"""
app/notify.py  (geozones)
Owner-facing notifications to the platform bell. When someone interacts
with your site (signs guestbook, follows, likes), the owner is pinged.
Best-effort, non-blocking. Never notifies the actor about their own action.
"""
import os, threading, requests
from app.models import User

AI_BASE_URL     = os.environ.get("MYAREA_AI_URL", "http://myarea-ai:8930")
SERVICE_API_KEY = os.environ.get("SERVICE_API_KEY", "")


def _fire(payload):
    try:
        requests.post(AI_BASE_URL + "/api/notifications/push", json=payload,
                      headers={"X-Service-Key": SERVICE_API_KEY}, timeout=3)
    except Exception:
        pass


def notify_user(user_id, ntype, title, body, url):
    """Push to a single local user by id (resolves to their oidc_sub)."""
    if not user_id:
        return
    u = User.query.get(user_id)
    sub = getattr(u, "oidc_sub", None) if u else None
    if not sub:
        return
    threading.Thread(target=_fire, args=({
        "recipient": sub, "actor": "", "type": ntype,
        "title": title, "body": body, "url": url, "app": "geozones",
    },), daemon=True).start()
