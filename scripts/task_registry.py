#!/usr/bin/env python3
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import fcntl

ACTIVE_STATUSES = {"creating", "submitted", "pending", "processing"}
STALE_CREATING_AFTER_SECONDS = 900


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class TaskRegistry:
    def __init__(self, path: Optional[str] = None):
        if path:
            self.path = Path(path)
        else:
            self.path = Path(__file__).resolve().parents[1] / "runtime" / "state" / "task_registry.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(".lock")

    @contextmanager
    def _locked(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_unlocked(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "tasks": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"version": 1, "tasks": []}
        if not isinstance(data, dict):
            return {"version": 1, "tasks": []}
        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            data["tasks"] = []
        return data

    def _write_unlocked(self, payload: Dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _is_creating_stale(task: Dict[str, Any]) -> bool:
        if task.get("status") != "creating":
            return False
        updated = parse_iso(task.get("updated_at"))
        if not updated:
            return False
        return datetime.now(timezone.utc) - updated > timedelta(seconds=STALE_CREATING_AFTER_SECONDS)

    @staticmethod
    def _is_open(task: Dict[str, Any]) -> bool:
        if task.get("status") in ACTIVE_STATUSES:
            return True
        return task.get("status") == "completed" and not task.get("response_sent", False)

    def reserve(
        self,
        *,
        request_key: str,
        conversation_key: Optional[str],
        client_message_id: Optional[str],
        plan_summary: Dict[str, Any],
        output_dir: Optional[str],
    ) -> Dict[str, Any]:
        with self._locked():
            data = self._read_unlocked()
            tasks: List[Dict[str, Any]] = data.get("tasks", [])

            existing_by_request = None
            existing_by_conversation = None
            for task in reversed(tasks):
                if self._is_creating_stale(task):
                    continue
                if request_key and task.get("request_key") == request_key and self._is_open(task):
                    existing_by_request = task
                    break
            if not existing_by_request and conversation_key:
                for task in reversed(tasks):
                    if self._is_creating_stale(task):
                        continue
                    if task.get("conversation_key") == conversation_key and self._is_open(task):
                        existing_by_conversation = task
                        break

            existing = existing_by_request or existing_by_conversation
            if existing:
                return {
                    "reused": True,
                    "reason": "request_key_open" if existing_by_request else "conversation_has_open_task",
                    "task": existing,
                }

            now = utc_now_iso()
            record = {
                "local_request_id": f"local_{uuid.uuid4().hex[:16]}",
                "task_id": None,
                "request_key": request_key,
                "conversation_key": conversation_key,
                "client_message_id": client_message_id,
                "status": "creating",
                "response_sent": False,
                "response_sent_at": None,
                "intent_type": plan_summary.get("intent_type"),
                "entrypoint": plan_summary.get("entrypoint"),
                "mode": plan_summary.get("mode"),
                "plan_brief": plan_summary.get("plan_brief"),
                "suggested_next_actions": plan_summary.get("suggested_next_actions") or [],
                "output_dir": output_dir,
                "video_url": None,
                "saved_path": None,
                "created_at": now,
                "updated_at": now,
            }
            tasks.append(record)
            data["tasks"] = tasks
            self._write_unlocked(data)
            return {"reused": False, "reason": None, "task": record}

    def assign_task(
        self,
        *,
        local_request_id: str,
        task_id: Optional[str],
        status: str,
        raw: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._locked():
            data = self._read_unlocked()
            tasks: List[Dict[str, Any]] = data.get("tasks", [])
            now = utc_now_iso()
            updated = None
            for task in tasks:
                if task.get("local_request_id") == local_request_id:
                    task["task_id"] = task_id
                    task["status"] = status
                    task["updated_at"] = now
                    if raw is not None:
                        task["last_raw"] = raw
                    updated = task
                    break
            data["tasks"] = tasks
            self._write_unlocked(data)
            return updated

    def patch_by_task_id(self, task_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        with self._locked():
            data = self._read_unlocked()
            tasks: List[Dict[str, Any]] = data.get("tasks", [])
            now = utc_now_iso()
            updated = None
            for task in tasks:
                if task.get("task_id") == task_id:
                    task.update(fields)
                    task["updated_at"] = now
                    updated = task
                    break
            data["tasks"] = tasks
            self._write_unlocked(data)
            return updated

    def patch_by_local_request_id(self, local_request_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        with self._locked():
            data = self._read_unlocked()
            tasks: List[Dict[str, Any]] = data.get("tasks", [])
            now = utc_now_iso()
            updated = None
            for task in tasks:
                if task.get("local_request_id") == local_request_id:
                    task.update(fields)
                    task["updated_at"] = now
                    updated = task
                    break
            data["tasks"] = tasks
            self._write_unlocked(data)
            return updated

    def mark_response_sent(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.patch_by_task_id(task_id, response_sent=True, response_sent_at=utc_now_iso())

    def lookup(
        self,
        *,
        task_id: Optional[str] = None,
        request_key: Optional[str] = None,
        conversation_key: Optional[str] = None,
        active_only: bool = False,
    ) -> Optional[Dict[str, Any]]:
        with self._locked():
            data = self._read_unlocked()
            tasks: List[Dict[str, Any]] = data.get("tasks", [])
            for task in reversed(tasks):
                if self._is_creating_stale(task):
                    continue
                if active_only and not self._is_open(task):
                    continue
                if task_id and task.get("task_id") == task_id:
                    return task
                if request_key and task.get("request_key") == request_key:
                    return task
                if conversation_key and task.get("conversation_key") == conversation_key:
                    return task
        return None
