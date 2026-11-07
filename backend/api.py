"""HTTP API for the School Hero mini app."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated, Any, Iterator, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field

from .config import Settings
from .db import connect
from . import admin, joins, registration
from .security import AuthError, Identity, identity_from_request
from .service import (
    archive_challenge,
    award_student_by_teacher,
    batch_review_completions,
    build_state,
    buy_item,
    create_challenge,
    ensure_user,
    equip_item,
    get_school_catalog,
    search_cities,
    join_school_class,
    lookup_class_by_code,
    remove_student,
    reset_demo,
    restore_student,
    EXCLUDED_MESSAGE,
    is_excluded,
    set_profile_name,
    review_completion,
    save_onboarding,
    submit_challenge,
    switch_role,
)


# SQLite integers are 64-bit: bigger ids would overflow (500) instead of 404.
MAX_ID = 2**62
IdPath = Annotated[int, Path(ge=1, le=MAX_ID)]
Id = Annotated[int, Field(ge=1, le=MAX_ID)]
# 0 / null mean "not chosen" for optional class ids (kept for old clients).
OptionalClassId = Annotated[int | None, Field(ge=0, le=MAX_ID)]


class RoleBody(BaseModel):
    role: str


class SubmitBody(BaseModel):
    # Exact rules (3-1000 chars after trim, http(s) link up to 500) are checked
    # in service.submit_challenge with readable 400 messages; these are caps.
    proof: str = Field(default="", max_length=4000)
    proof_url: str = Field(default="", max_length=2000)
    # Photo uploaded earlier with POST /api/uploads (required for photo tasks).
    upload_id: int | None = Field(default=None, ge=1, le=2**62)


class BatchReviewBody(BaseModel):
    completion_ids: list[Id] = Field(min_length=1, max_length=100)
    action: Literal["approve", "reject"]
    reason: str = Field(default="", max_length=200)


class ReviewBody(BaseModel):
    action: Literal["approve", "reject"]
    reason: str = Field(default="", max_length=200)


class CheckCodeBody(BaseModel):
    code: str = Field(default="", max_length=32)


class ChallengeBody(BaseModel):
    title: str = Field(min_length=3, max_length=80)
    description: str = Field(default="", max_length=320)
    category: str
    xp: int = Field(ge=10, le=300)
    kind: str
    deadline: str = ""
    subject: str = Field(default="Общее", max_length=60)
    # Own subject name when ``subject`` is "Другое".
    subject_other: str = Field(default="", max_length=40)
    proof_type: str = Field(default="text", max_length=20)
    class_id: OptionalClassId = None


class RewardStudentBody(BaseModel):
    student_id: Id
    amount: int = Field(default=50, ge=10, le=300)
    reason: str = Field(min_length=3, max_length=120)


class EquipBody(BaseModel):
    key: str
    item_id: str


class BuyBody(BaseModel):
    item_id: str


class JoinSchoolBody(BaseModel):
    invite_code: str = Field(default="", max_length=32)
    class_id: OptionalClassId = None


class NewClassBody(BaseModel):
    name: str = Field(min_length=1, max_length=12)
    weekly_goal: int = Field(default=1600, ge=100, le=20000)


class UpdateClassBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=12)
    weekly_goal: int | None = Field(default=None, ge=100, le=20000)


class NewSchoolBody(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    city: str = Field(min_length=2, max_length=60)
    # IANA zone from the supported list (state.timezones); empty: Moscow.
    timezone: str = Field(default="", max_length=40)
    classes: list[NewClassBody] = Field(min_length=1, max_length=40)
    # Name of one of the new classes the director leads as a teacher; empty: none.
    teach_class: str | None = Field(default=None, max_length=12)


class TeachBody(BaseModel):
    # Class of the school the director leads; null stops leading a class.
    class_id: OptionalClassId = None


class ViewBody(BaseModel):
    view: Literal["director", "teacher"]


class SchoolTimezoneBody(BaseModel):
    timezone: str = Field(max_length=40)


class CodeResetBody(BaseModel):
    kind: str = Field(max_length=10)
    # teacher code only: also take the class away from teachers who joined
    disconnect_teachers: bool = False


class JoinDecisionBody(BaseModel):
    action: Literal["approve", "decline"]


class SchoolStatusBody(BaseModel):
    status: str = Field(max_length=10)
    # Optional reason of a rejection; the school director sees it.
    reason: str = Field(default="", max_length=200)


class DeleteSchoolBody(BaseModel):
    # The school name typed by the admin: must match exactly.
    confirm_name: str = Field(max_length=120)


class BlockUserBody(BaseModel):
    reason: str = Field(default="", max_length=200)


class SetAdminBody(BaseModel):
    enabled: bool


class RemoveStudentBody(BaseModel):
    reason: str = Field(default="", max_length=120)


class NameBody(BaseModel):
    first_name: str = Field(min_length=2, max_length=24)
    last_name: str = Field(default="", max_length=32)


class OnboardingBody(BaseModel):
    first_name: str = Field(min_length=2, max_length=24)
    last_name: str = Field(default="", max_length=32)
    avatar: dict[str, str] = Field(default_factory=dict)
    invite_code: str = Field(default="", max_length=32)
    class_id: OptionalClassId = None


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
    # One connection per request. FastAPI may open it in one worker thread
    # and run the endpoint in another, so the thread check is off; the
    # connection is never shared between requests or used concurrently.
    conn = connect(settings.db_path, check_same_thread=False)
    try:
        try:
            identity = identity_from_request(init_data, client_id, settings)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        user = ensure_user(conn, identity, settings)
        if admin.is_blocked(user, settings):
            raise HTTPException(
                status_code=403,
                detail=admin.BLOCKED_MESSAGE,
                headers={"X-Access-Blocked": "1"},
            )
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
    result: dict[str, Any] = {
        "status": "ok",
        "mode": settings.app_mode,
    }
    if settings.sandbox_mode:
        result["boot_id"] = getattr(request.app.state, "boot_id", None)
    return result


@router.get("/state")
def state(ctx: Context = Depends(get_context)) -> dict[str, Any]:
    ctx.conn.commit()
    return build_state(ctx.conn, ctx.user, ctx.settings)


@router.post("/school/check-code")
def school_check_code(
    payload: CheckCodeBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    # POST body, not a query string: invite codes must not land in access logs.
    registration.guard_code_attempts(ctx.settings, int(ctx.user["id"]))
    info = lookup_class_by_code(ctx.conn, payload.code)
    if info and info["kind"] == "student" and is_excluded(
        ctx.conn, int(ctx.user["id"]), int(info["class_id"])
    ):
        return {"valid": False, "detail": EXCLUDED_MESSAGE}
    if not info:
        registration.register_code_failure(ctx.settings, int(ctx.user["id"]))
        return {
            "valid": False,
            "detail": "Код приглашения не найден. Уточните код у классного руководителя или выберите школу вручную.",
        }
    return info


@router.get("/school/catalog")
def school_catalog(
    city: str = "",
    q: str = "",
    limit: Annotated[int, Query(ge=-1_000_000, le=1_000_000)] = 500,
    only_cities: bool = False,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    ctx: Context = Depends(get_context),
) -> dict[str, Any]:
    return get_school_catalog(
        ctx.conn, city=city, query=q, limit=limit, only_cities=only_cities, offset=offset
    )


@router.get("/school/cities")
def school_cities(
    q: str = "",
    limit: Annotated[int, Query(ge=-1000, le=1000)] = 10,
    ctx: Context = Depends(get_context),
) -> dict[str, Any]:
    return search_cities(ctx.conn, q, limit)


class SandboxAdminBody(BaseModel):
    enabled: bool


@router.post("/sandbox/admin")
def sandbox_admin(
    payload: SandboxAdminBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    """Sandbox only: toggle the platform admin role of the test user."""
    registration.set_sandbox_admin(ctx.conn, ctx.user, ctx.settings, payload.enabled)
    ctx.conn.commit()
    ctx.user = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (ctx.user["id"],)).fetchone()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/school/join")
def school_join(
    payload: JoinSchoolBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    res = join_school_class(
        ctx.conn,
        ctx.user,
        ctx.settings,
        class_id=payload.class_id,
        invite_code=payload.invite_code,
    )
    ctx.conn.commit()
    return res


@router.post("/school/create")
def school_create(
    payload: NewSchoolBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    school_id = registration.create_school(
        ctx.conn, ctx.user, ctx.settings, payload.model_dump()
    )
    ctx.conn.commit()
    return {"school_id": school_id, "state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/school/{school_id}/teach")
def school_teach(
    school_id: IdPath, payload: TeachBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    registration.set_teaching_class(
        ctx.conn, ctx.user, ctx.settings, school_id, payload.class_id or None
    )
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/school/{school_id}/classes")
def school_add_class(
    school_id: IdPath, payload: NewClassBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    registration.add_class(
        ctx.conn, ctx.user, ctx.settings, school_id, payload.name, payload.weekly_goal
    )
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.patch("/school/{school_id}")
def school_update(
    school_id: IdPath, payload: SchoolTimezoneBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    registration.set_school_timezone(
        ctx.conn, ctx.user, ctx.settings, school_id, payload.timezone
    )
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/school/{school_id}/select")
def school_select(school_id: IdPath, ctx: Context = Depends(get_context)) -> dict[str, Any]:
    registration.select_school(ctx.conn, ctx.user, ctx.settings, school_id)
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.patch("/school/classes/{class_id}")
def school_update_class(
    class_id: IdPath, payload: UpdateClassBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    registration.update_class(
        ctx.conn, ctx.user, ctx.settings, class_id, payload.name, payload.weekly_goal
    )
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.delete("/school/classes/{class_id}")
def school_delete_class(class_id: IdPath, ctx: Context = Depends(get_context)) -> dict[str, Any]:
    registration.delete_class(ctx.conn, ctx.user, ctx.settings, class_id)
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/school/classes/{class_id}/codes")
def school_reset_code(
    class_id: IdPath, payload: CodeResetBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    registration.reset_code(
        ctx.conn, ctx.user, ctx.settings, class_id, payload.kind, payload.disconnect_teachers
    )
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/school/classes/{class_id}/teachers/{teacher_id}/disconnect")
def school_disconnect_teacher(
    class_id: IdPath, teacher_id: IdPath, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    registration.disconnect_teacher(ctx.conn, ctx.user, ctx.settings, class_id, teacher_id)
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/join-requests/cancel")
def join_request_cancel(ctx: Context = Depends(get_context)) -> dict[str, Any]:
    joins.cancel_join_request(ctx.conn, ctx.user)
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/join-requests/{request_id}")
def join_request_decide(
    request_id: IdPath, payload: JoinDecisionBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    result = joins.decide_join_request(
        ctx.conn, ctx.user, ctx.settings, request_id, payload.action
    )
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings), "result": result}


@router.post("/admin/schools/{school_id}/status")
def admin_school_status(
    school_id: IdPath, payload: SchoolStatusBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    registration.set_school_status(
        ctx.conn, ctx.user, ctx.settings, school_id, payload.status, payload.reason
    )
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.get("/admin/schools")
def admin_schools(
    status: Annotated[str, Query(max_length=10)] = "",
    q: Annotated[str, Query(max_length=80)] = "",
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = admin.PAGE_LIMIT,
    ctx: Context = Depends(get_context),
) -> dict[str, Any]:
    return admin.list_schools(ctx.conn, ctx.user, ctx.settings, status, q, offset, limit)


@router.get("/admin/schools/{school_id}")
def admin_school_detail(school_id: IdPath, ctx: Context = Depends(get_context)) -> dict[str, Any]:
    return admin.school_detail(ctx.conn, ctx.user, ctx.settings, school_id)


@router.post("/admin/schools/{school_id}/delete")
def admin_school_delete(
    school_id: IdPath, payload: DeleteSchoolBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    deleted = admin.delete_school(
        ctx.conn, ctx.user, ctx.settings, school_id, payload.confirm_name
    )
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings), "deleted": deleted}


@router.get("/admin/users")
def admin_users(
    q: Annotated[str, Query(max_length=80)] = "",
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = admin.PAGE_LIMIT,
    blocked: bool = False,
    ctx: Context = Depends(get_context),
) -> dict[str, Any]:
    return admin.list_users(ctx.conn, ctx.user, ctx.settings, q, offset, limit, blocked)


@router.post("/admin/users/{user_id}/block")
def admin_user_block(
    user_id: IdPath, payload: BlockUserBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    return {"user": admin.block_user(ctx.conn, ctx.user, ctx.settings, user_id, payload.reason)}


@router.post("/admin/users/{user_id}/admin")
def admin_user_admin(
    user_id: IdPath, payload: SetAdminBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    user = admin.set_admin(ctx.conn, ctx.user, ctx.settings, user_id, payload.enabled)
    ctx.user = ctx.conn.execute("SELECT * FROM users WHERE id = ?", (ctx.user["id"],)).fetchone()
    return {"user": user, "state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/admin/users/{user_id}/unblock")
def admin_user_unblock(user_id: IdPath, ctx: Context = Depends(get_context)) -> dict[str, Any]:
    return {"user": admin.unblock_user(ctx.conn, ctx.user, ctx.settings, user_id)}


@router.post("/profile/view")
def profile_view(payload: ViewBody, ctx: Context = Depends(get_context)) -> dict[str, Any]:
    registration.set_view(ctx.conn, ctx.user, ctx.settings, payload.view)
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/profile/name")
def profile_name(payload: NameBody, ctx: Context = Depends(get_context)) -> dict[str, Any]:
    set_profile_name(ctx.conn, ctx.user, payload.model_dump())
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/onboarding")
def onboarding(
    payload: OnboardingBody, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    save_onboarding(
        ctx.conn,
        ctx.user,
        ctx.settings,
        {
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "avatar": payload.avatar,
            "invite_code": payload.invite_code,
            "class_id": payload.class_id,
        },
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
    challenge_id: IdPath,
    payload: SubmitBody,
    ctx: Context = Depends(get_context),
) -> dict[str, Any]:
    result = submit_challenge(
        ctx.conn,
        ctx.user,
        ctx.settings,
        challenge_id,
        payload.proof,
        payload.proof_url,
        payload.upload_id,
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
    challenge_id: IdPath, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    archive_challenge(ctx.conn, ctx.user, ctx.settings, challenge_id)
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}



@router.post("/reviews/batch")
def batch_review(
    payload: BatchReviewBody,
    ctx: Context = Depends(get_context),
) -> dict[str, Any]:
    result = batch_review_completions(
        ctx.conn,
        ctx.user,
        ctx.settings,
        payload.completion_ids,
        payload.action,
        payload.reason,
    )
    ctx.conn.commit()
    return {
        "state": build_state(ctx.conn, ctx.user, ctx.settings),
        "result": result,
    }

@router.post("/reviews/{completion_id}")
def review(
    completion_id: IdPath,
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


@router.post("/teacher/students/{student_id}/remove")
def teacher_remove_student(
    student_id: IdPath,
    payload: RemoveStudentBody,
    ctx: Context = Depends(get_context),
) -> dict[str, Any]:
    remove_student(ctx.conn, ctx.user, ctx.settings, student_id, payload.reason)
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/teacher/students/{student_id}/restore")
def teacher_restore_student(
    student_id: IdPath, ctx: Context = Depends(get_context)
) -> dict[str, Any]:
    restore_student(ctx.conn, ctx.user, ctx.settings, student_id)
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


@router.post("/teacher/reward")
def teacher_reward(
    payload: RewardStudentBody,
    ctx: Context = Depends(get_context),
) -> dict[str, Any]:
    award_student_by_teacher(
        ctx.conn,
        ctx.user,
        ctx.settings,
        payload.student_id,
        payload.amount,
        payload.reason,
    )
    ctx.conn.commit()
    return {"state": build_state(ctx.conn, ctx.user, ctx.settings)}


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
