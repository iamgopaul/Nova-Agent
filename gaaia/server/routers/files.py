from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from gaaia.memory.store import MemoryStore
from gaaia.server.dependencies import get_current_user, get_memory
from gaaia.memory.models import User
from gaaia.services import embedding_service, file_processor

router = APIRouter()

_MAX_FILE_SIZE_MB = 25
_ALLOWED_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
}


def _uploads_dir(data_dir: Path) -> Path:
    d = data_dir / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("")
def list_files(
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> list[dict]:
    return memory.list_uploaded_files(current_user.id)


@router.post("", status_code=201)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> dict:
    content_type = file.content_type or "application/octet-stream"
    if content_type not in _ALLOWED_TYPES and not (file.filename or "").endswith((".pdf", ".txt", ".md")):
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {content_type}")

    data = await file.read()
    if len(data) > _MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {_MAX_FILE_SIZE_MB} MB limit.")

    data_dir: Path = request.app.state.settings.data_dir
    uploads = _uploads_dir(data_dir)
    safe_name = Path(file.filename or "upload").name
    dest = uploads / f"{current_user.id}_{safe_name}"
    dest.write_bytes(data)

    db_file = memory.create_uploaded_file(
        user_id=current_user.id,
        filename=safe_name,
        content_type=content_type,
        size_bytes=len(data),
        storage_path=str(dest.relative_to(data_dir)),
    )

    # Process and embed in the background
    asyncio.create_task(_process_and_embed(db_file.id, dest, content_type, current_user.id, memory))

    return {
        "id": db_file.id,
        "filename": db_file.filename,
        "size_bytes": db_file.size_bytes,
        "processed": False,
    }


async def _process_and_embed(
    file_id: str, path: Path, content_type: str, user_id: str, memory: MemoryStore
) -> None:
    chunks_text = await asyncio.to_thread(file_processor.process_file, path, content_type)
    chunks_with_embeddings = []
    for chunk in chunks_text:
        emb = await embedding_service.embed_text(chunk)
        chunks_with_embeddings.append({"content": chunk, "embedding": emb})
    memory.save_file_chunks(file_id, chunks_with_embeddings)


@router.delete("/{file_id}", status_code=204)
def delete_file(
    file_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    memory: MemoryStore = Depends(get_memory),
) -> None:
    storage_rel = memory.delete_uploaded_file(file_id, current_user.id)
    if storage_rel is None:
        raise HTTPException(status_code=404, detail="File not found.")
    data_dir: Path = request.app.state.settings.data_dir
    full_path = data_dir / storage_rel
    if full_path.exists():
        full_path.unlink(missing_ok=True)
