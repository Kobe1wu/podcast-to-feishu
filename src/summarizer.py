"""
AI 总结模块 - 使用 DeepSeek API
将播客文字稿总结为结构化笔记
"""
import os
from openai import OpenAI


def get_llm_client() -> OpenAI:
    """获取 DeepSeek 客户端"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("请设置 DEEPSEEK_API_KEY 环境变量")

    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )


def summarize_episode(podcast_name: str, title: str, transcript: str, show_notes: str = "") -> str:
    """
    用 LLM 总结播客内容为结构化笔记

    返回格式化的 Markdown 文本，后续会写入飞书文档
    """
    client = get_llm_client()

    # 如果文字稿太长，分段后取首尾关键部分
    max_input_chars = 20000
    if len(transcript) > max_input_chars:
        half = max_input_chars // 2
        transcript = transcript[:half] + "\n\n...（中间内容省略）...\n\n" + transcript[-half:]

    system_prompt = """你是播客笔记整理助手。请将播客内容总结为结构化笔记，使用以下格式：

## 本期概要
2-3句话概括本期核心主题

## 核心观点
- 观点1：具体内容
- 观点2：具体内容
（列出 5-8 个核心观点，每个观点附带播客中的具体论据或例子）

## 关键金句
> "原文金句引用"
（摘录 3-5 句播客中有价值的原话）

## 思维启发
- 对投资/生活/工作有启发的观点
- 可以实践的行动建议

## 延伸信息
- 提到的书籍、人物、产品、公司等（如果能识别出来）"""

    user_prompt = f"""播客：{podcast_name}
标题：{title}

Show Notes：
{show_notes[:2000] if show_notes else '无'}

文字稿：
{transcript}

请按要求的格式生成结构化总结笔记。每个部分都要充实，不要只列一个点。"""

    print(f"  [总结] 调用 DeepSeek API 生成总结...")

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        max_tokens=6000,
    )

    summary = response.choices[0].message.content
    print(f"  [总结] 完成! 字数: {len(summary)}")

    return summary
