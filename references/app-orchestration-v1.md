# App Orchestration V1

## 一句话原则
- 大模型只负责理解用户想做什么
- 代码负责任务编排、去重、状态跟踪、结果回传

## 必须由代码锁死的部分
1. 同一个请求只 create 一次
2. follow-up（“怎么样了/到哪一步了”）只能查进度，不能重新 create
3. 生成完成后必须走结果回传
4. 已回传前，同 request_key 不允许重复下单

## 推荐链路
用户消息
→ `plan` / 意图识别
→ `create` 或复用已有 task
→ 持久化 `{message_id, request_key, conversation_key, task_id, status}`
→ 后续只 `status/wait`
→ `download`
→ 应用层调用消息发送，把文件或 URL 回到当前会话
→ `mark-sent`

## 现在 skill 新增的编排能力
- `--request-key`
- `--conversation-key`
- `current`
- `mark-sent`
- 本地 `task_registry.json` 台账

## 应用层最小接法
### 首次生成
- 给 create/run 传 `request_key` 和 `conversation_key`
- 如果返回 `reused_existing`，不要再 create

### 用户追问进度
- 先 `current --conversation-key ...`
- 查到 task_id 后只跑 `status` 或 `wait`

### 结果回传
- 先 `current --conversation-key ...` 拿到最近待回传任务
- 优先发本地文件
- 发不了就发 video_url
- 成功回传后执行 `mark-sent <task_id>`

## 为什么这套更稳
因为视频生成是贵任务：
- 不能靠大模型临场判断是否重跑
- 必须让代码把“下单、查单、回传”三件事分清楚
