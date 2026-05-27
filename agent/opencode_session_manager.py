#!/usr/bin/env python3
"""
OpenCode Session Manager — persists session state for Janitor-Dev-Boss.

Tracks:
- active_sessions: sessions currently in use
- completed_sessions: finished sessions kept for auditing
- pending_tasks: tasks queued but not yet started

This manager does NOT delete sessions — they persist for post-task auditing
as specified in the design spec.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

STATE_FILE = Path("~/.janitor/opencode_sessions.json").expanduser()


@dataclass
class TaskRecord:
    task_name: str
    session_id: str
    status: Literal["pending", "running", "completed", "failed", "blocked"]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    error_detail: Optional[str] = None
    retry_count: int = 0


class OpenCodeSessionManager:
    """
    Manages session lifecycle and state persistence for Dev-Boss autonomous operation.

    Usage:
        manager = OpenCodeSessionManager()
        await manager.init()

        session_id = await orchestrator.create_session()
        manager.start_task("analizar auth module", session_id)

        # ... work happens ...

        manager.complete_task("analizar auth module")
    """

    def __init__(self, state_file: Path = STATE_FILE):
        self.state_file = state_file
        self.tasks: dict[str, TaskRecord] = {}

    async def init(self) -> None:
        """Load existing state if available."""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                for task_name, rec in data.get("tasks", {}).items():
                    self.tasks[task_name] = TaskRecord(**rec)
                logger.info(f"Loaded {len(self.tasks)} task records")
            except json.JSONDecodeError as e:
                logger.warning(f"Could not load state file (invalid JSON): {e}")
            except OSError as e:
                logger.warning(f"Could not load state file (I/O error): {e}")

    def _save(self) -> None:
        """Persist state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "tasks": {name: asdict(rec) for name, rec in self.tasks.items()},
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.state_file.write_text(json.dumps(data, indent=2))
        except OSError as e:
            logger.error(f"Could not write state file: {e}")

    def start_task(self, task_name: str, session_id: str) -> None:
        """Mark a task as started."""
        self.tasks[task_name] = TaskRecord(
            task_name=task_name,
            session_id=session_id,
            status="running",
        )
        self._save()
        logger.info(f"Task started: {task_name} (session: {session_id})")

    def complete_task(self, task_name: str) -> None:
        """Mark a task as completed."""
        if task_name in self.tasks:
            self.tasks[task_name].status = "completed"
            self.tasks[task_name].completed_at = datetime.now(timezone.utc).isoformat()
            self._save()
            logger.info(f"Task completed: {task_name}")
        else:
            logger.warning(f"complete_task: task not found: {task_name}")

    def fail_task(self, task_name: str, error_detail: str) -> None:
        """Mark a task as failed."""
        if task_name in self.tasks:
            self.tasks[task_name].status = "failed"
            self.tasks[task_name].error_detail = error_detail
            self.tasks[task_name].completed_at = datetime.now(timezone.utc).isoformat()
            self._save()
            logger.warning(f"Task failed: {task_name} — {error_detail}")
        else:
            logger.warning(f"fail_task: task not found: {task_name}")

    def block_task(self, task_name: str, error_detail: str) -> None:
        """Mark a task as blocked (requires human intervention)."""
        if task_name in self.tasks:
            self.tasks[task_name].status = "blocked"
            self.tasks[task_name].error_detail = error_detail
            self._save()
            logger.warning(f"Task blocked (requires intervention): {task_name}")
        else:
            logger.warning(f"block_task: task not found: {task_name}")

    def increment_retry(self, task_name: str) -> int:
        """Increment retry count and return new value."""
        if task_name not in self.tasks:
            raise KeyError(f"increment_retry: task not found: {task_name}")
        self.tasks[task_name].retry_count += 1
        self._save()
        return self.tasks[task_name].retry_count

    def get_task(self, task_name: str) -> Optional[TaskRecord]:
        """Get a task record by name."""
        return self.tasks.get(task_name)

    def get_session_id(self, task_name: str) -> Optional[str]:
        """Get the session_id for a task."""
        task = self.tasks.get(task_name)
        return task.session_id if task else None

    def list_active_tasks(self) -> list[TaskRecord]:
        """List tasks that are currently running."""
        return [t for t in self.tasks.values() if t.status == "running"]

    def list_completed_tasks(self) -> list[TaskRecord]:
        """List completed tasks (for auditing)."""
        return [t for t in self.tasks.values() if t.status == "completed"]

    def list_blocked_tasks(self) -> list[TaskRecord]:
        """List blocked tasks (requiring human intervention)."""
        return [t for t in self.tasks.values() if t.status == "blocked"]