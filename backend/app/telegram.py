"""Telegram alert channel (ADR-029). Bot token from env only; chat_id per store. Messages are HTML-escaped plain text.

`notify_pending` is called after every alert evaluation: opened incidents not yet notified get an "opened" message,
resolved ones that were announced get a "pulih" message. Failures are logged and retried on the next tick."""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Alert, Store

log = logging.getLogger("telegram")
TELEGRAM_API = "https://api.telegram.org"
_transport: httpx.AsyncBaseTransport | None = None  # tests inject a MockTransport here


async def send_message(token: str, chat_id: str, text: str) -> str | None:
    """Returns None on success, otherwise a short error string (never containing the token)."""
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0, transport=_transport) as c:
            r = await c.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
    except httpx.HTTPError as exc:
        return f"network: {type(exc).__name__}"
    if r.status_code == 200:
        return None
    try:
        desc = r.json().get("description") or ""
    except ValueError:
        desc = ""
    return f"telegram HTTP {r.status_code}: {desc}"[:200]


def _fmt(ts: datetime, tz: str) -> str:
    return ts.astimezone(ZoneInfo(tz)).strftime("%d %b %Y %H:%M")


def format_opened(a: Alert, store: Store) -> str:
    icon = "🔴" if a.severity == "critical" else "🟠"
    return (f"{icon} <b>{html.escape(store.name)}</b> — alert {html.escape(a.rule)}\n"
            f"{html.escape(a.message)}\n"
            f"Mulai: {_fmt(a.opened_at, store.timezone)} ({html.escape(store.timezone)})")


def format_resolved(a: Alert, store: Store) -> str:
    mins = int((a.resolved_at - a.opened_at).total_seconds() // 60)
    return (f"🟢 <b>{html.escape(store.name)}</b> — pulih: {html.escape(a.rule)}\n"
            f"{html.escape(a.message)}\n"
            f"Durasi: {mins} menit · selesai {_fmt(a.resolved_at, store.timezone)}")


async def notify_pending(s: AsyncSession, token: str | None) -> int:
    """Send Telegram messages for alerts of stores with a chat_id. Returns the number of messages sent. Commits."""
    if not token:
        return 0
    stores = {st.id: st for st in (await s.execute(select(Store).where(Store.telegram_chat_id.is_not(None)))).scalars()}
    if not stores:
        return 0
    rows = (await s.execute(select(Alert).where(
        Alert.store_id.in_(stores), (Alert.notified_at.is_(None)) | ((Alert.resolved_at.is_not(None)) & (Alert.resolved_notified_at.is_(None)))
    ))).scalars().all()
    now = datetime.now(timezone.utc)
    sent = 0
    for a in rows:
        st = stores[a.store_id]
        if a.notified_at is None:
            if a.resolved_at is not None:  # resolved before it was ever announced: nothing to say
                a.notified_at = a.resolved_notified_at = now
                continue
            err = await send_message(token, st.telegram_chat_id, format_opened(a, st))
            if err:
                log.warning("telegram opened-message failed for alert %s: %s", a.id, err)
                continue
            a.notified_at = now
            sent += 1
        elif a.resolved_at is not None and a.resolved_notified_at is None:
            err = await send_message(token, st.telegram_chat_id, format_resolved(a, st))
            if err:
                log.warning("telegram resolved-message failed for alert %s: %s", a.id, err)
                continue
            a.resolved_notified_at = now
            sent += 1
    await s.commit()
    return sent
