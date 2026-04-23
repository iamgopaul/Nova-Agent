from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import and_, create_engine, event, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as DBSession

from nova.memory.models import Base, Fact, Folder, Message, Session


@event.listens_for(Engine, "connect", retval=False)
def _sqlite_pragma(dbapi_connection, connection_record) -> None:
    """WAL + sane sync so history survives restarts and abrupt process exit more often."""
    try:
        eng = connection_record.engine
    except Exception:
        return
    if eng.dialect.name != "sqlite":
        return
    cur = dbapi_connection.cursor()
    try:
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
    finally:
        cur.close()


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self._engine)
        self._ensure_schema()

    # ── Session ───────────────────────────────────────────────────────

    def get_or_create_session(self, session_id: str | None = None) -> str:
        sid = session_id or str(uuid.uuid4())
        with DBSession(self._engine) as db:
            existing = db.get(Session, sid)
            if not existing:
                db.add(Session(id=sid))
                db.commit()
        return sid

    # ── Messages ──────────────────────────────────────────────────────

    def save_turn(self, session_id: str, role: str, content: str) -> None:
        with DBSession(self._engine) as db:
            db.add(Message(session_id=session_id, role=role, content=content))
            db.commit()

    def get_recent_turns(
        self, session_id: str, n: int = 20
    ) -> list[dict[str, str]]:
        with DBSession(self._engine) as db:
            rows = db.scalars(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.desc())
                .limit(n)
            ).all()
        rows = list(reversed(rows))
        return [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in rows
        ]

    def list_sessions(self) -> list[dict[str, object]]:
        """
        Session list for the sidebar. Uses a few targeted queries instead of
        loading *all* messages for *every* session (which was O(total messages)
        and very slow for large history).
        """
        with DBSession(self._engine) as db:
            sessions: list[Session] = list(
                db.scalars(select(Session).order_by(Session.created_at.desc())).all()
            )
            if not sessions:
                return []

            sids = [s.id for s in sessions]

            c_rows = db.execute(
                select(Message.session_id, func.count())
                .where(Message.session_id.in_(sids))
                .group_by(Message.session_id)
            ).all()
            count_map: dict[str, int] = {r[0]: int(r[1]) for r in c_rows}  # type: ignore[index]

            smax = (
                select(Message.session_id, func.max(Message.id).label("max_id"))
                .where(Message.session_id.in_(sids))
                .group_by(Message.session_id)
                .subquery()
            )
            last_rows = list(
                db.execute(
                    select(Message).join(
                        smax,
                        and_(
                            Message.session_id == smax.c.session_id,
                            Message.id == smax.c.max_id,
                        ),
                    )
                )
                .scalars()
                .all()
            )
            last_by_sid: dict[str, Message] = {m.session_id: m for m in last_rows}

            sfirst = (
                select(Message.session_id, func.min(Message.id).label("min_id"))
                .where(
                    Message.session_id.in_(sids),
                    Message.role == "user",
                    func.length(func.trim(Message.content)) > 0,
                )
                .group_by(Message.session_id)
                .subquery()
            )
            first_rows = list(
                db.execute(
                    select(Message).join(
                        sfirst,
                        and_(
                            Message.session_id == sfirst.c.session_id,
                            Message.id == sfirst.c.min_id,
                        ),
                    )
                )
                .scalars()
                .all()
            )
            first_by_sid: dict[str, Message] = {m.session_id: m for m in first_rows}

        summaries: list[dict[str, object]] = []
        for session in sessions:
            message_count = count_map.get(session.id, 0)
            first_user = first_by_sid.get(session.id)
            last_message = last_by_sid.get(session.id)
            title_source = (
                first_user.content
                if first_user
                else (last_message.content if last_message else "New chat")
            )
            preview_source = last_message.content if last_message else "No messages yet."
            title = (session.custom_title or "").strip() or self._summarize_text(title_source, 42) or "New chat"
            summaries.append(
                {
                    "id": session.id,
                    "title": title,
                    "preview": self._summarize_text(preview_source, 84) or "No messages yet.",
                    "folder": session.folder_name,
                    "created_at": session.created_at,
                    "last_message_at": last_message.created_at if last_message else None,
                    "message_count": message_count,
                }
            )

        return summaries

    def delete_session(self, session_id: str) -> bool:
        with DBSession(self._engine) as db:
            row = db.get(Session, session_id)
            if not row:
                return False
            db.delete(row)
            db.commit()
            return True

    def rename_session(self, session_id: str, title: str | None) -> bool:
        normalized = " ".join((title or "").split()).strip()
        if len(normalized) > 160:
            normalized = normalized[:160].rstrip()

        with DBSession(self._engine) as db:
            row = db.get(Session, session_id)
            if not row:
                return False
            row.custom_title = normalized or None
            db.commit()
            return True

    def move_session_to_folder(self, session_id: str, folder: str | None) -> bool:
        folder_name = " ".join((folder or "").split()).strip()
        if len(folder_name) > 120:
            folder_name = folder_name[:120].rstrip()

        with DBSession(self._engine) as db:
            row = db.get(Session, session_id)
            if not row:
                return False

            if not folder_name:
                row.folder_name = None
                db.commit()
                return True

            existing_folder = db.get(Folder, folder_name)
            if not existing_folder:
                db.add(Folder(name=folder_name))

            row.folder_name = folder_name
            db.commit()
            return True

    def list_folders(self) -> list[dict[str, object]]:
        with DBSession(self._engine) as db:
            folders = db.scalars(
                select(Folder).order_by(Folder.name.asc())
            ).all()

        return [
            {
                "name": folder.name,
                "created_at": folder.created_at,
            }
            for folder in folders
        ]

    def create_folder(self, name: str) -> bool:
        folder_name = " ".join(name.split()).strip()
        if not folder_name:
            return False
        if len(folder_name) > 120:
            folder_name = folder_name[:120].rstrip()

        with DBSession(self._engine) as db:
            existing = db.get(Folder, folder_name)
            if existing:
                return True
            db.add(Folder(name=folder_name))
            db.commit()
            return True

    def delete_folder(self, name: str) -> bool:
        folder_name = " ".join(name.split()).strip()
        if not folder_name:
            return False

        with DBSession(self._engine) as db:
            folder = db.get(Folder, folder_name)
            if not folder:
                return False

            sessions = db.scalars(
                select(Session).where(Session.folder_name == folder_name)
            ).all()
            for session in sessions:
                session.folder_name = None

            db.delete(folder)
            db.commit()
            return True

    # ── Facts ─────────────────────────────────────────────────────────

    def save_fact(self, key: str, value: str, source: str = "inferred") -> None:
        with DBSession(self._engine) as db:
            existing = db.scalar(select(Fact).where(Fact.key == key))
            if existing:
                existing.value = value
                existing.source = source
            else:
                db.add(Fact(key=key, value=value, source=source))
            db.commit()

    def get_facts(self) -> list[dict[str, str]]:
        with DBSession(self._engine) as db:
            rows = db.scalars(
                select(Fact).order_by(Fact.updated_at.desc())
            ).all()
        return [{"key": f.key, "value": f.value, "source": f.source} for f in rows]

    def delete_fact(self, key: str) -> bool:
        with DBSession(self._engine) as db:
            row = db.scalar(select(Fact).where(Fact.key == key))
            if row:
                db.delete(row)
                db.commit()
                return True
        return False

    def get_fact_value(self, key: str, default: str = "") -> str:
        with DBSession(self._engine) as db:
            row = db.scalar(select(Fact).where(Fact.key == key))
            if row and row.value:
                return row.value
        return default

    def clear_all(self) -> None:
        """Delete all sessions, messages, facts, and folders (e.g. admin reset; optional test wipe). \
        Preserves auto-feed `live_knowledge*` keys. Not run on normal server exit."""
        _PRESERVE_FACT_PREFIXES = ("live_knowledge",)
        with self._engine.begin() as conn:
            conn.execute(text("DELETE FROM messages"))
            conn.execute(text("DELETE FROM sessions"))
            conn.execute(text("DELETE FROM folders"))
            # Delete all facts except auto-feed knowledge (those are expensive to re-fetch)
            placeholders = ", ".join(f"'{p}%'" for p in _PRESERVE_FACT_PREFIXES)
            conn.execute(text(
                f"DELETE FROM facts WHERE key NOT LIKE {placeholders.replace(', ', ' AND key NOT LIKE ')}"
            ))
        print("[Nova] Memory cleared on shutdown (knowledge feed preserved).", flush=True)

    @staticmethod
    def _summarize_text(text: str, max_length: int) -> str:
        normalized = " ".join(text.split()).strip()
        if len(normalized) <= max_length:
            return normalized
        return normalized[: max_length - 1].rstrip() + "…"

    def _ensure_schema(self) -> None:
        with self._engine.begin() as conn:
            columns = conn.execute(text("PRAGMA table_info(sessions)")).fetchall()
            column_names = {str(col[1]) for col in columns}

            if "custom_title" not in column_names:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN custom_title VARCHAR(160)"))

            if "folder_name" not in column_names:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN folder_name VARCHAR(120)"))
