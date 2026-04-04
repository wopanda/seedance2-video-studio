# APIMart / doubao-seedance-2.0 接口梳理

> 来源：`https://docs.apimart.ai/` 公开文档页（已查证存在 `doubao-seedance-2.0` 视频生成文档）

## 1. 基础信息

### Base URL
- `https://api.apimart.ai/v1`

### 认证方式
- Header: `Authorization: Bearer <token>`

### 模型名
- `doubao-seedance-2.0`
- `doubao-seedance-2.0-fast`

---

## 2. 创建视频任务

### Endpoint
- `POST /videos/generations`

### 最小文生请求体
```json
{
  "model": "doubao-seedance-2.0",
  "prompt": "小猫对着镜头打哈欠",
  "resolution": "720p",
  "size": "16:9",
  "duration": 5,
  "generate_audio": true
}
```

### 成功返回
```json
{
  "code": 200,
  "data": [
    {
      "status": "submitted",
      "task_id": "task_01KMCGF6BQGN3X28H3KSR50X5T"
    }
  ]
}
```

---

## 3. 查询任务状态

### Endpoint
- `GET /tasks/{task_id}?language=zh`

### 视频任务完成返回重点字段
```json
{
  "code": 200,
  "data": {
    "id": "task_xxx",
    "status": "completed",
    "progress": 100,
    "result": {
      "thumbnail_url": "...jpg",
      "videos": [
        {
          "url": ["...mp4"],
          "expires_at": 1762940095
        }
      ]
    }
  }
}
```

### 任务状态枚举
- `pending`
- `processing`
- `completed`
- `failed`
- `cancelled`

---

## 4. 图片上传

### Endpoint
- `POST /uploads/images`

### 用途
先上传图片，再把返回 URL 放进视频生成请求。

### 返回
```json
{
  "url": "https://upload.apimart.ai/f/image/...jpg",
  "filename": "photo.jpg"
}
```

---

## 5. Seedance 2.0 特有能力（文档可确认）
- 文生视频
- 图生视频
- 首帧 / 尾帧
- 参考视频
- 参考音频
- 有声视频
- return_last_frame
- adaptive 比例

---

## 6. 对当前 skill 的直接映射

### text_only
映射为：
- `model`
- `prompt`
- `resolution`
- `size`
- `duration`
- `generate_audio`

### first_frame
映射为：
- 先上传图片
- 再用图片 URL 进入视频生成请求
- 字段优先研究 `image_with_roles` / `image_urls`

### first_last_frame
映射为：
- 先上传两张图
- 再构造 `image_with_roles`:
  - `first_frame`
  - `last_frame`

---

## 7. 当前仍待代码中进一步确认的点
- `image_with_roles` 的完整请求示例
- `video_urls` / `audio_urls` 的完整请求体位置
- 失败响应的稳定字段结构
- 下载是否直接用 `result.videos[0].url[0]`
