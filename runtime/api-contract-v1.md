# Seedance 2.0 API Contract V1（APIMart 版）

> 当前状态：已根据 APIMart 文档完成第一版接口契约收口，并补齐上传图片 / 创建任务 / 轮询等待 / 下载结果的执行链路。

## 基础信息
- Base URL: `https://api.apimart.ai`
- 认证: `Authorization: Bearer <API_KEY>`
- 当前接入模型: `doubao-seedance-2.0`
- 兼容快速版: `doubao-seedance-2.0-fast`

## 1. create_task

### Endpoint
`POST /v1/videos/generations`

### 典型请求体
```json
{
  "model": "doubao-seedance-2.0",
  "prompt": "小猫对着镜头打哈欠",
  "resolution": "720p",
  "size": "16:9",
  "duration": 5,
  "generate_audio": true,
  "return_last_frame": true,
  "image_with_roles": [
    {"url": "https://.../first.jpg", "role": "first_frame"},
    {"url": "https://.../last.jpg", "role": "last_frame"}
  ]
}
```

### 成功响应
```json
{
  "code": 200,
  "data": [
    {
      "status": "submitted",
      "task_id": "task_xxx"
    }
  ]
}
```

## 2. get_status

### Endpoint
`GET /v1/tasks/{task_id}?language=zh`

### 关键返回字段
- `data.id`
- `data.status` → `pending | processing | completed | failed | cancelled`
- `data.progress`
- `data.result.videos[0].url[0]`
- `data.result.thumbnail_url`

## 3. upload_image

### Endpoint
`POST /v1/uploads/images`

### 请求
- `multipart/form-data`
- 字段名：`file`

### 成功返回
```json
{
  "url": "https://upload.apimart.ai/...jpg"
}
```

## 4. 当前工程映射
- Text-only → 直接发送 `prompt`
- First Frame → 本地图片会先走 `upload_image`，再映射为 `image_with_roles=[{url, role:first_frame}]`
- First + Last Frame → 本地图片会先走 `upload_image`，再映射为 `image_with_roles=[{url, role:first_frame}, {url, role:last_frame}]`
- 本地图片 → 自动上传图片，再把 URL 注入生成请求
- 远程图片 URL → 直接注入生成请求
- 参考视频 `video_urls` / 参考音频 `audio_urls` → 当前支持远程 URL 直传
- `wait_for_completion(task_id)` → 轮询直到完成/失败/超时
- `download_result(video_url, output_dir)` → 下载生成结果

## 5. CLI 能力
- `health`
- `upload-image <file_path>`
- `plan --prompt ... [--image ...]`
- `create --prompt ... [--image ...]`
- `status <task_id>`
- `wait <task_id> [--download-dir DIR]`
- `run --prompt ... [--image ...] [--download-dir DIR]`

## 6. 当前保留项
- 飞书媒体回传还待补
- 本地视频/本地音频上传未接（当前 video/audio 仅支持远程 URL）
