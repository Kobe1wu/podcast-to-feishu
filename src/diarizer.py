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
    """用 AI 识别并标注不同说话人，合并同说话人的连续发言"""
    client = get_client()

    max_chars = 12000
    text = transcript[:max_chars]

    system_prompt = """你是一个播客文字稿处理助手。请完成以下任务：

1. 识别文字稿中的不同说话人
2. 如果能推断出名字/称呼（如「浩哥」「小明」），使用实际称呼；否则用「主持人」「嘉宾」
3. **关键**：把同一个说话人的连续发言合并成完整的段落，不要逐句换行。一个说话人连续说的一段话应该写在一个段落里。

错误示例（不要这样）：
甲：大家好。
甲：今天聊AI。
乙：对，很有意思。

正确示例（要这样）：
甲：大家好。今天聊AI。

乙：对，很有意思。

4. 用段落间空行分隔不同说话人的切换，保留原文标点。"""

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请处理以下《{podcast_name}》播客文字稿：\n\n{text}"}
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
