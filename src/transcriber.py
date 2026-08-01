"""
Groq Whisper 语音转文字（含角色区分）
使用 Groq 免费 API，将长音频拆段后分段转录，解决输出截断问题。
转录后调用 DeepSeek，根据逐段时间戳为每段标注说话人（角色），
在每段前加【角色名】前缀，实现对话稿的角色区分。
"""
import os
import re
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


def get_deepseek_client() -> OpenAI:
    """用于角色区分（说话人标注）的 DeepSeek 客户端"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("请设置 DEEPSEEK_API_KEY 环境变量")
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


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

    # 收集带全局时间戳的片段
    segments = []

    # 如果短于15分钟，直接转录
    if duration <= CHUNK_SECONDS:
        print(f"  [转录] 单段转录 (whisper-large-v3)...")
        segments = _transcribe_chunk(client, local_path, 0)
        cleanup(local_path)
    else:
        # 长音频：拆段转录
        chunks = math.ceil(duration / CHUNK_SECONDS)
        print(f"  [转录] 拆为 {chunks} 段，每段 15 分钟...")
        for i in range(chunks):
            start = i * CHUNK_SECONDS
            chunk_path = f"{local_path}.chunk{i}.mp3"
            print(f"  [转录] 转录第 {i+1}/{chunks} 段 ({start//60}:00)...")

            run_ffmpeg(["-y", "-i", local_path, "-ss", str(start),
                         "-t", str(CHUNK_SECONDS), "-c:a", "libmp3lame",
                         "-b:a", "32k", "-ac", "1", "-ar", "16000", chunk_path])

            try:
                segs = _transcribe_chunk(client, chunk_path, start)
                segments.extend(segs)
                print(f"  [转录] 第 {i+1} 段: {len(segs)} 个片段")
            except Exception as e:
                print(f"  [转录] 第 {i+1} 段失败: {e}")
            finally:
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)

        cleanup(local_path)

    total_text = "".join(s["text"] for s in segments)
    print(f"  [转录] 全部完成! 片段数: {len(segments)}, 字数: {len(total_text)}")

    # 角色区分
    labeled = label_speakers(segments, podcast_name)
    result = "\n".join(labeled)
    print(f"  [角色] 标注完成! 字数: {len(result)}")
    return result


def _transcribe_chunk(client: OpenAI, path: str, offset: float) -> list:
    """转录单个音频片段，返回带全局时间戳的片段列表"""
    with open(path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=f,
            response_format="verbose_json",
            language="zh",
        )
    raw_segments = getattr(resp, "segments", None) or []
    out = []
    for seg in raw_segments:
        text = (seg.get("text") if isinstance(seg, dict) else getattr(seg, "text", "")) or ""
        text = text.strip()
        if text:
            start = (seg.get("start") if isinstance(seg, dict) else getattr(seg, "start", 0)) or 0
            out.append({"start": offset + float(start), "text": text})
    # 兜底：没有片段时退回整段文本
    if not out and getattr(resp, "text", ""):
        out.append({"start": offset, "text": resp.text.strip()})
    return out


def label_speakers(segments: list, podcast_name: str = "") -> list:
    """
    用 DeepSeek 为每段文字标注说话人（角色），返回带【角色名】前缀的片段列表。
    LLM 只返回“编号: 角色名”的标签映射，不在输出里复述原文，
    这样即使文字稿很长也不会被输出 token 上限截断。
    """
    if not segments:
        return []
    if len(segments) == 1:
        return [segments[0]["text"]]

    try:
        client = get_deepseek_client()
    except Exception as e:
        print(f"  [角色] 未配置 DeepSeek，跳过角色区分: {e}")
        return [s["text"] for s in segments]

    # 构造带全局编号的片段文本
    numbered = [f"{i}. {s['text']}" for i, s in enumerate(segments)]
    batches = _split_batches(numbered, max_chars=14000)
    role_def = None
    labels = {}

    for b in batches:
        try:
            batch_labels, role_def = _call_diarize(client, b, role_def, podcast_name)
            if batch_labels:
                labels.update(batch_labels)
        except Exception as e:
            print(f"  [角色] 单批标注失败，该批退回无标签: {e}")

    out = []
    for i, s in enumerate(segments):
        lab = labels.get(i)
        if not lab:
            lab = "未知"
        out.append(f"【{lab}】{s['text']}")
    return out


def _split_batches(numbered: list, max_chars: int = 14000) -> list:
    """把带编号的行拆成多个批次，保证每批总长度 <= max_chars 且不切断单行"""
    batches, cur, size = [], [], 0
    for line in numbered:
        if size + len(line) + 1 > max_chars and cur:
            batches.append(cur)
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        batches.append(cur)
    return batches


def _call_diarize(client, batch_lines, role_def, podcast_name):
    """调用 DeepSeek 标注。首个批次返回 (labels, role_def)，后续批次沿用 role_def。"""
    numbered_text = "\n".join(batch_lines)

    if role_def:
        system = ("你是播客角色标注助手。下面逐段文字带全局编号，已知角色定义已给出。"
                  "请严格沿用已有角色名，为每段输出 '<编号>: <角色名>'，每行一个，"
                  "不要额外解释，不要代码块。无法确定标注 '未知'。编号必须与输入一致。")
        user = f"已知角色定义：\n{role_def}\n\n逐段文字：\n{numbered_text}"
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.0, max_tokens=2000,
        )
        content = resp.choices[0].message.content or ""
        labels, _ = _parse_labels_only(content)
        return labels, role_def

    system = ("你是播客角色区分助手。下面逐段文字带全局编号。"
              "请：1) 先判断有几类说话人并定义角色名"
              "（有明确身份如主持/嘉宾就用身份名，否则用【主播A】【主播B】编号），"
              "用 '角色定义：' 开头、一行一个 '角色名：描述'；"
              "2) 再为每段标注，用 '标注：' 开头、每行 '<编号>: <角色名>'。"
              "不要代码块，不要其他解释。无法确定标注 '未知'。编号须与输入一致。")
    user = f"播客：{podcast_name}\n\n逐段文字：\n{numbered_text}"
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0.0, max_tokens=3000,
    )
    content = resp.choices[0].message.content or ""
    return _parse_def_and_labels(content)


def _parse_label_line(line: str):
    m = re.match(r"^\s*(\d+)\s*[:：]\s*(.+?)\s*$", line)
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None


def _parse_def_and_labels(content: str):
    """解析首批次返回：前半部分是角色定义，'标注：'之后是编号->角色映射"""
    parts = re.split(r"标注\s*[:：]", content, maxsplit=1)
    def_part = parts[0]
    label_part = parts[1] if len(parts) > 1 else ""
    role_def = re.sub(r"^角色定义\s*[:：]?\s*", "", def_part).strip()
    labels = {}
    for line in label_part.splitlines():
        r = _parse_label_line(line)
        if r:
            labels[r[0]] = r[1]
    return labels, role_def


def _parse_labels_only(content: str):
    labels = {}
    for line in content.splitlines():
        r = _parse_label_line(line)
        if r:
            labels[r[0]] = r[1]
    return labels, None


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
