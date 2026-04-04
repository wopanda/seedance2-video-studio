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
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Literal

from seedance2_adapter import Seedance2Adapter

Mode = Literal["text_only", "first_frame", "first_last_frame"]


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


DEFAULT_NEGATIVE = [
    "no subtitles",
    "no watermark",
    "no logo",
    "no on-screen text",
]


def detect_mode(intent: UserIntent) -> Mode:
    image_assets = [a for a in intent.assets if a.kind == "image"]
    if len(image_assets) >= 2:
        return "first_last_frame"
    if len(image_assets) == 1:
        return "first_frame"
    return "text_only"


def detect_confirmation_need(intent: UserIntent, mode: Mode) -> tuple[bool, Optional[str]]:
    if intent.confirm_prompt_first:
        return True, "user_requested_prompt_preview"
    image_assets = [a for a in intent.assets if a.kind == "image"]
    if len(image_assets) > 2:
        return True, "too_many_images_unclear_priority"
    return False, None


def expand_prompt(intent: UserIntent, mode: Mode) -> GenerationPlan:
    duration = intent.duration or 6
    ratio = intent.ratio or "9:16"
    style = intent.style or "cinematic realistic"
    needs_confirmation, reason = detect_confirmation_need(intent, mode)

    assets_mapping = []
    if mode == "first_frame":
        assets_mapping.append({"asset": "@image1", "role": "first frame / identity anchor"})
    elif mode == "first_last_frame":
        assets_mapping.append({"asset": "@image1", "role": "start frame / opening composition"})
        assets_mapping.append({"asset": "@image2", "role": "end frame / closing composition"})

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


def cli() -> None:
    parser = argparse.ArgumentParser(description="Seedance 2.0 Video Studio CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Build a generation plan from prompt and assets")
    add_generation_args(p_plan)

    p_create = sub.add_parser("create", help="Create generation task from prompt and assets")
    add_generation_args(p_create)

    p_status = sub.add_parser("status", help="Query task status")
    p_status.add_argument("task_id")

    p_wait = sub.add_parser("wait", help="Poll task status until completion")
    p_wait.add_argument("task_id")
    p_wait.add_argument("--poll-seconds", type=int, default=5)
    p_wait.add_argument("--timeout-seconds", type=int, default=900)

    p_download = sub.add_parser("download", help="Download video result")
    p_download.add_argument("video_url")
    p_download.add_argument("--output-dir", default="/root/seedance2-video-studio/runtime/downloads")

    p_upload = sub.add_parser("upload-image", help="Upload local image to APIMart")
    p_upload.add_argument("file_path")

    p_run = sub.add_parser("run", help="Create task, wait, and optionally download result")
    add_generation_args(p_run)
    p_run.add_argument("--poll-seconds", type=int, default=5)
    p_run.add_argument("--timeout-seconds", type=int, default=900)
    p_run.add_argument("--output-dir", default="/root/seedance2-video-studio/runtime/downloads")
    p_run.add_argument("--no-download", action="store_true")

    sub.add_parser("health", help="Check API connectivity and balance")

    args = parser.parse_args()

    if args.command in {"plan", "create", "run"}:
        intent = build_intent_from_args(args)
        mode = detect_mode(intent)
        plan = expand_prompt(intent, mode)

        if args.command == "plan":
            print(json.dumps(asdict(plan), ensure_ascii=False, indent=2))
            return

        created = create_task(plan)
        if args.command == "create":
            print(json.dumps(created, ensure_ascii=False, indent=2))
            return

        task_id = created.get("task_id")
        if not task_id:
            print(json.dumps(created, ensure_ascii=False, indent=2))
            return

        waited = wait_for_completion(
            task_id=task_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        output = {
            "created": created,
            "waited": waited,
        }
        video_url = waited.get("video_url")
        if video_url and not args.no_download:
            output["download"] = download_video(video_url, args.output_dir)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if args.command == "status":
        print(json.dumps(get_status(args.task_id), ensure_ascii=False, indent=2))
    elif args.command == "wait":
        print(json.dumps(wait_for_completion(args.task_id, args.poll_seconds, args.timeout_seconds), ensure_ascii=False, indent=2))
    elif args.command == "download":
        print(json.dumps(download_video(args.video_url, args.output_dir), ensure_ascii=False, indent=2))
    elif args.command == "upload-image":
        print(json.dumps(upload_image(args.file_path), ensure_ascii=False, indent=2))
    elif args.command == "health":
        adapter = Seedance2Adapter()
        print(json.dumps(adapter.health_check(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
