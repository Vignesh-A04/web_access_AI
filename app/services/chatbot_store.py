"""Durable local persistence layer for WhatsApp Incoming-Message Chatbot using SQLite."""

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from app.api.schemas import (
    ChatbotConfigModel,
    ChatbotContactItem,
    ChatbotMessageRecord,
    ChatbotMessageStatusEnum,
)
from app.config import settings
from app.logging.setup import get_logger

logger = get_logger("chatbot_store")


class ChatbotStore:
    """Thread-safe SQLite store for chatbot configuration, contact allowlist, and message lifecycle."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            data_dir = Path("task_artifacts")
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(data_dir / "chatbot.db")
        else:
            self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chatbot_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    config_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contact_allowlist (
                    contact_name TEXT PRIMARY KEY,
                    is_paused INTEGER NOT NULL DEFAULT 0,
                    added_at TEXT NOT NULL,
                    notes TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_messages (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL UNIQUE,
                    contact_name TEXT NOT NULL,
                    incoming_text TEXT NOT NULL,
                    timestamp_str TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reply_text TEXT,
                    intent TEXT,
                    confidence REAL,
                    skip_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_contact_created
                ON processed_messages(contact_name, created_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_fingerprint
                ON processed_messages(fingerprint)
            """)
            conn.commit()

    # =========================================================================
    # Configuration Management
    # =========================================================================

    def get_config(self) -> ChatbotConfigModel:
        """Load stored config or initialize default."""
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT config_json FROM chatbot_config WHERE id = 1").fetchone()
            if row:
                try:
                    data = json.loads(row["config_json"])
                    # Sync allowed and paused contacts from contact_allowlist table
                    contacts_rows = conn.execute("SELECT contact_name, is_paused FROM contact_allowlist").fetchall()
                    allowed = [r["contact_name"] for r in contacts_rows]
                    paused = [r["contact_name"] for r in contacts_rows if r["is_paused"]]
                    data["allowed_contacts"] = allowed
                    data["paused_contacts"] = paused
                    return ChatbotConfigModel(**data)
                except Exception as e:
                    logger.error(f"Failed to deserialize chatbot config: {e}")

            default_config = ChatbotConfigModel()
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                INSERT INTO chatbot_config (id, config_json, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at
            """, (json.dumps(default_config.model_dump()), now_iso))
            conn.commit()
            return default_config

    def save_config(self, config: ChatbotConfigModel) -> None:
        """Save configuration."""
        with self._lock, self._get_connection() as conn:
            now_iso = datetime.now(timezone.utc).isoformat()
            config_dict = config.model_dump()
            conn.execute("""
                INSERT INTO chatbot_config (id, config_json, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at
            """, (json.dumps(config_dict), now_iso))
            conn.commit()

    # =========================================================================
    # Contact Allowlist Management
    # =========================================================================

    def list_contacts(self) -> List[ChatbotContactItem]:
        """List all allowlisted contacts."""
        with self._lock, self._get_connection() as conn:
            rows = conn.execute("SELECT contact_name, is_paused, added_at, notes FROM contact_allowlist ORDER BY contact_name ASC").fetchall()
            return [
                ChatbotContactItem(
                    contact_name=r["contact_name"],
                    is_paused=bool(r["is_paused"]),
                    added_at=r["added_at"],
                    notes=r["notes"]
                )
                for r in rows
            ]

    def add_contact(self, contact_name: str, notes: Optional[str] = None) -> ChatbotContactItem:
        """Add an explicitly allowlisted contact. Normalizes whitespace and preserves display casing."""
        display_name = contact_name.strip()
        if not display_name:
            raise ValueError("Contact name cannot be empty.")
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock, self._get_connection() as conn:
            existing = conn.execute(
                "SELECT contact_name FROM contact_allowlist WHERE LOWER(contact_name) = LOWER(?)",
                (display_name,)
            ).fetchone()
            if existing:
                raise ValueError(f"Contact '{existing['contact_name']}' is already in the allowlist.")

            conn.execute("""
                INSERT INTO contact_allowlist (contact_name, is_paused, added_at, notes)
                VALUES (?, 0, ?, ?)
            """, (display_name, now_iso, notes))
            conn.commit()
        return ChatbotContactItem(contact_name=display_name, name=display_name, is_paused=False, added_at=now_iso, notes=notes)

    def remove_contact(self, contact_name: str) -> bool:
        """Remove a contact from the allowlist."""
        normalized = contact_name.strip()
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM contact_allowlist WHERE LOWER(contact_name) = LOWER(?)", (normalized,))
            conn.commit()
            return cursor.rowcount > 0

    def pause_contact(self, contact_name: str) -> bool:
        """Pause automated replies for a contact."""
        normalized = contact_name.strip()
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("UPDATE contact_allowlist SET is_paused = 1 WHERE LOWER(contact_name) = LOWER(?)", (normalized,))
            conn.commit()
            return cursor.rowcount > 0

    def resume_contact(self, contact_name: str) -> bool:
        """Resume automated replies for a contact."""
        normalized = contact_name.strip()
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("UPDATE contact_allowlist SET is_paused = 0 WHERE LOWER(contact_name) = LOWER(?)", (normalized,))
            conn.commit()
            return cursor.rowcount > 0

    def get_contact(self, contact_name: str) -> Optional[ChatbotContactItem]:
        """Get contact entry by name."""
        normalized = contact_name.strip()
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT contact_name, is_paused, added_at, notes FROM contact_allowlist WHERE LOWER(contact_name) = LOWER(?)", (normalized,)).fetchone()
            if row:
                return ChatbotContactItem(
                    contact_name=row["contact_name"],
                    is_paused=bool(row["is_paused"]),
                    added_at=row["added_at"],
                    notes=row["notes"]
                )
            return None

    def is_contact_allowed(self, contact_name: str) -> bool:
        """Check if contact is explicitly in allowlist and not paused."""
        contact = self.get_contact(contact_name)
        return contact is not None and not contact.is_paused

    def set_contact_paused(self, contact_name: str, paused: bool) -> bool:
        """Set pause state for a contact."""
        return self.pause_contact(contact_name) if paused else self.resume_contact(contact_name)

    # =========================================================================
    # Fingerprinting & Duplicate Prevention
    # =========================================================================

    @staticmethod
    def compute_fingerprint(contact_name: str, text: str, timestamp_str: str, dom_context: str = "") -> str:
        """Generate a deterministic, durable cryptographic fingerprint for an incoming message.

        Incorporates sender name, message content, timestamp / DOM metadata, and context.
        Limitations: WhatsApp Web virtualizes chat bubbles and does not always expose server-assigned
        UUIDs in the DOM. Hence, identical text sent by the same user within the same minute or DOM context
        will produce the same fingerprint (which protects against duplicate replies).
        """
        raw = f"{contact_name.strip().lower()}:{text.strip()}:{timestamp_str.strip()}:{dom_context.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def is_message_known(self, fingerprint: str) -> bool:
        """Check whether this message fingerprint has already been processed or detected."""
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT 1 FROM processed_messages WHERE fingerprint = ?", (fingerprint,)).fetchone()
            return bool(row)

    def record_detected_message(
        self,
        fingerprint: str,
        contact_name: str,
        incoming_text: str,
        timestamp_str: str
    ) -> Optional[ChatbotMessageRecord]:
        """Atomically record an incoming message as DETECTED if not already present.

        Returns the record if newly inserted, or None if already known (enforcing uniqueness).
        """
        msg_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock, self._get_connection() as conn:
            try:
                conn.execute("""
                    INSERT INTO processed_messages (
                        id, fingerprint, contact_name, incoming_text, timestamp_str,
                        status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    msg_id,
                    fingerprint,
                    contact_name.strip(),
                    incoming_text.strip(),
                    timestamp_str.strip(),
                    ChatbotMessageStatusEnum.DETECTED.value,
                    now_iso,
                    now_iso
                ))
                conn.commit()
                return ChatbotMessageRecord(
                    id=msg_id,
                    fingerprint=fingerprint,
                    contact_name=contact_name.strip(),
                    incoming_text=incoming_text.strip(),
                    timestamp_str=timestamp_str.strip(),
                    status=ChatbotMessageStatusEnum.DETECTED,
                    created_at=now_iso,
                    updated_at=now_iso
                )
            except sqlite3.IntegrityError:
                # Fingerprint collision: message already processed or being processed
                return None

    def update_message_status(
        self,
        message_id: str,
        new_status: ChatbotMessageStatusEnum,
        reply_text: Optional[str] = None,
        intent: Optional[str] = None,
        confidence: Optional[float] = None,
        skip_reason: Optional[str] = None
    ) -> bool:
        """Atomically update a message's state."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("""
                UPDATE processed_messages
                SET status = ?,
                    reply_text = COALESCE(?, reply_text),
                    intent = COALESCE(?, intent),
                    confidence = COALESCE(?, confidence),
                    skip_reason = COALESCE(?, skip_reason),
                    updated_at = ?
                WHERE id = ?
            """, (
                new_status.value,
                reply_text,
                intent,
                confidence,
                skip_reason,
                now_iso,
                message_id
            ))
            conn.commit()
            return cursor.rowcount > 0

    def count_recent_replies(self, contact_name: str, window_minutes: int) -> int:
        """Count how many automated replies were sent (or sending) to this contact within window."""
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
        with self._lock, self._get_connection() as conn:
            row = conn.execute("""
                SELECT COUNT(*) as count FROM processed_messages
                WHERE LOWER(contact_name) = LOWER(?)
                  AND status IN ('SENT', 'SENDING')
                  AND created_at >= ?
            """, (contact_name.strip(), cutoff)).fetchone()
            return row["count"] if row else 0

    def list_recent_messages(self, limit: int = 50) -> List[ChatbotMessageRecord]:
        """List recently observed messages and their outcomes."""
        with self._lock, self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM processed_messages
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [
                ChatbotMessageRecord(
                    id=r["id"],
                    fingerprint=r["fingerprint"],
                    contact_name=r["contact_name"],
                    incoming_text=r["incoming_text"],
                    timestamp_str=r["timestamp_str"],
                    status=ChatbotMessageStatusEnum(r["status"]),
                    reply_text=r["reply_text"],
                    intent=r["intent"],
                    confidence=r["confidence"],
                    skip_reason=r["skip_reason"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"]
                )
                for r in rows
            ]

    def get_message_by_id(self, message_id: str) -> Optional[ChatbotMessageRecord]:
        """Retrieve a message record by its unique ID."""
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM processed_messages WHERE id = ?", (message_id,)).fetchone()
            if row:
                return ChatbotMessageRecord(
                    id=row["id"],
                    fingerprint=row["fingerprint"],
                    contact_name=row["contact_name"],
                    incoming_text=row["incoming_text"],
                    timestamp_str=row["timestamp_str"],
                    status=ChatbotMessageStatusEnum(row["status"]),
                    reply_text=row["reply_text"],
                    intent=row["intent"],
                    confidence=row["confidence"],
                    skip_reason=row["skip_reason"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
                )
            return None

    def reconcile_unconfirmed_message(self, message_id: str, confirmed: bool, notes: Optional[str] = None) -> Optional[ChatbotMessageRecord]:
        """Resolve a SEND_UNCONFIRMED message outcome following conversation reconciliation."""
        msg = self.get_message_by_id(message_id)
        if not msg:
            return None

        new_status = ChatbotMessageStatusEnum.SENT if confirmed else ChatbotMessageStatusEnum.SKIPPED
        reason = notes or ("Reconciled: manual confirmation confirmed message delivered" if confirmed else "Reconciled: marked skipped without resending")
        self.update_message_status(message_id, new_status, skip_reason=reason)
        return self.get_message_by_id(message_id)


# Global singleton store instance
chatbot_store = ChatbotStore()
