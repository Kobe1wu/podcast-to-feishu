# 音频链路探针结果

生成时间（UTC）: 2026-09-16 13:33:56

## 分步结论

| 步骤 | 结果 | 备注 |
|---|---|---|
| 拉取 RSS 并取最新一集 | 通过 | 0.4s |
| 检查音频地址 | 通过 | audio_url 存在 |
| 下载音频 | 通过 | 1.2s |
| 下载音频 | 通过 | 48.2 MB |
| ffprobe 取时长（原逻辑） | 通过 | 0.1s |
| 整文件压缩（原逻辑 120s 上限） | 通过 | 18.4s |
| 切出 60s 样本 | 通过 | 0.4s |
| Groq 试转样本 | 通过 | 1.8s |

## 一句话诊断

音频链路（下载 / 探测 / 压缩 / 切片 / Groq 试转）全部通过。

→ 断点不在 ffmpeg 侧。下一步应检查：Groq 长音频输出截断、
  免费额度限流，或 transcribe_audio 里「逐片失败被 except 吞掉」
  导致 segments 为空而函数仍正常返回空串。

## 原始输出

```

================================================================
音频链路探针 —— 定位转录失败的真实断点
================================================================

[环境]
  Python       : 3.11.16
  ffmpeg 路径  : /usr/bin/ffmpeg
  ffprobe 路径 : /usr/bin/ffprobe
  GROQ_API_KEY : 已配置
  DEEPSEEK_KEY : 已配置
  CHUNK_SECONDS: 900
  MAX_FILE_SIZE: 25 MB
  ffmpeg 版本  : ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023 the FFmpeg developers

探测对象 : 三点下班
RSS      : https://feed.xyzfm.space/tlel9j4tg3eu

[拉取 RSS 并取最新一集]
  结果: OK  (耗时 0.4s)
  条目总数     : 128
  最新一集标题 : 空仓--用AI，从“上头”拉回“理性”
  RSS 声明时长 : 00:52:00
  音频地址     : https://dts-api.xiaoyuzhoufm.com/track/62bd91adf288fd4eae3606ff/6a90fcda1352af56ff3d48fc/media.xyzcdn.net/62bd

[下载音频]
  结果: OK  (耗时 1.2s)
  本地文件   : /tmp/podcast_liZGdisOpH_r6exYnzGYDa3qsquY.m4a
  文件大小   : 48.2 MB (50508146 字节)
  是否需压缩 : 是

[ffprobe 取时长（原逻辑）]
  ffprobe returncode : 0
  ffprobe stdout     : '3120.100000'
  ffprobe stderr     : ''
  结果: OK  (耗时 0.1s)
  解析出的时长 : 3120.1s = 52.0 分钟
  预计切片数   : 4（阈值 900s）

  说明：下一步复现原代码的整文件压缩，run_ffmpeg 内部 timeout=120s。
        若在此超时，即为转录失败的起点。

[整文件压缩（原逻辑 120s 上限）]
  压缩后大小 : 11.9 MB
  压缩耗时   : 18.4s (run_ffmpeg 内部上限 120s)
  结果: OK  (耗时 18.4s)

[切出 60s 样本]
  样本大小 : 235 KB
  结果: OK  (耗时 0.4s)

[Groq 试转样本]
  调用耗时       : 1.8s
  返回 segments  : 20 个
  返回 text 字数 : 211
  文本样例       : 本期节目由千文赞助播出千文上线工作助理模式会思考更会行动是你靠谱的AI助手帮助我们做好日常投资的研究和其他的办公需求大家好欢迎收听三点下班这是一档有趣又有料的投资陪伴型节目每期围绕着股市和股民生活随便聊聊我是李永浩我是殷晨上期我们聊了整个上半年的总结复盘和一些感受评论区很多人说希望能够有一些更具体的
  结果: OK  (耗时 1.8s)
```
