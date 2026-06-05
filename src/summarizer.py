"""
AI 总结模块 - 使用 DeepSeek API
将播客文字稿总结为结构化笔记
"""
import os
import json
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

    # 如果文字稿太长，截取前 15000 字
    max_chars = 15000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n\n...（文字稿过长已截断）"

    system_prompt = """你是播客笔记整理助手。请将播客内容总结为结构化笔记，使用以下格式：

## 📝 本期概要
2-3句话概括本期核心主题

## 🎯 核心观点/要点
- 要点1: 具体内容
- 要点2: 具体内容
- ...

## 💡 关键金句
> "原文金句引用"

## 📋 思维启发
- 对我有启发的观点或可实践的行动建议

## 📎 延伸信息
- 提到的书籍、人物、产品等"""

    user_prompt = f"""播客: {podcast_name}
标题: {title}

Show Notes:
{show_notes[:2000] if show_notes else '无'}

文字稿:
{transcript}

请按要求的格式生成结构化总结笔记。"""

    print(f"  [总结] 调用 DeepSeek API 生成总结...")

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        max_tokens=2000,
    )

    summary = response.choices[0].message.content
    print(f"  [总结] 完成! 字数: {len(summary)}")

    return summary
