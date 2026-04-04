# 执行层说明

当前执行层是 **skeleton v1**。

已完成：
- 模式判断
- 提示词轻量扩展
- generation plan 结构化输出
- create/status 命令骨架

未完成：
- 真正的 Seedance 2.0 API 接入
- 轮询与下载
- 飞书媒体结果回传

## 当前可本地测试

```bash
python3 scripts/seedance2_video.py plan \
  --prompt "做一个 8 秒竖屏视频，雨夜街头，女生慢慢回头看镜头，电影感" \
  --duration 8 \
  --ratio 9:16
```

或：

```bash
python3 scripts/seedance2_video.py plan \
  --prompt "用这张图做首帧，生成一个 6 秒视频，人物从静止到微笑转头" \
  --image /tmp/firstframe.png
```
