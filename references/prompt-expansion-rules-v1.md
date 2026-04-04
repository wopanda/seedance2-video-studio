# 自动提示词扩展规则 V1

## 总原则
自动扩展不是把用户的话写得更长，而是把它翻译成更适合 Seedance 2.0 的结构化输入。

## 扩展目标
AI 自动补：
- mode
- 风格与色调
- 镜头节奏
- 时间结构
- negative constraints
- generation settings

## 三层扩展

### 第 1 层：基础补全（默认）
- duration 默认值
- ratio 默认值
- 基础风格
- 基础 negative constraints

### 第 2 层：结构化增强（默认轻量开启）
把需求整理成：
- 开场
- 中段
- 结尾

### 第 3 层：高级拓展（仅显式触发）
只有用户明确说先看 prompt / 专业模式 / 分镜版时才展开更多结构。

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

### First + Last Frame
自动补：
- `@image1` = 起始锚点
- `@image2` = 结尾锚点
- 中段过渡逻辑
- 自然连续性要求

## 默认 negative constraints
- no subtitles
- no watermark
- no logo
- no on-screen text

## 后续可迭代项
- 风格词库
- 镜头模板
- 行业模板（广告 / 人像 / 产品）
- Extend continuity 规则
