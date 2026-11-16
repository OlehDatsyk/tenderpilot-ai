"""Tasks and comments, scoped to the organisation and optionally to a tender."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from app.api.deps import DB, Ctx
from app.models import Task, TaskComment, Tender
from app.schemas.domain import CommentIn, CommentOut, TaskCreate, TaskDetail, TaskOut, TaskStatus, TaskUpdate
from app.services.access import ensure_member, get_requirement, get_task, get_tender, log_activity, user_names

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _out(db, tasks: list[Task]) -> list[TaskOut]:
    names = user_names(db, {t.assignee_id for t in tasks})
    tender_ids = {t.tender_id for t in tasks if t.tender_id}
    titles = dict(db.execute(select(Tender.id, Tender.title).where(Tender.id.in_(tender_ids))).all()) if tender_ids else {}
    ids = [t.id for t in tasks]
    counts = dict(db.execute(select(TaskComment.task_id, func.count()).where(TaskComment.task_id.in_(ids)).group_by(TaskComment.task_id)).all()) if ids else {}
    today = date.today()
    return [
        TaskOut.model_validate(t).model_copy(
            update={
                "assignee_name": names.get(t.assignee_id),
                "tender_title": titles.get(t.tender_id),
                "is_overdue": bool(t.due_date and t.due_date < today and t.status != "done"),
                "comment_count": counts.get(t.id, 0),
            }
        )
        for t in tasks
    ]


@router.get("", response_model=list[TaskOut])
def list_tasks(
    ctx: Ctx,
    db: DB,
    tender_id: uuid.UUID | None = None,
    status_: list[TaskStatus] | None = Query(None, alias="status"),
    assignee: str | None = Query(None, description="'me' or a user id"),
    overdue: bool | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> list[TaskOut]:
    stmt = select(Task).where(Task.organization_id == ctx.org_id)
    if tender_id is not None:
        get_tender(db, ctx.org_id, tender_id)
        stmt = stmt.where(Task.tender_id == tender_id)
    if status_:
        stmt = stmt.where(Task.status.in_(status_))
    if assignee == "me":
        stmt = stmt.where(Task.assignee_id == ctx.user.id)
    elif assignee:
        try:
            stmt = stmt.where(Task.assignee_id == uuid.UUID(assignee))
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid assignee.") from None
    if overdue:
        stmt = stmt.where(Task.due_date < date.today(), Task.status != "done")
    tasks = list(db.scalars(stmt.order_by(Task.due_date.asc().nulls_last(), Task.created_at.desc()).limit(limit)))
    return _out(db, tasks)


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreate, ctx: Ctx, db: DB) -> TaskOut:
    tender = get_tender(db, ctx.org_id, body.tender_id) if body.tender_id else None
    if body.requirement_id:
        req = get_requirement(db, ctx.org_id, body.requirement_id)
        if tender is None or req.tender_id != tender.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The requirement does not belong to the selected tender.")
    ensure_member(db, ctx.org_id, body.assignee_id)
    task = Task(organization_id=ctx.org_id, created_by_id=ctx.user.id, **body.model_dump())
    if task.status == "done":
        task.completed_at = datetime.now(UTC)
    db.add(task)
    log_activity(db, ctx.org_id, ctx.user.id, "task.created", f"Task '{task.title}' created", task.tender_id)
    db.commit()
    return _out(db, [task])[0]


@router.get("/{task_id}", response_model=TaskDetail)
def get_task_detail(task_id: uuid.UUID, ctx: Ctx, db: DB) -> TaskDetail:
    task = get_task(db, ctx.org_id, task_id)
    names = user_names(db, {c.author_id for c in task.comments})
    comments = [CommentOut.model_validate(c).model_copy(update={"author_name": names.get(c.author_id)}) for c in task.comments]
    return TaskDetail(**_out(db, [task])[0].model_dump(), comments=comments)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: uuid.UUID, body: TaskUpdate, ctx: Ctx, db: DB) -> TaskOut:
    task = get_task(db, ctx.org_id, task_id)
    changes = body.model_dump(exclude_unset=True, exclude={"clear_assignee", "clear_due_date"})
    if changes.get("assignee_id") is not None:
        ensure_member(db, ctx.org_id, changes["assignee_id"])
    old_status = task.status
    for key, value in changes.items():
        if value is not None:
            setattr(task, key, value)
    if body.clear_assignee:
        task.assignee_id = None
    if body.clear_due_date:
        task.due_date = None
    if task.status != old_status:
        task.completed_at = datetime.now(UTC) if task.status == "done" else None
        log_activity(db, ctx.org_id, ctx.user.id, "task.status_changed", f"Task '{task.title}' → {task.status.replace('_', ' ')}", task.tender_id)
    db.commit()
    db.refresh(task)
    return _out(db, [task])[0]


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: uuid.UUID, ctx: Ctx, db: DB) -> Response:
    task = get_task(db, ctx.org_id, task_id)
    log_activity(db, ctx.org_id, ctx.user.id, "task.deleted", f"Task '{task.title}' deleted", task.tender_id)
    db.delete(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(task_id: uuid.UUID, body: CommentIn, ctx: Ctx, db: DB) -> CommentOut:
    task = get_task(db, ctx.org_id, task_id)
    c = TaskComment(task_id=task.id, author_id=ctx.user.id, body=body.body.strip())
    db.add(c)
    db.commit()
    return CommentOut.model_validate(c).model_copy(update={"author_name": ctx.user.full_name})


@router.delete("/{task_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(task_id: uuid.UUID, comment_id: uuid.UUID, ctx: Ctx, db: DB) -> Response:
    task = get_task(db, ctx.org_id, task_id)
    c = db.scalar(select(TaskComment).where(TaskComment.id == comment_id, TaskComment.task_id == task.id))
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found.")
    if c.author_id != ctx.user.id and not ctx.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own comments.")
    db.delete(c)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
