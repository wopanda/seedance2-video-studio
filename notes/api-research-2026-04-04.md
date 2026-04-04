# 接口调研记录（当前可确认）

## 可确认事实
1. Seedance 2.0 官方页明确存在，且强调统一多模态（text/image/audio/video）输入。
2. 官方页可确认有 reference / extend 等能力关键词。
3. BytePlus Seedance 产品页可确认存在 API / pricing / dialogue / audio-visual generation 等能力描述。
4. 现成 `seedance-video-generation` skill 使用的是火山 Ark 风格任务接口，而不是明确标注为 Seedance 2.0 专属接口。

## 当前结论
在没有更稳定的一手公开 API 文档前：
- 我们可以确定交互与适配层需要支持 Seedance 2.0 的模式与能力设计。
- 但真实执行 adapter 目前仍缺少“明确可用且一手确认的 Seedance 2.0 官方 API 合约”。

## 对当前工程的影响
- 交互层继续按 Seedance 2.0 设计（已完成）
- adapter 层保持独立（已完成）
- 真正接入前，必须先补齐：认证方式、create/status/download 字段契约

## 下一步建议
1. 若你手上有 Seedance 2.0 平台文档 / API 文档 / 截图 / 开发者入口，可直接给我。
2. 拿到一手接口后，我可以很快把 adapter 接上。
