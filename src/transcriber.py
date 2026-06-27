"""
Groq Whisper 语音转文字
使用 Groq 免费 API 进行音频转录（whisper-large-v3，支持完整音频）
完全免费，无需信用卡
"""
import os
import requests
import tempfile
from openai import OpenAI


# Groq 最大支持 25MB 文件上传
MAX_FILE_SIZE = 25 * 1024 * 1024


def get_groq_client() -> OpenAI:
    """获取 Groq 客户端"""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("请设置 GROQ_API_KEY 环境变量")

    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1"
    )


def transcribe_audio(audio_url: str, podcast_name: str = "") -> str:
    """
    转写音频文件为文字
    使用 Groq Whisper API（完全免费）
    - whisper-large-v3: 支持完整音频时长（无30分钟限制）
    - 先下载音频到临时文件
    - 上传到 Groq 进行转录
    - 返回完整文字稿
    """
    client = get_groq_client()

    print(f"  [转录] 下载音频: {podcast_name}")
    local_path = download_audio(audio_url)

    file_size = os.path.getsize(local_path)
    print(f"  [转录] 音频大小: {file_size / 1024 / 1024:.1f}MB")

    # 检查文件大小限制
    if file_size > MAX_FILE_SIZE:
        print(f"  [转录] 音频超过25MB，正在压缩...")
        truncated_path = local_path + ".truncated.mp3"
        try:
            compress_audio(local_path, truncated_path)
            os.remove(local_path)
            local_path = truncated_path
            file_size = os.path.getsize(local_path)
            print(f"  [转录] 压缩后: {file_size / 1024 / 1024:.1f}MB")
        except Exception as e:
            print(f"  [转录] 压缩失败，尝试直接上传: {e}")

    print(f"  [转录] 调用 Groq Whisper API (whisper-large-v3)...")
    with open(local_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=audio_file,
            response_format="text",
            language="zh",
        )

    # 清理临时文件
    try:
        os.remove(local_path)
        if os.path.exists(local_path + ".truncated.mp3"):
            os.remove(local_path + ".truncated.mp3")
    except OSError:
        pass

    result = transcript if isinstance(transcript, str) else (transcript.text if hasattr(transcript, 'text') else str(transcript))
    print(f"  [转录] 完成! 字数: {len(result)}")
    return result


def download_audio(url: str) -> str:
    """下载音频到临时文件"""
    local_filename = os.path.join(
        tempfile.gettempdir(),
        "podcast_" + url.split("/")[-1].split("?")[0][-40:] or "audio.mp3"
    )
    if not any(local_filename.endswith(ext) for ext in (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus")):
        local_filename += ".mp3"

    resp = requests.get(url, stream=True, timeout=600)
    resp.raise_for_status()

    with open(local_filename, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return local_filename


def compress_audio(input_path: str, output_path: str):
    """用 ffmpeg 压缩音频（降低码率以满足25MB限制）"""
    import subprocess
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-b:a", "32k", "-ac", "1", "-ar", "16000", output_path],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise Exception(f"ffmpeg 压缩失败: {result.stderr}")


def estimate_cost(audio_minutes: float) -> str:
    """Groq 完全免费"""
    return "免费"
