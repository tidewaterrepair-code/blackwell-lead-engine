"""Request dependencies: DB session, current user/org, CSRF guard, feature gates, rate limits."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..accounts import primary_membership
from ..db import new_session
from ..models import Membership, Org, User
from ..plans import Plan, effective_plan, has_feature

CSRF_HEADER = "x-pegasus"


def get_db():
    session = new_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def csrf_guard(request: Request) -> None:
    """Unsafe API calls must carry a custom header, which cross-site forms and simple requests can't set."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(403, "Missing X-Pegasus header.")


@dataclass
class Ctx:
    user: User
    org: Org
    membership: Membership
    plan: Plan

    def feature(self, name: str) -> bool:
        return has_feature(self.org, name)

    @property
    def is_admin_role(self) -> bool:
        return self.membership.role in ("owner", "admin")


def current_ctx(request: Request, db: Session = Depends(get_db)) -> Ctx:
    user_id = request.session.get("uid")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(401, "Sign in to continue.")
    membership = primary_membership(db, user, request.session.get("org"))
    if membership is None:
        raise HTTPException(403, "You're not part of any team yet.")
    org = db.get(Org, membership.org_id)
    return Ctx(user=user, org=org, membership=membership, plan=effective_plan(org))


def require_feature(name: str):
    def check(ctx: Ctx = Depends(current_ctx)) -> Ctx:
        if not ctx.feature(name):
            raise HTTPException(402, {"upgrade": True, "feature": name,
                                      "message": "That's included in a higher plan."})
        return ctx

    return check


def require_org_admin(ctx: Ctx = Depends(current_ctx)) -> Ctx:
    if not ctx.is_admin_role:
        raise HTTPException(403, "Only team owners and admins can do that.")
    return ctx


def require_platform_admin(ctx: Ctx = Depends(current_ctx)) -> Ctx:
    if not ctx.user.is_admin:
        raise HTTPException(404)
    return ctx


_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(bucket: str, limit: int, per_seconds: int):
    """Tiny in-process sliding-window limiter (per client IP) for auth endpoints."""

    def check(request: Request) -> None:
        ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
        key = f"{bucket}:{ip}"
        now = time.monotonic()
        q = _hits[key]
        while q and q[0] < now - per_seconds:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
        q.append(now)

    return check
