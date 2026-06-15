"""
说话人识别模块 - DeepSeek AI 区分播客中的不同发言人
"""
import os
from openai import OpenAI


def get_client():
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("请设置 DEEPSEEK_API_KEY")
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def label_speakers(transcript: str, podcast_name: str) -> str:
    """用 AI 识别并标注不同说话人"""
    client = get_client()

    # 截取处理避免超出 token 限制
    max_chars = 12000
    text = transcript[:max_chars]

    system_prompt = """你是一个播客文字稿处理助手。请仔细阅读以下文字稿，识别出不同的说话人，并用以下格式标注：
- 如果能推断出说话人名字/称呼，使用实际名字
- 否则用「主持人」「嘉宾」或「甲」「乙」区分
- 保留原文标点，只添加说话人前缀

输出格式示例：
主持人：今天我们来聊聊AI...
嘉宾：对，最近大模型的进展确实很快...
主持人：那么先从OpenAI说起吧..."""

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请为以下《{podcast_name}》播客的文字稿标注说话人：\n\n{text}"}
            ],
            temperature=0.3,
            max_tokens=8192,
        )
        result = resp.choices[0].message.content
        if result:
            result += f"\n\n[注：篇幅限制，以上为前 {max_chars} 字的标注结果]"
        return result or transcript
    except Exception as e:
        print(f"  [说话人识别] 调用失败: {e}")
        return transcript
