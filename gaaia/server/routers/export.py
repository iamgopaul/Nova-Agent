from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from gaaia.memory.store import MemoryStore
from gaaia.server.dependencies import get_current_user, get_memory
from gaaia.memory.models import User

router = APIRouter()


@router.get("/data")
def export_my_data(
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> StreamingResponse:
    """Download a ZIP archive containing all the user's data as JSON (GDPR export)."""
    data = memory.export_user_data(current_user.id)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "gaaia_export.json",
            json.dumps(data, indent=2, default=str),
        )

        # Separate files for readability
        zf.writestr("profile.json", json.dumps(data.get("user", {}), indent=2, default=str))
        zf.writestr("facts.json", json.dumps(data.get("facts", []), indent=2, default=str))
        zf.writestr("sessions.json", json.dumps(data.get("sessions", []), indent=2, default=str))
        zf.writestr("scheduled_tasks.json", json.dumps(data.get("scheduled_tasks", []), indent=2, default=str))
        zf.writestr("watched_topics.json", json.dumps(data.get("watched_topics", []), indent=2, default=str))

    buf.seek(0)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"gaaia_export_{ts}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
