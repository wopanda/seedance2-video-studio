#!/usr/bin/env python3
"""Seedance 2.0 adapter for APIMart.

Current implementation scope:
- health_check
- upload_image
- create_task
- get_status
- wait_for_completion
- download_result
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests


@dataclass
class AdapterResult:
    ok: bool
    status: str
    task_id: Optional[str] = None
    video_url: Optional[str] = None
    saved_path: Optional[str] = None
    error: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class Seedance2Adapter:
    TERMINAL_STATUSES = {"completed", "succeeded", "success", "failed", "error", "cancelled"}

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        runtime_env = self._load_runtime_env()
        self.api_key = api_key or runtime_env.get("APIMART_API_KEY") or os.environ.get("APIMART_API_KEY")
        self.base_url = (base_url or runtime_env.get("APIMART_BASE_URL") or os.environ.get("APIMART_BASE_URL") or "https://api.apimart.ai").rstrip("/")
        self.model = model or runtime_env.get("APIMART_MODEL") or os.environ.get("APIMART_MODEL") or "doubao-seedance-2.0"

    def _load_runtime_env(self) -> Dict[str, str]:
        env: Dict[str, str] = {}
        p = Path("/root/seedance2-video-studio/runtime/.env.local")
        if not p.exists():
            return env
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
        return env

    def _headers(self, json_body: bool = True) -> Dict[str, str]:
        if not self.api_key:
            raise RuntimeError("APIMART_API_KEY is not set")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    @staticmethod
    def _is_url(value: str) -> bool:
        return value.startswith("http://") or value.startswith("https://")

    def _request_json(
        self,
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        response = requests.request(
            method=method,
            url=url,
            json=payload,
            params=params,
            headers=self._headers(json_body=True),
            timeout=timeout,
        )
        data = response.json()
        if not response.ok:
            raise RuntimeError(str(data))
        return data

    def health_check(self) -> Dict[str, Any]:
        try:
            response = requests.get(
                f"{self.base_url}/v1/user/balance",
                headers=self._headers(json_body=False),
                timeout=30,
            )
            data = response.json()
            if not response.ok:
                return {
                    "ok": False,
                    "base_url": self.base_url,
                    "model": self.model,
                    "status_code": response.status_code,
                    "error": str(data),
                }
            return {
                "ok": True,
                "base_url": self.base_url,
                "model": self.model,
                "status_code": response.status_code,
                "data": data,
            }
        except Exception as e:
            return {"ok": False, "base_url": self.base_url, "model": self.model, "error": str(e)}

    def upload_image(self, file_path: str) -> AdapterResult:
        try:
            p = Path(file_path).expanduser().resolve()
            if not p.exists() or not p.is_file():
                return AdapterResult(ok=False, status="failed", error=f"image file not found: {file_path}")
            with open(p, "rb") as f:
                response = requests.post(
                    f"{self.base_url}/v1/uploads/images",
                    headers=self._headers(json_body=False),
                    files={"file": (p.name, f)},
                    timeout=120,
                )
            data = response.json()
            if not response.ok:
                return AdapterResult(ok=False, status="failed", error=str(data), raw=data)
            return AdapterResult(ok=True, status="uploaded", raw=data)
        except Exception as e:
            return AdapterResult(ok=False, status="failed", error=str(e))

    def _resolve_image_path_or_url(self, value: str) -> str:
        if self._is_url(value):
            return value
        upload = self.upload_image(value)
        if not upload.ok:
            raise RuntimeError(upload.error or f"failed to upload image: {value}")
        url = (upload.raw or {}).get("url")
        if not url:
            raise RuntimeError(f"upload returned no url for image: {value}")
        return url

    def _convert_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        settings = payload.get("generation_settings", {})
        req: Dict[str, Any] = {
            "model": settings.get("model") or self.model,
            "prompt": payload.get("prompt", ""),
            "resolution": settings.get("resolution", "720p"),
            "size": settings.get("ratio", "9:16"),
            "duration": settings.get("duration", 6),
            "generate_audio": settings.get("generate_audio", False),
            "return_last_frame": settings.get("return_last_frame", False),
        }

        if settings.get("camera_fixed") is not None:
            req["camera_fixed"] = settings.get("camera_fixed")

        assets: List[Dict[str, Any]] = payload.get("assets", [])
        image_assets = [a for a in assets if a.get("kind") == "image"]
        video_assets = [a for a in assets if a.get("kind") == "video"]
        audio_assets = [a for a in assets if a.get("kind") == "audio"]
        mode = payload.get("mode")

        if mode == "first_frame" and image_assets:
            req["image_with_roles"] = [
                {"url": self._resolve_image_path_or_url(image_assets[0]["path"]), "role": "first_frame"}
            ]
        elif mode == "first_last_frame" and len(image_assets) >= 2:
            req["image_with_roles"] = [
                {"url": self._resolve_image_path_or_url(image_assets[0]["path"]), "role": "first_frame"},
                {"url": self._resolve_image_path_or_url(image_assets[1]["path"]), "role": "last_frame"},
            ]
        elif image_assets:
            req["image_urls"] = [self._resolve_image_path_or_url(a["path"]) for a in image_assets]

        if video_assets:
            invalid = [a["path"] for a in video_assets if not self._is_url(a["path"])]
            if invalid:
                raise RuntimeError(
                    "video assets currently require remote URLs on APIMart: " + ", ".join(invalid)
                )
            req["video_urls"] = [a["path"] for a in video_assets]

        if audio_assets:
            invalid = [a["path"] for a in audio_assets if not self._is_url(a["path"])]
            if invalid:
                raise RuntimeError(
                    "audio assets currently require remote URLs on APIMart: " + ", ".join(invalid)
                )
            req["audio_urls"] = [a["path"] for a in audio_assets]

        return req

    def create_task(self, payload: Dict[str, Any]) -> AdapterResult:
        try:
            request_payload = self._convert_payload(payload)
            data = self._request_json(
                "POST",
                f"{self.base_url}/v1/videos/generations",
                payload=request_payload,
                timeout=120,
            )
            items = data.get("data") or []
            item = items[0] if isinstance(items, list) and items else {}
            return AdapterResult(
                ok=True,
                status=item.get("status", "submitted"),
                task_id=item.get("task_id"),
                raw={"request": request_payload, "response": data},
            )
        except Exception as e:
            return AdapterResult(ok=False, status="failed", error=str(e), raw=payload)

    @staticmethod
    def _extract_video_url(task_data: Dict[str, Any]) -> Optional[str]:
        result = task_data.get("result") or {}
        videos = result.get("videos") or []
        if not videos:
            return None
        first = videos[0] if isinstance(videos, list) else None
        if isinstance(first, dict):
            url_value = first.get("url")
            if isinstance(url_value, list) and url_value:
                return url_value[0]
            if isinstance(url_value, str):
                return url_value
        return None

    def get_status(self, task_id: str) -> AdapterResult:
        try:
            data = self._request_json(
                "GET",
                f"{self.base_url}/v1/tasks/{task_id}",
                params={"language": "zh"},
                timeout=60,
            )
            task = data.get("data") or {}
            return AdapterResult(
                ok=True,
                status=task.get("status", "unknown"),
                task_id=task.get("id") or task_id,
                video_url=self._extract_video_url(task),
                raw=data,
            )
        except Exception as e:
            return AdapterResult(ok=False, status="failed", task_id=task_id, error=str(e))

    def wait_for_completion(self, task_id: str, poll_seconds: int = 5, timeout_seconds: int = 900) -> AdapterResult:
        start = time.time()
        history: List[Dict[str, Any]] = []
        while True:
            current = self.get_status(task_id)
            history.append({
                "status": current.status,
                "video_url": current.video_url,
                "raw": current.raw,
                "error": current.error,
            })
            if not current.ok:
                current.raw = {"history": history}
                return current
            if current.status in self.TERMINAL_STATUSES:
                current.raw = {"history": history, "final": current.raw}
                return current
            if time.time() - start > timeout_seconds:
                return AdapterResult(
                    ok=False,
                    status="timeout",
                    task_id=task_id,
                    video_url=current.video_url,
                    error=f"timed out after {timeout_seconds}s",
                    raw={"history": history, "last": current.raw},
                )
            time.sleep(poll_seconds)

    def download_result(self, video_url: str, output_dir: str) -> AdapterResult:
        try:
            outdir = Path(output_dir).expanduser()
            outdir.mkdir(parents=True, exist_ok=True)
            filename = video_url.split("/")[-1].split("?")[0] or "seedance2_result.mp4"
            save_path = outdir / filename
            with requests.get(video_url, stream=True, timeout=300) as response:
                response.raise_for_status()
                with open(save_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            return AdapterResult(ok=True, status="downloaded", video_url=video_url, saved_path=str(save_path))
        except Exception as e:
            return AdapterResult(ok=False, status="failed", video_url=video_url, error=str(e))
