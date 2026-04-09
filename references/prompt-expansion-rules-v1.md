# 自动提示词扩展规则 V1

## 总原则
自动扩展不是把用户的话写得更长，而是把用户意图翻译成更适合 Seedance 2.0 的结构化输入。

默认策略：
- 优先保证可执行
- 优先保证一致性
- 优先保证短路径
- 非必要不升级到重度导演模式

## 扩展目标
AI 自动补：
- 意图类别（生成 / 复刻 / 延长 / 微调 / 补全 / 编辑）
- 素材角色映射（如有）
- 风格与色调
- 镜头节奏与三段式时间结构
- negative constraints
- generation settings

## 三层扩展

### 第 1 层：基础补全（默认）
默认补：
- duration（用户未指定时）
- ratio（用户未指定时）
- style（用户未指定时）
- 基础 negative constraints

### 第 2 层：结构化增强（默认轻量开启）
默认把需求整理成：
- 开场（建立场景）
- 中段（动作推进）
- 结尾（情绪/构图落点）

### 第 3 层：高级拓展（仅显式触发）
只有用户明确说：
- 先看 prompt
- 专业模式
- 分镜版
- 先出方案再生成

才展开：
- 更细的节奏控制
- 更完整的 continuity 控制
- 更细粒度的素材角色说明

## 意图驱动优先于模式驱动
先识别意图，再映射到模式。

映射建议：
- 生成 → text_only 或 first_frame
- 复刻 → first_frame / first_last_frame（按素材）
- 延长 → 预留 extend（V2）
- 微调 / 编辑 → 复用上次结果上下文 + 当前控制项
- 补全 → first_last_frame 或后续多段策略（V2+）

## 素材角色映射规则
不要只看素材数量，要看素材在本轮扮演的角色：
- 主体锚点（identity anchor）
- 首帧锚点（first frame）
- 尾帧锚点（last frame）
- 动作参考（motion reference）
- 风格参考（style reference）
- 音频节奏参考（rhythm reference）

如果角色冲突，先触发最短确认问句。

## 各模式扩展规则

### Text-only
自动补：
- 风格总纲
- 开场镜头
- 中段动作与推进
- 结尾落点
- negative constraints

### First Frame
自动补：
- `@image1` = first frame / identity anchor
- 开场保持首帧一致
- 中段动作变化
- 结尾清晰落点
- 连续性约束

### First + Last Frame
自动补：
- `@image1` = 起始锚点
- `@image2` = 结尾锚点
- 中段过渡逻辑
- 自然连续性要求
- 结尾构图收束

## 默认参数建议（可迭代）
- duration：6s（语义可触发 5/6/8）
- ratio：9:16（用户未指定时）
- style：cinematic realistic（用户未指定时）
- resolution：720p（默认）

## 默认 negative constraints
- no subtitles
- no watermark
- no logo
- no on-screen text

## 何时停止扩展、直接执行
满足以下条件，直接执行：
- 意图清楚
- 主素材清楚
- 不存在明显冲突
- 用户没要求先看方案/prompt

## 何时进入确认
- 多素材主次不清
- 新生成 / 延长冲突
- 风格目标冲突
- 用户主动要求先看方案

确认应只问一个关键问题，不做问卷。

## 后续可迭代项
- 风格词库
- 镜头模板
- 行业模板（广告 / 人像 / 产品 / 科普 / MV）
- Extend continuity 规则
- 结果卡“下一步动作”自动推荐策略
