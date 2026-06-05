"""
播客→飞书自动流水线主入口
GitHub Actions 定时触发，全云端运行
"""
import json
import os
import sys
import requests

# 添加 src 到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rss_checker import check_all
from transcriber import transcribe_audio
from summarizer import summarize_episode
from feishu_writer import FeishuClient


def main():
    print("=" * 50)
    print("🎧 播客→飞书 自动流水线")
    print("=" * 50)

    # 加载配置
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
    if not os.path.exists(config_path):
        print("[错误] 找不到 config.json")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 检查环境变量
    required_env = ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "GROQ_API_KEY",
                    "DEEPSEEK_API_KEY"]
    missing = [e for e in required_env if not os.environ.get(e)]
    if missing:
        print(f"[错误] 缺少环境变量: {', '.join(missing)}")
        sys.exit(1)

    # Step 1: 检查所有播客 RSS
    print("\n📡 Step 1: 检查播客更新")
    new_episodes = check_all(config)

    if not new_episodes:
        print("\n✅ 没有新节目，流程结束")
        return

    print(f"\n📋 共 {len(new_episodes)} 个新节目待处理")

    # Step 2-4: 逐个处理新节目
    feishu = FeishuClient()

    for idx, (eid, episode) in enumerate(new_episodes, 1):
        print(f"\n{'='*40}")
        print(f"[{idx}/{len(new_episodes)}] {episode['podcast']} - {episode['title']}")
        print(f"{'='*40}")

        # Step 2: 转写音频
        print("\n🔊 Step 2: 语音转文字")
        transcript = ""
        if episode.get("audio_url"):
            try:
                transcript = transcribe_audio(
                    episode["audio_url"],
                    podcast_name=episode["podcast"]
                )
            except Exception as e:
                print(f"  [跳过] 转录失败: {e}")
                transcript = ""
        else:
            print("  [跳过] 无音频链接")

        # Step 3: LLM 总结
        print("\n🤖 Step 3: AI 总结")
        summary = ""
        if transcript:
            try:
                summary = summarize_episode(
                    episode["podcast"],
                    episode["title"],
                    transcript,
                    show_notes=episode.get("summary", "")
                )
            except Exception as e:
                print(f"  [错误] 总结失败: {e}")
                summary = transcript[:2000] if transcript else ""
        else:
            # 无文字稿时用 Show Notes 做简要总结
            notes = episode.get("summary", "")[:3000]
            if notes:
                summary = f"本期内容摘要：\n\n{notes}"
            else:
                summary = f"【{episode['title']}】\n来自 {episode['podcast']}\n{episode.get('link', '')}"

        # Step 4: 写入飞书
        print("\n📝 Step 4: 写入飞书文档")
        try:
            doc_link = feishu.write_podcast_note(
                title=episode["title"],
                summary_text=summary,
                full_transcript=transcript if transcript else None,
                podcast_name=episode["podcast"],
                episode_link=episode.get("link", "")
            )
            print(f"\n✅ 完成! 飞书文档: {doc_link}")
            episode["doc_link"] = doc_link
        except Exception as e:
            print(f"  [错误] 写入飞书失败: {e}")
            episode["doc_link"] = "写入失败"

    print(f"\n{'='*50}")
    print(f"✅ 全部完成! 处理了 {len(new_episodes)} 个新节目")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
