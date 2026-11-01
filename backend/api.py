"""HTTP API for the School Hero mini app."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated, Any, Iterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .config import Settings
from .db import connect
from .security import AuthError, Identity, identity_from_request
from .service import (
    archive_challenge,
    build_state,
    buy_item,
    create_challenge,
    ensure_user,
    equip_item,
    reset_demo,
    review_completion,
    save_onboarding,
    submit_challenge,
    switch_role,
)


class RoleBody(BaseModel):
    role: str


class SubmitBody(BaseModel):
    proof: str = Field(default="", max_length=300)


class ReviewBody(BaseModel):
    action: str
    reason: str = Field(default="", max_length=200)


class ChallengeBody(BaseModel):
    title: str = Field(min_length=3, max_length=80)
    description: str = Field(default="", max_length=320)
    category: str
    xp: int = Field(ge=10, le=200)
    kind: str
    deadline: str = ""


class EquipBody(BaseModel):
    key: str
    item_id: str


class BuyBody(BaseModel):
    item_id: str


class OnboardingBody(BaseModel):
    first_name: str = Field(min_length=2, max_length=24)
    avatar: dict[str, str] = Field(default_factory=dict)


@dataclass
class Context:
    conn: sqlite3.Connection
    settings: Settings
    identity: Identity
    user: sqlite3.Row


@contextmanager
def _context(
    request: Request,
    init_data: str | None,
    client_id: str | None,
) -> Iterator[Context]:
    settings: Settings = request.app.state.settings
    conn = connect(settings.db_path)
    try:
        try:
            identity = identity_from_request(init_data, client_id, settings)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        user = ensure_user(conn, identity, settings)
        yield Context(conn=conn, settings=settings, identity=identity, user=user)
    finally:
        conn.close()


def get_context(
    request: Request,
    init_data: Annotated[str | None, Header(alias="X-Max-Init-Data")] = None,
    client_id: Annotated[str | None, Header(alias="X-Client-Id")] = None,
) -> Iterator[Context]:
    with _context(request, init_data, client_id) as ctx:
        yield ctx


router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    return {
        "status": "ok",
        "mode": "demo" if settings.demo_mode else "max",
    }


@router.get("/state")
def state(ctx: Context = Depends(get_context)) -> dict[str, Any]:
    ctx.conn.commit()
    return build_state(ctx.conn, ctx.user, ctx.settings)


@router.post("/onboarding")
def onboarding(
    payload: OnboardingBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    save_onboarding(
        ctx.conn,
        ctx.user,
        ctx.settings,
        {"first_name": payload.first_name, "avatar": payload.avatar},
    )
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/avatar/equip")
def equip(payload: EquipBody, ctx: Context = Depends(get_context)) -> dict[str, Any]:
    equip_item(ctx.conn, ctx.user, payload.key, payload.item_id)
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/shop/buy")
def buy(payload: BuyBody, ctx: Context = Depends(get_context)) -> dict[str, Any]:
    buy_item(ctx.conn, ctx.user, payload.item_id)
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/challenges/{challenge_id}/submit")
def submit(
    challenge_id: int,
    payload: SubmitBody,
    ctx: Context = Depends(get_context),
) -> dict[str, Any]:
    result = submit_challenge(
        ctx.conn,
        ctx.user,
        ctx.settings,
        challenge_id,
        payload.proof,
    )
    ctx.conn.commit()
    return {
        "state": build_state(ctx.conn, ctx.user, ctx.settings),
        "result": result,
    }


@router.post("/challenges")
def create(
    payload: ChallengeBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    create_challenge(
        ctx.conn,
        ctx.user,
        ctx.settings,
        payload.model_dump(),
    )
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/challenges/{challenge_id}/archive")
def archive(
    challenge_id: int, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    archive_challenge(ctx.conn, ctx.user, ctx.settings, challenge_id)
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/reviews/{completion_id}")
def review(
    completion_id: int,
    payload: ReviewBody,
    ctx: Context = Depends(get_context),
) -> dict[str, Any]:
    result = review_completion(
        ctx.conn,
        ctx.user,
        ctx.settings,
        completion_id,
        payload.action,
        payload.reason,
    )
    ctx.conn.commit()
    return {
        "state": build_state(ctx.conn, ctx.user, ctx.settings),
        "result": result,
    }


@router.post("/demo/role")
def demo_role(payload: RoleBody, ctx: Context = Depends(get_context)) -> dict[str, Any]:
    switch_role(ctx.conn, ctx.user, ctx.settings, payload.role)
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/demo/reset")
def demo_reset(ctx: Context = Depends(get_context)) -> dict[str, Any]:
    reset_demo(ctx.conn, ctx.user, ctx.settings)
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}
