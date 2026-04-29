from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from gaaia.memory.store import MemoryStore
from gaaia.server.dependencies import get_current_user, get_memory
from gaaia.memory.models import User
from gaaia.services import resend_service

router = APIRouter()
_APP_URL = os.environ.get("APP_URL", "http://localhost:3000")


class CreateOrgBody(BaseModel):
    name: str
    slug: str


@router.post("")
def create_org(
    body: CreateOrgBody,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    existing = memory.get_org_by_slug(body.slug)
    if existing:
        raise HTTPException(status_code=409, detail="Slug already taken.")
    org = memory.create_org(body.name, body.slug, current_user.id)
    return {"id": org.id, "name": org.name, "slug": org.slug, "owner_id": org.owner_id}


@router.get("")
def list_my_orgs(
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> list[dict]:
    entries = memory.list_user_orgs(current_user.id)
    return [
        {
            "id": e["org"].id,
            "name": e["org"].name,
            "slug": e["org"].slug,
            "role": e["role"],
            "subscription_tier": e["org"].subscription_tier,
        }
        for e in entries
    ]


@router.get("/{org_id}/members")
def list_members(
    org_id: str,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> list[dict]:
    role = memory.get_org_role(org_id, current_user.id)
    if not role:
        raise HTTPException(status_code=403, detail="Not a member of this organisation.")
    return memory.list_org_members(org_id)


class InviteBody(BaseModel):
    email: EmailStr
    role: str = "member"


@router.post("/{org_id}/invite")
def invite_member(
    org_id: str,
    body: InviteBody,
    request: Request,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    role = memory.get_org_role(org_id, current_user.id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only admins can invite members.")
    org = memory.get_org(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found.")
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    memory.create_invitation(
        org_id=org_id, email=body.email, role=body.role,
        invited_by=current_user.id, token=token, expires_at=expires,
    )
    invite_url = f"{_APP_URL}/orgs/accept?token={token}"
    resend_service.send_org_invitation_email(
        to=body.email, org_name=org.name,
        inviter_name=current_user.display_name, invite_url=invite_url,
    )
    return {"message": f"Invitation sent to {body.email}.", "invite_url": invite_url}


@router.post("/accept")
def accept_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    ok = memory.accept_invitation(token, current_user.id)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid or expired invitation.")
    return {"message": "Joined organisation successfully."}


@router.delete("/{org_id}/members/{user_id}")
def remove_member(
    org_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    role = memory.get_org_role(org_id, current_user.id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only admins can remove members.")
    ok = memory.remove_org_member(org_id, user_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot remove this member.")
    return {"message": "Member removed."}
