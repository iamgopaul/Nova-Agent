from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import uuid as _uuid_mod

from sqlalchemy import and_, create_engine, event, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as DBSession

from gaaia.memory.models import (
    AuthBase,
    DataBase,
    Fact,
    Folder,
    Message,
    OAuthIdentity,
    Session,
    User,
    WatchedTopic,
)


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
    """
    Persistent storage for GAAIA conversations, facts, and user accounts.

    Two modes:
    - SQLite (default, local dev): single file, all tables in one database.
    - PostgreSQL (production): single `gaaia` database with two schemas:
        * `auth`  — users, oauth_identities
        * `data`  — sessions, messages, facts, folders, watched_topics, agent runs
      Pass `database_url="postgresql+psycopg2://..."` to activate this mode.
      No PgBouncer or external connection pooler is used; SQLAlchemy's built-in
      QueuePool handles connection reuse.
    """

    def __init__(self, db_path: Path, *, database_url: str | None = None) -> None:
        if database_url:
            self._mode = "postgres"
            # One real engine; two execution-option proxies for schema routing.
            # schema_translate_map={None: "auth"} routes all un-schemed tables to
            # the `auth` schema; likewise for `data`.  No connection pooler needed.
            _base = create_engine(database_url, pool_pre_ping=True)
            self._auth_engine: Engine = _base.execution_options(
                schema_translate_map={None: "auth"}
            )
            self._data_engine: Engine = _base.execution_options(
                schema_translate_map={None: "data"}
            )
            # Ensure schemas exist before create_all (idempotent)
            with _base.begin() as conn:
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS data"))
            AuthBase.metadata.create_all(self._auth_engine)
            DataBase.metadata.create_all(self._data_engine)
        else:
            self._mode = "sqlite"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._engine: Engine = create_engine(
                f"sqlite:///{db_path}",
                connect_args={"check_same_thread": False},
            )
            self._auth_engine = self._engine
            self._data_engine = self._engine
            AuthBase.metadata.create_all(self._engine)
            DataBase.metadata.create_all(self._engine)
            self._ensure_sqlite_migrations()

    # ── Engine helpers ────────────────────────────────────────────────

    @contextmanager
    def _auth_sess(self) -> Generator[DBSession, None, None]:
        with DBSession(self._auth_engine) as db:
            yield db

    @contextmanager
    def _data_sess(self) -> Generator[DBSession, None, None]:
        with DBSession(self._data_engine) as db:
            yield db

    # ── Session ───────────────────────────────────────────────────────

    def get_or_create_session(
        self,
        session_id: str | None = None,
        user_id: str | None = None,
        source: str = "chat",
    ) -> str:
        sid = session_id or str(_uuid_mod.uuid4())
        with self._data_sess() as db:
            existing = db.get(Session, sid)
            if not existing:
                db.add(Session(id=sid, user_id=user_id, source=source))
                db.commit()
            elif user_id:
                if existing.user_id is None:
                    existing.user_id = user_id
                    db.commit()
                elif existing.user_id != user_id:
                    raise ValueError("Session does not belong to this user.")
        return sid

    # ── Messages ──────────────────────────────────────────────────────

    def save_turn(self, session_id: str, role: str, content: str) -> None:
        with self._data_sess() as db:
            db.add(Message(session_id=session_id, role=role, content=content))
            db.commit()

    def get_recent_turns(
        self, session_id: str, n: int = 20, user_id: str | None = None
    ) -> list[dict[str, str]]:
        with self._data_sess() as db:
            session = db.get(Session, session_id)
            if session is None:
                return []
            if user_id is not None and session.user_id != user_id:
                return []
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

    def list_sessions(self, user_id: str | None = None, source: str = "chat") -> list[dict[str, object]]:
        """
        Session list for the sidebar. Returns only sessions matching *source*
        ("chat" by default) so GAAIA Voice history stays out of GAAIA Chat.
        """
        with self._data_sess() as db:
            q = select(Session).where(Session.source == source).order_by(Session.created_at.desc())
            if user_id is not None:
                q = q.where(Session.user_id == user_id)
            sessions: list[Session] = list(db.scalars(q).all())
            if not sessions:
                return []

            sids = [s.id for s in sessions]

            c_rows = db.execute(
                select(Message.session_id, func.count())
                .where(Message.session_id.in_(sids))
                .group_by(Message.session_id)
            ).all()
            count_map: dict[str, int] = {r[0]: int(r[1]) for r in c_rows}

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

    def list_voice_sessions(self, user_id: str | None = None) -> list[dict[str, object]]:
        return self.list_sessions(user_id=user_id, source="voice")

    def delete_session(self, session_id: str, user_id: str | None = None) -> bool:
        with self._data_sess() as db:
            row = db.get(Session, session_id)
            if not row:
                return False
            if user_id is not None and row.user_id is not None and row.user_id != user_id:
                return False
            db.delete(row)
            db.commit()
            return True

    def rename_session(self, session_id: str, title: str | None, user_id: str | None = None) -> bool:
        normalized = " ".join((title or "").split()).strip()
        if len(normalized) > 160:
            normalized = normalized[:160].rstrip()

        with self._data_sess() as db:
            row = db.get(Session, session_id)
            if not row:
                return False
            if user_id is not None and row.user_id != user_id:
                return False
            row.custom_title = normalized or None
            db.commit()
            return True

    def move_session_to_folder(self, session_id: str, folder: str | None, user_id: str | None = None) -> bool:
        folder_name = " ".join((folder or "").split()).strip()
        if len(folder_name) > 120:
            folder_name = folder_name[:120].rstrip()

        with self._data_sess() as db:
            row = db.get(Session, session_id)
            if not row:
                return False
            if user_id is not None and row.user_id != user_id:
                return False

            if not folder_name:
                row.folder_name = None
                db.commit()
                return True

            existing_folder = db.get(Folder, folder_name)
            if not existing_folder:
                db.add(Folder(name=folder_name, user_id=user_id))
            elif user_id is not None and existing_folder.user_id != user_id:
                return False

            row.folder_name = folder_name
            db.commit()
            return True

    def list_folders(self, user_id: str | None = None) -> list[dict[str, object]]:
        with self._data_sess() as db:
            q = select(Folder).order_by(Folder.name.asc())
            if user_id is not None:
                q = q.where(Folder.user_id == user_id)
            folders = db.scalars(q).all()

        return [
            {
                "name": folder.name,
                "created_at": folder.created_at,
            }
            for folder in folders
        ]

    def create_folder(self, name: str, user_id: str | None = None) -> bool:
        folder_name = " ".join(name.split()).strip()
        if not folder_name:
            return False
        if len(folder_name) > 120:
            folder_name = folder_name[:120].rstrip()

        with self._data_sess() as db:
            existing = db.get(Folder, folder_name)
            if existing:
                return True
            db.add(Folder(name=folder_name, user_id=user_id))
            db.commit()
            return True

    def delete_folder(self, name: str, user_id: str | None = None) -> bool:
        folder_name = " ".join(name.split()).strip()
        if not folder_name:
            return False

        with self._data_sess() as db:
            folder = db.get(Folder, folder_name)
            if not folder:
                return False
            if user_id is not None and folder.user_id != user_id:
                return False

            q = select(Session).where(Session.folder_name == folder_name)
            if user_id is not None:
                q = q.where(Session.user_id == user_id)
            for session in db.scalars(q).all():
                session.folder_name = None

            db.delete(folder)
            db.commit()
            return True

    # ── Facts ─────────────────────────────────────────────────────────

    def save_fact(self, key: str, value: str, source: str = "inferred", user_id: str | None = None) -> None:
        with self._data_sess() as db:
            q = select(Fact).where(Fact.key == key)
            if user_id is not None:
                q = q.where(Fact.user_id == user_id)
            existing = db.scalar(q)
            if existing:
                existing.value = value
                existing.source = source
            else:
                db.add(Fact(key=key, value=value, source=source, user_id=user_id))
            db.commit()

    def get_facts(self, user_id: str | None = None) -> list[dict[str, str]]:
        with self._data_sess() as db:
            q = select(Fact).order_by(Fact.updated_at.desc())
            if user_id is not None:
                q = q.where(Fact.user_id == user_id)
            rows = db.scalars(q).all()
        return [{"key": f.key, "value": f.value, "source": f.source} for f in rows]

    def delete_fact(self, key: str, user_id: str | None = None) -> bool:
        with self._data_sess() as db:
            q = select(Fact).where(Fact.key == key)
            if user_id is not None:
                q = q.where(Fact.user_id == user_id)
            row = db.scalar(q)
            if row:
                db.delete(row)
                db.commit()
                return True
        return False

    def get_fact_value(self, key: str, default: str = "", user_id: str | None = None) -> str:
        with self._data_sess() as db:
            q = select(Fact).where(Fact.key == key)
            if user_id is not None:
                q = q.where(Fact.user_id == user_id)
            row = db.scalar(q)
            if row and row.value:
                return row.value
        return default

    def clear_all(self) -> None:
        """Delete all sessions, messages, facts, and folders (admin reset or test wipe).
        Preserves auto-feed `live_knowledge*` keys."""
        _PRESERVE_FACT_PREFIXES = ("live_knowledge",)
        with self._data_engine.begin() as conn:
            conn.execute(text("DELETE FROM messages"))
            conn.execute(text("DELETE FROM sessions"))
            conn.execute(text("DELETE FROM folders"))
            conn.execute(text(
                "DELETE FROM facts WHERE key NOT LIKE 'live_knowledge%'"
            ))
        print("[GAAIA] Memory cleared (knowledge feed preserved).", flush=True)

    @staticmethod
    def _summarize_text(text: str, max_length: int) -> str:
        normalized = " ".join(text.split()).strip()
        if len(normalized) <= max_length:
            return normalized
        return normalized[: max_length - 1].rstrip() + "…"

    # ── User CRUD ──────────────────────────────────────────────────────

    def create_user(
        self, email: str, hashed_password: str, display_name: str, avatar_color: str = "#38bdf8"
    ) -> User:
        user = User(
            id=str(_uuid_mod.uuid4()),
            email=email.lower().strip(),
            hashed_password=hashed_password,
            display_name=display_name.strip(),
            avatar_color=avatar_color,
        )
        with self._auth_sess() as db:
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    def get_user_by_email(self, email: str) -> User | None:
        with self._auth_sess() as db:
            return db.scalar(select(User).where(User.email == email.lower().strip()))

    def get_user_by_id(self, user_id: str) -> User | None:
        with self._auth_sess() as db:
            return db.get(User, user_id)

    def update_user(self, user_id: str, display_name: str | None, avatar_color: str | None) -> User | None:
        with self._auth_sess() as db:
            user = db.get(User, user_id)
            if not user:
                return None
            if display_name is not None:
                user.display_name = display_name.strip()
            if avatar_color is not None:
                user.avatar_color = avatar_color
            db.commit()
            db.refresh(user)
        return user

    def update_user_password(self, user_id: str, hashed_password: str) -> User | None:
        with self._auth_sess() as db:
            user = db.get(User, user_id)
            if not user:
                return None
            user.hashed_password = hashed_password
            # Bump token_version so all previously issued JWTs are immediately invalid
            user.token_version = (user.token_version or 0) + 1
            db.commit()
            db.refresh(user)
        return user

    def count_users(self) -> int:
        with self._auth_sess() as db:
            return db.scalar(select(func.count()).select_from(User)) or 0

    def claim_orphaned_sessions(self, user_id: str) -> None:
        """Assign all sessions/folders/facts with no owner to the first registered user."""
        with self._data_engine.begin() as conn:
            conn.execute(
                text("UPDATE sessions SET user_id = :uid WHERE user_id IS NULL"),
                {"uid": user_id},
            )
            conn.execute(
                text("UPDATE folders SET user_id = :uid WHERE user_id IS NULL"),
                {"uid": user_id},
            )
            conn.execute(
                text("UPDATE facts SET user_id = :uid WHERE user_id IS NULL"),
                {"uid": user_id},
            )

    # ── OAuth identities ──────────────────────────────────────────────

    def get_user_id_by_oauth(self, provider: str, provider_user_id: str) -> str | None:
        with self._auth_sess() as db:
            row = db.scalar(
                select(OAuthIdentity).where(
                    OAuthIdentity.provider == provider,
                    OAuthIdentity.provider_user_id == provider_user_id,
                )
            )
            return row.user_id if row else None

    def list_oauth_providers(self, user_id: str) -> list[str]:
        with self._auth_sess() as db:
            rows = db.scalars(
                select(OAuthIdentity.provider).where(OAuthIdentity.user_id == user_id)
            ).all()
        return sorted({str(p) for p in rows if p})

    def link_oauth_identity(
        self,
        user_id: str,
        provider: str,
        provider_user_id: str,
        email: str | None = None,
    ) -> tuple[bool, str | None]:
        with self._auth_sess() as db:
            existing_provider = db.scalar(
                select(OAuthIdentity).where(
                    OAuthIdentity.provider == provider,
                    OAuthIdentity.provider_user_id == provider_user_id,
                )
            )
            if existing_provider and existing_provider.user_id != user_id:
                return False, "oauth_identity_in_use"

            existing_user_provider = db.scalar(
                select(OAuthIdentity).where(
                    OAuthIdentity.user_id == user_id,
                    OAuthIdentity.provider == provider,
                )
            )

            if existing_provider and existing_provider.user_id == user_id:
                if email and not existing_provider.email:
                    existing_provider.email = email
                    db.commit()
                return True, None

            if existing_user_provider:
                existing_user_provider.provider_user_id = provider_user_id
                if email:
                    existing_user_provider.email = email
                db.commit()
                return True, None

            db.add(
                OAuthIdentity(
                    user_id=user_id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    email=email,
                )
            )
            db.commit()
            return True, None

    # ── Watched Topics (Web Watcher) ──────────────────────────────────

    def list_watched_topics(self, user_id: str) -> list[dict]:
        with self._data_sess() as db:
            rows = db.scalars(
                select(WatchedTopic)
                .where(WatchedTopic.user_id == user_id)
                .order_by(WatchedTopic.created_at.asc())
            ).all()
        return [
            {
                "id": t.id,
                "label": t.label,
                "query": t.query,
                "category": t.category,
                "enabled": t.enabled,
                "last_fetched_at": t.last_fetched_at,
                "last_result": t.last_result,
                "created_at": t.created_at,
            }
            for t in rows
        ]

    def add_watched_topic(
        self, user_id: str, label: str, query: str, category: str = "custom"
    ) -> dict:
        t = WatchedTopic(
            id=str(uuid.uuid4()),
            user_id=user_id,
            label=label.strip(),
            query=query.strip(),
            category=category,
            enabled=True,
        )
        with self._data_sess() as db:
            db.add(t)
            db.commit()
            db.refresh(t)
            return {
                "id": t.id,
                "label": t.label,
                "query": t.query,
                "category": t.category,
                "enabled": t.enabled,
                "last_fetched_at": t.last_fetched_at,
                "last_result": t.last_result,
                "created_at": t.created_at,
            }

    def delete_watched_topic(self, topic_id: str, user_id: str) -> bool:
        with self._data_sess() as db:
            t = db.get(WatchedTopic, topic_id)
            if not t or t.user_id != user_id:
                return False
            db.delete(t)
            db.commit()
        return True

    def toggle_watched_topic(self, topic_id: str, user_id: str, enabled: bool) -> bool:
        with self._data_sess() as db:
            t = db.get(WatchedTopic, topic_id)
            if not t or t.user_id != user_id:
                return False
            t.enabled = enabled
            db.commit()
        return True

    def update_watched_topic_result(self, topic_id: str, result_json: str) -> None:
        with self._data_sess() as db:
            t = db.get(WatchedTopic, topic_id)
            if t:
                t.last_result = result_json
                t.last_fetched_at = datetime.now(timezone.utc)
                db.commit()

    def list_all_enabled_topics(self) -> list[dict]:
        with self._data_sess() as db:
            rows = db.scalars(
                select(WatchedTopic).where(WatchedTopic.enabled.is_(True))
            ).all()
        return [
            {"id": t.id, "user_id": t.user_id, "label": t.label, "query": t.query}
            for t in rows
        ]

    # ── SQLite backward-compat migrations ─────────────────────────────

    def _ensure_sqlite_migrations(self) -> None:
        """Add columns introduced after the initial schema (SQLite ALTER TABLE)."""
        with self._engine.begin() as conn:
            user_cols = {str(c[1]) for c in conn.execute(text("PRAGMA table_info(users)")).fetchall()}
            if "avatar_color" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN avatar_color VARCHAR(20) NOT NULL DEFAULT '#38bdf8'"))
            if "created_at" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME"))
                conn.execute(text("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
            if "token_version" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"))

            session_cols = {str(c[1]) for c in conn.execute(text("PRAGMA table_info(sessions)")).fetchall()}
            if "custom_title" not in session_cols:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN custom_title VARCHAR(160)"))
            if "folder_name" not in session_cols:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN folder_name VARCHAR(120)"))
            if "user_id" not in session_cols:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN user_id VARCHAR(36)"))
            if "source" not in session_cols:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT 'chat'"))

            folder_cols = {str(c[1]) for c in conn.execute(text("PRAGMA table_info(folders)")).fetchall()}
            if "user_id" not in folder_cols:
                conn.execute(text("ALTER TABLE folders ADD COLUMN user_id VARCHAR(36)"))

            fact_cols = {str(c[1]) for c in conn.execute(text("PRAGMA table_info(facts)")).fetchall()}
            if "user_id" not in fact_cols:
                conn.execute(text("ALTER TABLE facts ADD COLUMN user_id VARCHAR(36)"))

            # oauth_identities is created by AuthBase.metadata.create_all; just
            # ensure the unique indexes exist for older databases that predate create_all.
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_oauth_provider_user "
                "ON oauth_identities(provider, provider_user_id)"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_oauth_user_provider "
                "ON oauth_identities(user_id, provider)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_oauth_user_id "
                "ON oauth_identities(user_id)"
            ))
