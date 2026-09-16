"""
音频链路探针（诊断用，不写飞书、不改 state）

用途：当「飞书文档总结简陋 / 没有完整文字稿」时，定位转录链路的真实断点。
流程：取配置里第一个播客的最新一集 → 下载 → ffprobe 取时长 → 判断并执行压缩
      → 切出 60s 样本 → Groq 试转一小段。

每一步都记录耗时、异常类型与完整 traceback；结果写入 PROBE_RESULT.md。
（Actions 日志下载需鉴权，写文件可用 raw 直接读取，沿用本仓库既有做法。）

注意：本脚本只调用现有 transcriber 函数，不修改任何业务逻辑，
      目的是先看清「原代码断在哪一步」。

用法：
  在 Actions 手动触发 workflow，或 push 本文件；
  本地执行：python src/probe_audio.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

import transcriber
from rss_checker import parse_rss

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_PATH = os.path.join(REPO_ROOT, "PROBE_RESULT.md")
MAX_TRACEBACK_LINES = 25

LINES = []
RESULTS = []
TMP_FILES = []


def log(msg=""):
    text = str(msg)
    print(text)
    LINES.append(text)


def record(step, status, detail=""):
    RESULTS.append((step, status, detail))


def section(title):
    log()
    log("=" * 64)
    log(title)
    log("=" * 64)


def guard(step_name, fn, fatal=False):
    """执行一步，记录耗时/异常/traceback。fatal=True 时失败即终止探针。"""
    log()
    log(f"[{step_name}]")
    t0 = time.time()
    try:
        result = fn()
        cost = time.time() - t0
        log(f"  结果: OK  (耗时 {cost:.1f}s)")
        record(step_name, "OK", f"{cost:.1f}s")
        return result
    except subprocess.TimeoutExpired as e:
        cost = time.time() - t0
        log(f"  结果: 超时！(耗时 {cost:.1f}s, 上限 {e.timeout}s)")
        log("  >>> 关键线索：命令被 run_ffmpeg 的 timeout 截断 <<<")
        record(step_name, "TIMEOUT", f"上限 {e.timeout}s，已跑 {cost:.1f}s")
        if fatal:
            finish()
            sys.exit(0)
        return None
    except Exception as e:
        cost = time.time() - t0
        log(f"  结果: FAIL (耗时 {cost:.1f}s)")
        log(f"  异常: {type(e).__name__}: {e}")
        log("  --- traceback ---")
        for line in traceback.format_exc().splitlines()[-MAX_TRACEBACK_LINES:]:
            log("  " + line)
        record(step_name, "FAIL", f"{type(e).__name__}: {str(e)[:120]}")
        if fatal:
            finish()
            sys.exit(0)
        return None


def track(path):
    if path:
        TMP_FILES.append(path)
    return path


def cleanup():
    for p in TMP_FILES:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def fetch_latest_episode(rss_url):
    resp = requests.get(rss_url, timeout=60)
    resp.raise_for_status()
    items = parse_rss(resp.text)
    if not items:
        raise RuntimeError("RSS 里没有解析到任何条目")
    return items[0], len(items)


def ffprobe_duration(path):
    """完全复现原逻辑：run_ffmpeg(cmd='ffprobe') 不检查 returncode，
    取 stdout 直接 float()。先把原始 stdout/stderr 打出来便于判断。"""
    proc = transcriber.run_ffmpeg(
        ["-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        cmd="ffprobe",
    )
    log(f"  ffprobe returncode : {proc.returncode}")
    log(f"  ffprobe stdout     : {proc.stdout.strip()[:200]!r}")
    log(f"  ffprobe stderr     : {proc.stderr.strip()[:300]!r}")
    return float(proc.stdout.strip())


def compress_whole(path, out):
    t = time.time()
    transcriber.run_ffmpeg(
        ["-y", "-i", path, "-b:a", "32k", "-ac", "1", "-ar", "16000", out]
    )
    cost = time.time() - t
    size = os.path.getsize(out) if os.path.exists(out) else 0
    log(f"  压缩后大小 : {size / 1024 / 1024:.1f} MB")
    log(f"  压缩耗时   : {cost:.1f}s (run_ffmpeg 内部上限 120s)")
    if size > transcriber.MAX_FILE_SIZE:
        log(f"  [!] 压缩后仍超过 {transcriber.MAX_FILE_SIZE / 1024 / 1024:.0f} MB 上限")
    return size


def make_sample(src, out, seconds=60):
    transcriber.run_ffmpeg(
        ["-y", "-i", src, "-t", str(seconds), "-c:a", "libmp3lame",
         "-b:a", "32k", "-ac", "1", "-ar", "16000", out]
    )
    size = os.path.getsize(out) if os.path.exists(out) else 0
    log(f"  样本大小 : {size / 1024:.0f} KB")
    return out


def groq_probe(sample):
    client = transcriber.get_groq_client()
    t = time.time()
    with open(sample, "rb") as fh:
        resp = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=fh,
            response_format="verbose_json",
            language="zh",
        )
    cost = time.time() - t
    segs = getattr(resp, "segments", None) or []
    text = (getattr(resp, "text", "") or "").strip()
    log(f"  调用耗时       : {cost:.1f}s")
    log(f"  返回 segments  : {len(segs)} 个")
    log(f"  返回 text 字数 : {len(text)}")
    log(f"  文本样例       : {text[:150]}")
    if not segs and not text:
        raise RuntimeError("Groq 返回既无 segments 也无 text")
    return len(text)


def write_report():
    out = [
        "# 音频链路探针结果",
        "",
        f"生成时间（UTC）: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}",
        "",
        "## 分步结论",
        "",
        "| 步骤 | 结果 | 备注 |",
        "|---|---|---|",
    ]
    for step, status, detail in RESULTS:
        mark = {"OK": "通过", "FAIL": "**失败**", "TIMEOUT": "**超时**"}.get(status, status)
        out.append(f"| {step} | {mark} | {detail} |")

    failed = [r for r in RESULTS if r[1] != "OK"]
    out += ["", "## 一句话诊断", ""]
    if not failed:
        out.append("音频链路（下载 / 探测 / 压缩 / 切片 / Groq 试转）全部通过。")
        out.append("")
        out.append("→ 断点不在 ffmpeg 侧。下一步应检查：Groq 长音频输出截断、")
        out.append("  免费额度限流，或 transcribe_audio 里「逐片失败被 except 吞掉」")
        out.append("  导致 segments 为空而函数仍正常返回空串。")
    else:
        first = failed[0]
        out.append(f"**最先失败的步骤：{first[0]}** —— {first[2]}")
        out.append("")
        out.append("→ 这一步就是静默失败链的起点。它被 except 吞掉后 transcript 变空，")
        out.append("  文档于是退化成没有结构的占位文案。")

    out += ["", "## 原始输出", "", "```"]
    out.extend(LINES)
    out.append("```")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def finish():
    write_report()
    log()
    log(f"报告已写入: {REPORT_PATH}")


def main():
    section("音频链路探针 —— 定位转录失败的真实断点")

    log()
    log("[环境]")
    log(f"  Python       : {sys.version.split()[0]}")
    log(f"  ffmpeg 路径  : {shutil.which('ffmpeg') or '(未找到)'}")
    log(f"  ffprobe 路径 : {shutil.which('ffprobe') or '(未找到)'}")
    log(f"  GROQ_API_KEY : {'已配置' if os.environ.get('GROQ_API_KEY') else '未配置'}")
    log(f"  DEEPSEEK_KEY : {'已配置' if os.environ.get('DEEPSEEK_API_KEY') else '未配置'}")
    log(f"  CHUNK_SECONDS: {transcriber.CHUNK_SECONDS}")
    log(f"  MAX_FILE_SIZE: {transcriber.MAX_FILE_SIZE / 1024 / 1024:.0f} MB")
    if shutil.which("ffmpeg"):
        try:
            v = subprocess.run(["ffmpeg", "-version"], capture_output=True,
                               text=True, timeout=30)
            log(f"  ffmpeg 版本  : {v.stdout.splitlines()[0] if v.stdout else '未知'}")
        except Exception as e:
            log(f"  ffmpeg 版本  : 读取失败 {e}")

    with open(os.path.join(REPO_ROOT, "config.json"), "r", encoding="utf-8") as f:
        config = json.load(f)
    podcasts = config.get("podcasts", [])
    if not podcasts:
        log("[致命] config.json 里没有播客配置")
        record("读取配置", "FAIL", "无 podcasts")
        finish()
        return

    first = podcasts[0]
    log()
    log(f"探测对象 : {first.get('name')}")
    log(f"RSS      : {first.get('rss_url')}")

    got = guard("拉取 RSS 并取最新一集", lambda: fetch_latest_episode(first["rss_url"]), fatal=True)
    if not got:
        finish()
        return
    entry, total = got
    title = (entry.get("title") or "").strip()
    audio_url = entry.get("audio_url") or ""
    rss_duration = (entry.get("duration") or "").strip()
    log(f"  条目总数     : {total}")
    log(f"  最新一集标题 : {title[:60]}")
    log(f"  RSS 声明时长 : {rss_duration or '(空)'}")
    log(f"  音频地址     : {audio_url[:110]}")

    if not audio_url:
        log("[致命] 该集没有 audio_url，无法继续")
        record("检查音频地址", "FAIL", "audio_url 为空")
        finish()
        return
    record("检查音频地址", "OK", "audio_url 存在")

    local_path = guard("下载音频", lambda: track(transcriber.download_audio(audio_url)), fatal=True)
    if not local_path:
        finish()
        return

    size = os.path.getsize(local_path)
    need_compress = size > transcriber.MAX_FILE_SIZE
    log(f"  本地文件   : {local_path}")
    log(f"  文件大小   : {size / 1024 / 1024:.1f} MB ({size} 字节)")
    log(f"  是否需压缩 : {'是' if need_compress else '否'}")
    record("下载音频", "OK", f"{size / 1024 / 1024:.1f} MB")

    duration = guard("ffprobe 取时长（原逻辑）", lambda: ffprobe_duration(local_path))
    if duration:
        log(f"  解析出的时长 : {duration:.1f}s = {duration / 60:.1f} 分钟")
        chunks = max(1, -(-int(duration) // transcriber.CHUNK_SECONDS))
        log(f"  预计切片数   : {chunks}（阈值 {transcriber.CHUNK_SECONDS}s）")
    else:
        log("  ffprobe 解析失败 —— 原代码此处会抛 ValueError，导致整集转录被跳过")

    if need_compress:
        out = track(local_path + ".compressed.mp3")
        log()
        log("  说明：下一步复现原代码的整文件压缩，run_ffmpeg 内部 timeout=120s。")
        log("        若在此超时，即为转录失败的起点。")
        guard("整文件压缩（原逻辑 120s 上限）", lambda: compress_whole(local_path, out))

    sample = track(os.path.join(tempfile.gettempdir(), "probe_sample.mp3"))
    guard("切出 60s 样本", lambda: make_sample(local_path, sample))

    if not os.path.exists(sample):
        log()
        log("[跳过] 样本未生成，无法测试 Groq")
        record("Groq 试转样本", "FAIL", "样本未生成")
        cleanup()
        finish()
        return

    if not os.environ.get("GROQ_API_KEY"):
        log()
        log("[跳过] 未配置 GROQ_API_KEY，无法验证转录调用")
        record("Groq 试转样本", "FAIL", "缺少 GROQ_API_KEY")
        cleanup()
        finish()
        return

    guard("Groq 试转样本", lambda: groq_probe(sample))

    cleanup()
    finish()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log()
        log("[探针自身异常]")
        log(traceback.format_exc())
        try:
            finish()
        except Exception:
            pass
