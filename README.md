# Seedance 2.0 Video Studio

一个可真实出片的 **Seedance 2.0 视频生成 skill**，当前已接通 **APIMart / doubao-seedance-2.0**。

## 当前状态
- 状态：**V1 可用**
- 已跑通：文生视频真实生成、任务轮询、结果下载
- 支持：文生视频 / 首帧图生 / 首尾帧过渡
- 当前重点：把本地可用版本整理成可安装、可发布的 skill 包

## 这个 skill 解决什么问题

用户不需要自己研究 mode、参数和 prompt 结构，只需要：
- 说想做什么视频
- 可选发图片

然后由 AI 自动：
- 判断模式
- 扩展提示词
- 调用 Seedance 2.0 接口生成
- 轮询任务状态
- 返回结果链接并下载视频

## 当前能力

### 支持
- 文生视频（text_only）
- 首帧图生（first_frame）
- 首尾帧过渡（first_last_frame）
- 轻量结构化提示词扩展
- 任务创建 / 状态查询 / 结果下载
- 图片上传到 APIMart 后再生成视频

### 暂不支持
- 多段自动拼接
- extend 连续视频
- 自动生图
- 完整剧本 / 分镜流水线
- 飞书结果自动回传稳定闭环（生成已通，消息回传仍待单独修）

## 最短成功路径

### 1）配置 API Key
推荐方式：
```bash
export APIMART_API_KEY='sk-...'
export APIMART_BASE_URL='https://api.apimart.ai'
export APIMART_MODEL='doubao-seedance-2.0'
```

也支持放在：
- `runtime/.env.local`

### 2）检查连通性
```bash
python3 scripts/seedance2_video.py health
```

### 3）直接跑一条视频
```bash
python3 scripts/seedance2_video.py run \
  --prompt '雨夜街头，女生慢慢回头看镜头，电影感' \
  --duration 5 \
  --ratio 9:16
```

### 4）图生视频
```bash
python3 scripts/seedance2_video.py run \
  --prompt '让人物自然转头看向镜头，电影感' \
  --image /path/to/image.jpg \
  --duration 6 \
  --ratio 9:16
```

## CLI 命令
- `health`：检查 APIMart key / 余额 / base_url
- `plan`：只看意图理解与参数展开
- `create`：只创建任务
- `status`：查询任务状态
- `wait`：轮询直到完成
- `download`：下载视频结果
- `upload-image`：上传本地图片到 APIMart
- `run`：一条龙执行 `create + wait + download`

## 设计文件
- `design-v1.md`：整体产品设计草案
- `references/interaction-spec-v1.md`：交互规格
- `references/prompt-expansion-rules-v1.md`：提示词自动扩展规则
- `references/execution-layer-v1.md`：执行层说明
- `references/apimart-seedance2-contract.md`：APIMart 接口梳理
- `runtime/api-contract-v1.md`：当前 API 合约
- `templates/examples.md`：输入样例
- `notes/roadmap.md`：迭代路线图

## 设计原则
- 默认简单，内部专业
- 人定方向，AI定做法
- 先把第一次成功路径做顺
- 先保证生成闭环，再优化飞书回传闭环

## 安全说明
- API Key 不要写进仓库文件
- `runtime/.env.local` 不应提交
- `runtime/downloads/` 不应提交
- 发布前应再次确认仓库里没有真实凭证与生成结果文件
