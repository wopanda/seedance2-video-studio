# 结果卡规格 V1

## 目标
让每次返回不止“报结果”，还天然承接下一步操作。

## 卡片分层

### A. 创建中（submitted / pending / processing）
必须返回：
- 当前识别意图（生成 / 复刻 / 延长 / 微调 / 补全 / 编辑）
- 当前路径（text_only / first_frame / first_last_frame / extend*）
- 关键参数（duration / ratio / style）
- task_id
- 状态

可选返回：
- 素材角色摘要（如：image1=首帧锚点）
- 简短说明（1 句）

### B. 成功（completed）
必须返回：
- 视频结果（URL 或文件路径）
- 本轮摘要（系统按什么思路做的）

应返回：
- 3~4 个下一步动作建议：
  - 再来一版
  - 延长 4 秒
  - 更像广告
  - 人物别变

### C. 失败（failed / cancelled / timeout）
必须返回：
- 失败原因（尽量可读）
- 最短重试建议（1~2 条）

如与素材相关，应明确：
- 主素材不清
- 参考不兼容
- 素材角色冲突

## 文本口径模板

### 创建中模板
- 已按「{intent}」开始处理
- 路径：{path}
- 参数：{duration}s / {ratio} / {style}
- 任务：{task_id}
- 状态：{status}

### 成功模板
- 已完成：{intent}
- 输出：{video_url_or_file}
- 本轮处理：{summary}
- 你可以继续：{next_actions}

### 失败模板
- 本次未完成：{reason}
- 建议重试：{retry_hint}

## 数据结构建议（内部）
```json
{
  "intent": "generate",
  "path": "first_frame",
  "task_id": "task_xxx",
  "status": "processing",
  "params": {
    "duration": 6,
    "ratio": "9:16",
    "style": "cinematic realistic"
  },
  "summary": "以首帧锚定人物，补中段动作并保持结尾构图",
  "result": {
    "video_url": null,
    "local_file": null
  },
  "next_actions": ["再来一版", "延长 4 秒", "人物别变"]
}
```

## 约束
- 不在卡片里暴露过多技术术语
- 默认不输出完整 prompt
- 用户明确要求时，才补充 prompt 预览
