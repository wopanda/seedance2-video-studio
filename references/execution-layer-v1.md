# 执行层说明 V1.1

## 当前状态
当前执行层为 **V1.1 可用**，已接通 APIMart / doubao-seedance-2.0。

已具备：
- 模式判断（text_only / first_frame / first_last_frame）
- 提示词轻量扩展
- generation plan 结构化输出
- 创建任务（create）
- 状态查询（status）
- 轮询等待（wait）
- 结果下载（download）
- 图片上传（upload-image）
- 一条龙执行（run = create + wait + download）
- 请求去重（request_key）
- 会话单任务锁（conversation_key）
- 当前/待回传任务查询（current）
- 回传完成标记（mark-sent）
- `--download-dir` 兼容别名

## 当前执行链路
1. 读取用户输入与素材
2. 规划层产出 generation plan
3. 若传入 `request_key` / `conversation_key`，先查本地任务登记表
4. 若已存在同请求或同会话活跃任务，则复用已有 task，不重复 create
5. 如无可复用任务，再调用 `/v1/videos/generations` 创建任务
6. 轮询 `/v1/tasks/{task_id}` 直到完成/失败/超时
7. 成功则下载结果并更新本地登记表
8. 应用层成功把文件/链接发回聊天后，执行 `mark-sent`

## 为什么这样改
视频生成是高成本动作，不能靠大模型临场判断“是不是该重新下单”。

需要把这些动作锁进代码逻辑：
- 同一请求只创建一次
- 问进度不等于重新生成
- 同一会话同时只跑一条活跃任务
- 已下载结果优先复用，不重复下载

## CLI 能力
```bash
python3 scripts/seedance2_video.py --help
```

子命令：
- `plan`
- `create`
- `status`
- `wait`
- `download`
- `upload-image`
- `run`
- `current`
- `mark-sent`
- `health`

## 推荐接法（应用层）
应用层在调用 `create` / `run` 时，应显式传入：
- `--request-key <message_id or dedupe_key>`
- `--conversation-key <chat/session id>`

这样才能稳定做到：
- 重复消息不重复创建
- 问进度时只查现有任务
- 同一会话避免并发多条贵任务

## 当前可本地验证

### 1）规划层验证（无需 API key）
```bash
python3 scripts/seedance2_video.py plan \
  --prompt "做一个 6 秒竖屏视频，雨夜街头，女生慢慢回头看镜头，电影感" \
  --duration 6 \
  --ratio 9:16
```

### 2）当前任务查询（无需新建任务）
```bash
python3 scripts/seedance2_video.py current \
  --request-key demo-request
```

### 3）兼容旧参数名
```bash
python3 scripts/seedance2_video.py run \
  --prompt "demo" \
  --download-dir /tmp/out \
  --no-download
```

## 已知边界
- 飞书媒体自动回传仍需由应用层接住（推荐：`current` → 发文件/URL → `mark-sent`）
- 本地视频/本地音频上传未接（当前 video/audio 仅支持远程 URL）
- Extend 能力预留在 V2

## 设计约束
执行层负责：
- 一次下单
- 状态跟踪
- 本地结果落盘
- 防重复与防并发

聊天消息回传（把文件真正发回会话）仍应由应用层编排接住。
