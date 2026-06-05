# 播客 → 飞书 自动流水线

每天自动检查你的播客订阅，有新节目就：
1. 下载音频 → Groq Whisper 免费转录 → DeepSeek AI 总结 → 写入飞书文档

**完全云端运行，电脑关机也不影响。零成本，无需任何付费订阅。**

## 使用前准备

### 1. GitHub 仓库
把本项目推送到你的 GitHub 仓库（公有/私有都可）。

### 2. 飞书自建应用
在 https://open.feishu.cn 创建自建应用：
- 开通「文档」权限：`docx:document`
- 发布上线

### 3. Groq 免费账号（用于语音转文字）
在 https://console.groq.com 注册免费账号：
- **无需绑定信用卡**
- 点击 API Keys → 生成 Key（格式：`gsk_...`）
- 每日 2000 次请求，完全够用

### 4. DeepSeek API（用于 AI 总结）
在 https://platform.deepseek.com 注册获取 API Key
- 充 10 块钱能用半年，一次不到 1 分钱

### 5. 配置 GitHub Secrets

在 GitHub 仓库 → Settings → Secrets and variables → Actions 中添加：

| Secret 名称 | 说明 |
|---|---|
| `FEISHU_APP_ID` | 飞书自建应用的 App ID |
| `FEISHU_APP_SECRET` | 飞书自建应用的 App Secret |
| `GROQ_API_KEY` | Groq 免费 API Key（用于语音转文字） |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（用于总结） |

### 6. 编辑播客订阅列表

修改 `config.json`，添加你的播客 RSS 地址：

```json
{
  "podcasts": [
    { "name": "播客名称", "rss_url": "https://example.com/rss" }
  ]
}
```

## 工作流

- 默认每天北京时间 **08:00** 和 **20:00** 各检查一次
- 可在 GitHub Actions 页面手动触发（`workflow_dispatch`）
- 每次有新节目 → 自动在飞书创建文档

## 查看结果

打开飞书 App → 在「文档」中可以找到自动创建的播客笔记。
