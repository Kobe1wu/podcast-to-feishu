"""
Groq Whisper 语音转文字
使用 Groq 免费 API，将长音频拆段后分段转录，解决输出截断问题
"""
import os
import requests
import tempfile
import subprocess
import math
from openai import OpenAI


MAX_FILE_SIZE = 25 * 1024 * 1024
CHUNK_SECONDS = 900  # 每段15分钟，避免Groq输出截断


def get_groq_client() -> OpenAI:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("请设置 GROQ_API_KEY 环境变量")
    return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")


def transcribe_audio(audio_url: str, podcast_name: str = "") -> str:
    client = get_groq_client()

    print(f"  [转录] 下载音频: {podcast_name}")
    local_path = download_audio(audio_url)
    file_size = os.path.getsize(local_path)
    print(f"  [转录] 音频大小: {file_size / 1024 / 1024:.1f}MB")

    # 如果超过25MB，先压缩
    if file_size > MAX_FILE_SIZE:
        print(f"  [转录] 音频超过25MB，正在压缩...")
        compressed = local_path + ".compressed.mp3"
        run_ffmpeg(["-y", "-i", local_path, "-b:a", "32k", "-ac", "1", "-ar", "16000", compressed])
        os.remove(local_path)
        local_path = compressed

    # 获取音频时长
    duration = float(run_ffmpeg(
        ["-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", local_path],
        cmd="ffprobe"
    ).stdout.strip())
    print(f"  [转录] 音频时长: {duration / 60:.1f} 分钟")

    # 如果短于15分钟，直接转录
    if duration <= CHUNK_SECONDS:
        print(f"  [转录] 单段转录 (whisper-large-v3)...")
        with open(local_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=f, response_format="text", language="zh",
            )
        result = transcript if isinstance(transcript, str) else str(transcript)
        cleanup(local_path)
        print(f"  [转录] 完成! 字数: {len(result)}")
        return result

    # 长音频：拆段转录
    chunks = math.ceil(duration / CHUNK_SECONDS)
    print(f"  [转录] 拆为 {chunks} 段，每段 15 分钟...")
    all_text = []

    for i in range(chunks):
        start = i * CHUNK_SECONDS
        chunk_path = f"{local_path}.chunk{i}.mp3"
        print(f"  [转录] 转录第 {i+1}/{chunks} 段 ({start//60}:00)...")

        run_ffmpeg(["-y", "-i", local_path, "-ss", str(start),
                     "-t", str(CHUNK_SECONDS), "-c:a", "libmp3lame",
                     "-b:a", "32k", "-ac", "1", "-ar", "16000", chunk_path])

        try:
            with open(chunk_path, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=f, response_format="text", language="zh",
                )
            text = transcript if isinstance(transcript, str) else str(transcript)
            all_text.append(text)
            print(f"  [转录] 第 {i+1} 段: {len(text)} 字")
        except Exception as e:
            print(f"  [转录] 第 {i+1} 段失败: {e}")
        finally:
            if os.path.exists(chunk_path):
                os.remove(chunk_path)

    cleanup(local_path)
    result = "\n\n".join(all_text)
    print(f"  [转录] 全部完成! 总计: {len(result)} 字")
    return result


def download_audio(url: str) -> str:
    local_filename = os.path.join(
        tempfile.gettempdir(),
        "podcast_" + url.split("/")[-1].split("?")[0][-40:] or "audio.mp3"
    )
    if not any(local_filename.endswith(ext) for ext in
               (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus")):
        local_filename += ".mp3"

    resp = requests.get(url, stream=True, timeout=600)
    resp.raise_for_status()

    with open(local_filename, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return local_filename


def run_ffmpeg(args: list, cmd: str = "ffmpeg") -> subprocess.CompletedProcess:
    result = subprocess.run([cmd] + args, capture_output=True, text=True, timeout=120)
    if result.returncode != 0 and cmd == "ffmpeg":
        raise Exception(f"{cmd} 失败: {result.stderr}")
    return result


def cleanup(path: str):
    try:
        os.remove(path)
    except OSError:
        pass
