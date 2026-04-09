#!/usr/bin/env python3
"""
Seedance 2.0 Video Studio - execution CLI

Current scope:
- build prompt / plan
- create task
- query status
- wait for completion
- download result
- run end-to-end flow
- health check

V1.1 orchestration safeguards:
- request/conversation tracking via local task registry
- dedupe repeated create/run for the same request
- single-active-task guard per conversation (unless --allow-parallel)
- task lookup by request_key / conversation_key
- alias support: --download-dir -> --output-dir
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from seedance2_adapter import Seedance2Adapter

Mode = Literal["text_only", "first_frame", "first_last_frame"]
IntentType = Literal["generate", "reference_create", "extend", "refine", "redo"]
EntryPoint = Literal["do_one", "by_reference", "continue_edit"]

ACTIVE_TASK_STATUSES = {"submitted", "pending", "processing", "running"}
TERMINAL_TASK_STATUSES = {"completed", "succeeded", "success", "failed", "error", "cancelled", "timeout", "downloaded"}
DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parent.parent / "runtime"


@dataclass
class Asset:
    kind: Literal["image", "video", "audio"]
    path: str
    role: Optional[str] = None


@dataclass
class UserIntent:
    prompt: str
    assets: List[Asset]
    duration: Optional[int] = None
    ratio: Optional[str] = None
    style: Optional[str] = None
    generate_audio: bool = False
    return_last_frame: bool = False
    camera_fixed: Optional[bool] = None
    confirm_prompt_first: bool = False


@dataclass
class GenerationPlan:
    intent_type: IntentType
    entrypoint: EntryPoint
    mode: Mode
    duration: int
    ratio: str
    style: str
    assets: List[dict]
    assets_mapping: List[dict]
    final_prompt: str
    negative_constraints: List[str]
    generation_settings: dict
    needs_confirmation: bool
    confirmation_reason: Optional[str] = None
    plan_brief: str = ""
    suggested_next_actions: Optional[List[str]] = None


DEFAULT_NEGATIVE = [
    "no subtitles",
    "no watermark",
    "no logo",
    "no on-screen text",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def runtime_dir() -> Path:
    custom = os.environ.get("SEEDANCE2_RUNTIME_DIR")
    return Path(custom).expanduser() if custom else DEFAULT_RUNTIME_DIR


def registry_path() -> Path:
    return runtime_dir() / "task_registry.json"


def ensure_runtime_dir() -> Path:
    path = runtime_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_registry() -> Dict[str, Any]:
    path = registry_path()
    empty = {"tasks": {}, "request_index": {}, "conversation_active": {}, "conversation_latest": {}}
    if not path.exists():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return empty
    data.setdefault("tasks", {})
    data.setdefault("request_index", {})
    data.setdefault("conversation_active", {})
    data.setdefault("conversation_latest", {})

    tasks = data.get("tasks", {})
    for task_id, record in tasks.items():
        if not isinstance(record, dict):
            continue
        request_key = record.get("request_key")
        conversation_key = record.get("conversation_key")
        if request_key and request_key not in data["request_index"]:
            data["request_index"][request_key] = task_id
        if conversation_key and conversation_key not in data["conversation_latest"]:
            data["conversation_latest"][conversation_key] = task_id
        record.setdefault("response_sent", False)
        record.setdefault("response_sent_at", None)

    return data


def save_registry(registry: Dict[str, Any]) -> None:
    ensure_runtime_dir()
    registry.setdefault("tasks", {})
    registry.setdefault("request_index", {})
    registry.setdefault("conversation_active", {})
    registry.setdefault("conversation_latest", {})
    registry_path().write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")


def is_active_status(status: Optional[str]) -> bool:
    return (status or "").lower() in ACTIVE_TASK_STATUSES


def is_terminal_status(status: Optional[str]) -> bool:
    return (status or "").lower() in TERMINAL_TASK_STATUSES


def can_return_to_conversation(record: Optional[Dict[str, Any]]) -> bool:
    if not record:
        return False
    if record.get("response_sent"):
        return False
    status = (record.get("status") or "").lower()
    if status in ACTIVE_TASK_STATUSES:
        return True
    return status in {"completed", "downloaded", "succeeded", "success"}


def compute_request_fingerprint(intent: UserIntent) -> str:
    payload = {
        "prompt": intent.prompt,
        "assets": [asdict(a) for a in intent.assets],
        "duration": intent.duration,
        "ratio": intent.ratio,
        "style": intent.style,
        "generate_audio": intent.generate_audio,
        "return_last_frame": intent.return_last_frame,
        "camera_fixed": intent.camera_fixed,
        "confirm_prompt_first": intent.confirm_prompt_first,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def contains_any(text: str, keywords: List[str]) -> bool:
    return any(k in text for k in keywords)


def infer_intent_type(prompt: str, has_assets: bool) -> IntentType:
    p = prompt.strip().lower()

    if contains_any(p, ["延长", "接着", "继续", "续上", "续写", "extend"]):
        return "extend"
    if contains_any(p, ["重做", "再来一版", "再来", "重来", "重新做", "redo"]):
        return "redo"
    if contains_any(p, ["微调", "调整", "改成", "更像", "更稳", "不要变", "保持"]):
        return "refine"
    if has_assets or contains_any(p, ["按这", "按这个", "参考", "照着", "复刻", "模仿", "同款"]):
        return "reference_create"
    return "generate"


def infer_entrypoint(intent_type: IntentType, has_assets: bool) -> EntryPoint:
    if intent_type in {"extend", "refine", "redo"}:
        return "continue_edit"
    if has_assets or intent_type == "reference_create":
        return "by_reference"
    return "do_one"


def detect_mode(intent: UserIntent) -> Mode:
    image_assets = [a for a in intent.assets if a.kind == "image"]
    if len(image_assets) >= 2:
        return "first_last_frame"
    if len(image_assets) == 1:
        return "first_frame"
    return "text_only"


def detect_confirmation_need(
    intent: UserIntent,
    mode: Mode,
    intent_type: IntentType,
    entrypoint: EntryPoint,
) -> tuple[bool, Optional[str]]:
    if intent.confirm_prompt_first:
        return True, "user_requested_prompt_preview"

    image_assets = [a for a in intent.assets if a.kind == "image"]

    if len(image_assets) > 2:
        return True, "too_many_images_unclear_priority"

    if intent_type == "extend":
        return True, "extend_requested_but_not_supported_v1"

    if entrypoint == "continue_edit" and not intent.assets:
        return True, "continue_edit_without_reference_context"

    if mode == "first_last_frame" and len(image_assets) < 2:
        return True, "first_last_frame_missing_images"

    return False, None


def build_assets_mapping(intent: UserIntent, mode: Mode) -> List[dict]:
    assets_mapping: List[dict] = []

    if mode == "first_frame":
        assets_mapping.append({"asset": "@image1", "role": "first frame / identity anchor"})
    elif mode == "first_last_frame":
        assets_mapping.append({"asset": "@image1", "role": "start frame / opening composition"})
        assets_mapping.append({"asset": "@image2", "role": "end frame / closing composition"})

    video_assets = [a for a in intent.assets if a.kind == "video"]
    for idx, _ in enumerate(video_assets, start=1):
        assets_mapping.append({"asset": f"@video{idx}", "role": "motion / pacing reference"})

    audio_assets = [a for a in intent.assets if a.kind == "audio"]
    for idx, _ in enumerate(audio_assets, start=1):
        assets_mapping.append({"asset": f"@audio{idx}", "role": "rhythm / mood reference"})

    return assets_mapping


def build_suggested_actions(entrypoint: EntryPoint) -> List[str]:
    if entrypoint == "do_one":
        return ["再来一版", "更像广告", "按这个参考做", "改成电影感"]
    if entrypoint == "by_reference":
        return ["人物别变", "镜头更稳一点", "延长 4 秒", "再来一版"]
    return ["延长 4 秒", "人物别变", "更像广告", "重做一版"]


def build_plan_brief(intent_type: IntentType, mode: Mode, needs_confirmation: bool) -> str:
    if needs_confirmation:
        return f"已识别为 {intent_type}，建议先确认后再执行（当前模式候选：{mode}）。"
    return f"已识别为 {intent_type}，按 {mode} 路径直接执行。"


def expand_prompt(intent: UserIntent, mode: Mode) -> GenerationPlan:
    duration = intent.duration or 6
    ratio = intent.ratio or "9:16"
    style = intent.style or "cinematic realistic"

    has_assets = len(intent.assets) > 0
    intent_type = infer_intent_type(intent.prompt, has_assets)
    entrypoint = infer_entrypoint(intent_type, has_assets)

    needs_confirmation, reason = detect_confirmation_need(intent, mode, intent_type, entrypoint)
    assets_mapping = build_assets_mapping(intent, mode)

    if mode == "text_only":
        final_prompt = (
            f"{style}. "
            f"Opening: establish the scene and subject clearly. "
            f"Middle: develop the core action with controlled camera movement. "
            f"Ending: land on a clear emotional or visual payoff. "
            f"User intent: {intent.prompt}"
        )
    elif mode == "first_frame":
        final_prompt = (
            f"{style}. Use @image1 as first frame and identity anchor. "
            f"Opening: preserve the opening composition from @image1. "
            f"Middle: introduce subtle motion and controlled camera progression. "
            f"Ending: reach a clean visual landing. "
            f"User intent: {intent.prompt}"
        )
    else:
        final_prompt = (
            f"{style}. Use @image1 as the start frame and @image2 as the end frame. "
            f"Opening: begin close to @image1 composition. "
            f"Middle: create a smooth and physically plausible transition. "
            f"Ending: land near @image2 composition. "
            f"User intent: {intent.prompt}"
        )

    return GenerationPlan(
        intent_type=intent_type,
        entrypoint=entrypoint,
        mode=mode,
        duration=duration,
        ratio=ratio,
        style=style,
        assets=[asdict(a) for a in intent.assets],
        assets_mapping=assets_mapping,
        final_prompt=final_prompt,
        negative_constraints=DEFAULT_NEGATIVE.copy(),
        generation_settings={
            "duration": duration,
            "ratio": ratio,
            "style": style,
            "resolution": "720p",
            "generate_audio": intent.generate_audio,
            "return_last_frame": intent.return_last_frame,
            "camera_fixed": intent.camera_fixed,
            "model": "doubao-seedance-2.0",
        },
        needs_confirmation=needs_confirmation,
        confirmation_reason=reason,
        plan_brief=build_plan_brief(intent_type, mode, needs_confirmation),
        suggested_next_actions=build_suggested_actions(entrypoint),
    )


def build_payload(plan: GenerationPlan) -> dict:
    return {
        "mode": plan.mode,
        "assets": plan.assets,
        "assets_mapping": plan.assets_mapping,
        "prompt": plan.final_prompt,
        "negative_constraints": plan.negative_constraints,
        "generation_settings": plan.generation_settings,
    }


def create_task(plan: GenerationPlan) -> dict:
    adapter = Seedance2Adapter()
    payload = build_payload(plan)
    result = adapter.create_task(payload)
    return {
        "status": result.status,
        "message": result.error or "ok",
        "task_id": result.task_id,
        "plan": asdict(plan),
        "payload": payload,
        "raw": result.raw,
    }


def get_status(task_id: str) -> dict:
    adapter = Seedance2Adapter()
    result = adapter.get_status(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "message": result.error or "ok",
        "video_url": result.video_url,
        "raw": result.raw,
    }


def wait_for_completion(task_id: str, poll_seconds: int, timeout_seconds: int) -> dict:
    adapter = Seedance2Adapter()
    result = adapter.wait_for_completion(
        task_id=task_id,
        poll_seconds=poll_seconds,
        timeout_seconds=timeout_seconds,
    )
    return {
        "task_id": task_id,
        "status": result.status,
        "message": result.error or "ok",
        "video_url": result.video_url,
        "raw": result.raw,
    }


def download_video(video_url: str, output_dir: str) -> dict:
    adapter = Seedance2Adapter()
    result = adapter.download_result(video_url, output_dir)
    return {
        "status": result.status,
        "message": result.error or "ok",
        "video_url": result.video_url,
        "saved_path": result.saved_path,
    }


def upload_image(file_path: str) -> dict:
    adapter = Seedance2Adapter()
    result = adapter.upload_image(file_path)
    return {
        "status": result.status,
        "message": result.error or "ok",
        "raw": result.raw,
    }


def build_intent_from_args(args: argparse.Namespace) -> UserIntent:
    assets: List[Asset] = []
    assets.extend(Asset(kind="image", path=p) for p in getattr(args, "image", []) or [])
    assets.extend(Asset(kind="video", path=p) for p in getattr(args, "video", []) or [])
    assets.extend(Asset(kind="audio", path=p) for p in getattr(args, "audio", []) or [])
    return UserIntent(
        prompt=args.prompt,
        assets=assets,
        duration=args.duration,
        ratio=args.ratio,
        style=args.style,
        generate_audio=getattr(args, "generate_audio", False),
        return_last_frame=getattr(args, "return_last_frame", False),
        camera_fixed=getattr(args, "camera_fixed", None),
        confirm_prompt_first=args.confirm_prompt_first,
    )


def add_generation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--video", action="append", default=[])
    parser.add_argument("--audio", action="append", default=[])
    parser.add_argument("--duration", type=int)
    parser.add_argument("--ratio")
    parser.add_argument("--style")
    parser.add_argument("--generate-audio", action="store_true")
    parser.add_argument("--return-last-frame", action="store_true")
    parser.add_argument("--camera-fixed", dest="camera_fixed", action="store_true")
    parser.add_argument("--camera-move", dest="camera_fixed", action="store_false")
    parser.add_argument("--confirm-prompt-first", action="store_true")
    parser.set_defaults(camera_fixed=None)


def add_tracking_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--request-key", help="idempotency key for the current generation request")
    parser.add_argument("--conversation-key", help="conversation/session key used for single-active-task guard")
    parser.add_argument("--allow-parallel", action="store_true", help="allow creating a new task even if another task in the same conversation is still active")


def upsert_registry_record(record: Dict[str, Any]) -> Dict[str, Any]:
    registry = load_registry()
    task_id = record["task_id"]
    existing = registry["tasks"].get(task_id, {})
    merged = {**existing, **record, "updated_at": now_iso()}
    registry["tasks"][task_id] = merged

    request_key = merged.get("request_key")
    if request_key:
        registry["request_index"][request_key] = task_id

    conversation_key = merged.get("conversation_key")
    if conversation_key:
        registry["conversation_latest"][conversation_key] = task_id
        if is_active_status(merged.get("status")):
            registry["conversation_active"][conversation_key] = task_id
        elif registry["conversation_active"].get(conversation_key) == task_id:
            registry["conversation_active"].pop(conversation_key, None)

    save_registry(registry)
    return merged


def get_registry_record(task_id: str) -> Optional[Dict[str, Any]]:
    return load_registry().get("tasks", {}).get(task_id)


def resolve_existing_task(request_key: Optional[str], conversation_key: Optional[str]) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    registry = load_registry()
    tasks = registry.get("tasks", {})

    if request_key:
        task_id = registry.get("request_index", {}).get(request_key)
        if task_id and task_id in tasks:
            return tasks[task_id], "request_key"

    if conversation_key:
        task_id = registry.get("conversation_active", {}).get(conversation_key)
        if task_id and task_id in tasks:
            return tasks[task_id], "conversation_active"

        latest_task_id = registry.get("conversation_latest", {}).get(conversation_key)
        latest = tasks.get(latest_task_id) if latest_task_id else None
        if can_return_to_conversation(latest):
            return latest, "conversation_latest"

    return None, None


def resolve_task_id(task_id: Optional[str], request_key: Optional[str], conversation_key: Optional[str]) -> Optional[str]:
    if task_id:
        return task_id
    existing, _ = resolve_existing_task(request_key, conversation_key)
    if existing:
        return existing.get("task_id")
    return None


def build_registry_record_from_create(
    created: Dict[str, Any],
    intent: UserIntent,
    plan: GenerationPlan,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    output_dir = getattr(args, "output_dir", None)
    return {
        "task_id": created["task_id"],
        "status": created.get("status"),
        "request_key": getattr(args, "request_key", None),
        "conversation_key": getattr(args, "conversation_key", None),
        "intent_type": plan.intent_type,
        "entrypoint": plan.entrypoint,
        "mode": plan.mode,
        "prompt": intent.prompt,
        "prompt_fingerprint": compute_request_fingerprint(intent),
        "plan_brief": plan.plan_brief,
        "suggested_next_actions": plan.suggested_next_actions,
        "output_dir": output_dir,
        "video_url": None,
        "saved_path": None,
        "response_sent": False,
        "response_sent_at": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def sync_registry_from_status(result: Dict[str, Any], fallback_record: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    task_id = result.get("task_id")
    if not task_id:
        return None
    base = get_registry_record(task_id) or fallback_record or {"task_id": task_id}
    update = {
        **base,
        "task_id": task_id,
        "status": result.get("status"),
        "video_url": result.get("video_url") or base.get("video_url"),
    }
    if result.get("video_url") and not base.get("response_ready_at"):
        update["response_ready_at"] = now_iso()
    return upsert_registry_record(update)


def sync_registry_download(task_id: str, download: Dict[str, Any], fallback_record: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    base = get_registry_record(task_id) or fallback_record or {"task_id": task_id}
    status = base.get("status")
    if download.get("saved_path"):
        status = "downloaded"
    update = {
        **base,
        "task_id": task_id,
        "status": status,
        "video_url": download.get("video_url") or base.get("video_url"),
        "saved_path": download.get("saved_path") or base.get("saved_path"),
    }
    if download.get("saved_path") and not base.get("response_ready_at"):
        update["response_ready_at"] = now_iso()
    return upsert_registry_record(update)


def make_reuse_response(record: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        "status": "reused_existing_task",
        "message": reason,
        "task_id": record.get("task_id"),
        "record": record,
    }


def maybe_reuse_before_create(args: argparse.Namespace, plan: GenerationPlan) -> Optional[Dict[str, Any]]:
    request_key = getattr(args, "request_key", None)
    conversation_key = getattr(args, "conversation_key", None)
    allow_parallel = getattr(args, "allow_parallel", False)

    if not request_key and not conversation_key:
        return None

    existing, reason = resolve_existing_task(request_key, conversation_key)
    if not existing:
        return None

    if reason == "request_key":
        return make_reuse_response(existing, "matched existing request_key; skip duplicate create")

    if reason == "conversation_key" and not allow_parallel and is_active_status(existing.get("status")):
        return make_reuse_response(existing, "conversation already has an active task; skip duplicate create")

    return None


def run_reused_flow(existing: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    created = make_reuse_response(existing, "reused existing task instead of creating a new one")
    task_id = existing.get("task_id")
    if not task_id:
        return {"created": created}

    current_status = existing.get("status")
    output: Dict[str, Any] = {"created": created}

    if is_active_status(current_status):
        waited = wait_for_completion(
            task_id=task_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        record = sync_registry_from_status(waited, existing)
        output["waited"] = waited
    else:
        status_info = get_status(task_id)
        record = sync_registry_from_status(status_info, existing)
        output["waited"] = status_info

    video_url = output["waited"].get("video_url")
    saved_path = (record or {}).get("saved_path")
    if video_url and not args.no_download and not saved_path:
        download = download_video(video_url, args.output_dir)
        sync_registry_download(task_id, download, record)
        output["download"] = download
    elif saved_path:
        output["download"] = {
            "status": "already_downloaded",
            "message": "existing task result already downloaded",
            "video_url": (record or {}).get("video_url"),
            "saved_path": saved_path,
        }

    return output


def cli() -> None:
    parser = argparse.ArgumentParser(description="Seedance 2.0 Video Studio CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Build a generation plan from prompt and assets")
    add_generation_args(p_plan)

    p_create = sub.add_parser("create", help="Create generation task from prompt and assets")
    add_generation_args(p_create)
    add_tracking_args(p_create)

    p_status = sub.add_parser("status", help="Query task status")
    p_status.add_argument("task_id", nargs="?")
    p_status.add_argument("--request-key")
    p_status.add_argument("--conversation-key")

    p_wait = sub.add_parser("wait", help="Poll task status until completion")
    p_wait.add_argument("task_id", nargs="?")
    p_wait.add_argument("--request-key")
    p_wait.add_argument("--conversation-key")
    p_wait.add_argument("--poll-seconds", type=int, default=5)
    p_wait.add_argument("--timeout-seconds", type=int, default=900)

    p_download = sub.add_parser("download", help="Download video result")
    p_download.add_argument("video_url")
    p_download.add_argument("--output-dir", "--download-dir", dest="output_dir", default="/root/seedance2-video-studio/runtime/downloads")

    p_upload = sub.add_parser("upload-image", help="Upload local image to APIMart")
    p_upload.add_argument("file_path")

    p_run = sub.add_parser("run", help="Create task, wait, and optionally download result")
    add_generation_args(p_run)
    add_tracking_args(p_run)
    p_run.add_argument("--poll-seconds", type=int, default=5)
    p_run.add_argument("--timeout-seconds", type=int, default=900)
    p_run.add_argument("--output-dir", "--download-dir", dest="output_dir", default="/root/seedance2-video-studio/runtime/downloads")
    p_run.add_argument("--no-download", action="store_true")

    p_current = sub.add_parser("current", help="Show current or latest-returnable task for a request or conversation")
    p_current.add_argument("--request-key")
    p_current.add_argument("--conversation-key")

    p_mark = sub.add_parser("mark-sent", help="Mark a task as already returned to the chat/user")
    p_mark.add_argument("task_id")

    sub.add_parser("health", help="Check API connectivity and balance")

    args = parser.parse_args()

    if args.command == "current":
        existing, reason = resolve_existing_task(args.request_key, args.conversation_key)
        if not existing:
            print(json.dumps({"status": "not_found", "message": "no tracked task found"}, ensure_ascii=False, indent=2))
            return
        print(json.dumps({"status": "ok", "matched_by": reason, "record": existing}, ensure_ascii=False, indent=2))
        return

    if args.command in {"plan", "create", "run"}:
        intent = build_intent_from_args(args)
        mode = detect_mode(intent)
        plan = expand_prompt(intent, mode)

        if args.command == "plan":
            print(json.dumps(asdict(plan), ensure_ascii=False, indent=2))
            return

        reused = maybe_reuse_before_create(args, plan)
        if reused and args.command == "create":
            print(json.dumps(reused, ensure_ascii=False, indent=2))
            return
        if reused and args.command == "run":
            existing = reused.get("record") or {}
            print(json.dumps(run_reused_flow(existing, args), ensure_ascii=False, indent=2))
            return

        created = create_task(plan)
        task_id = created.get("task_id")
        record: Optional[Dict[str, Any]] = None
        if task_id:
            record = upsert_registry_record(build_registry_record_from_create(created, intent, plan, args))

        if args.command == "create":
            print(json.dumps(created, ensure_ascii=False, indent=2))
            return

        if not task_id:
            print(json.dumps(created, ensure_ascii=False, indent=2))
            return

        waited = wait_for_completion(
            task_id=task_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        record = sync_registry_from_status(waited, record)
        output = {
            "created": created,
            "waited": waited,
        }
        video_url = waited.get("video_url")
        if video_url and not args.no_download:
            download = download_video(video_url, args.output_dir)
            sync_registry_download(task_id, download, record)
            output["download"] = download
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if args.command == "status":
        task_id = resolve_task_id(args.task_id, args.request_key, args.conversation_key)
        if not task_id:
            print(json.dumps({"status": "not_found", "message": "no task_id found for this status query"}, ensure_ascii=False, indent=2))
            return
        result = get_status(task_id)
        sync_registry_from_status(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "wait":
        task_id = resolve_task_id(args.task_id, args.request_key, args.conversation_key)
        if not task_id:
            print(json.dumps({"status": "not_found", "message": "no task_id found for this wait query"}, ensure_ascii=False, indent=2))
            return
        result = wait_for_completion(task_id, args.poll_seconds, args.timeout_seconds)
        sync_registry_from_status(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "download":
        print(json.dumps(download_video(args.video_url, args.output_dir), ensure_ascii=False, indent=2))
    elif args.command == "upload-image":
        print(json.dumps(upload_image(args.file_path), ensure_ascii=False, indent=2))
    elif args.command == "mark-sent":
        record = get_registry_record(args.task_id)
        if not record:
            print(json.dumps({"status": "not_found", "message": "task not found"}, ensure_ascii=False, indent=2))
            return
        updated = upsert_registry_record({**record, "response_sent": True, "response_sent_at": now_iso()})
        print(json.dumps({"status": "ok", "record": updated}, ensure_ascii=False, indent=2))
    elif args.command == "health":
        adapter = Seedance2Adapter()
        print(json.dumps(adapter.health_check(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
