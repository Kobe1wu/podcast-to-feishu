"""
RSS 播客订阅检查器
"""
import feedparser
import hashlib
import json
import os
import requests
from datetime import datetime, timezone
from typing import Optional

STATE_FILE = "state.json"

# xyzfm.space Tengine 服务端通过 UA ACL 黑名单拦截 feedparser 等非浏览器 User-Agent
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def load_state() -> dict:
    """加载已处理过的节目ID记录"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed": []}


def save_state(state: dict):
    """保存处理状态"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def episode_id(entry) -> str:
    """生成节目的唯一ID"""
    if hasattr(entry, "id") and entry.id:
        return hashlib.md5(entry.id.encode()).hexdigest()
    if hasattr(entry, "link") and entry.link:
        return hashlib.md5(entry.link.encode()).hexdigest()
    if hasattr(entry, "title") and entry.title:
        return hashlib.md5(entry.title.encode()).hexdigest()
    return None


def check_podcast(rss_url: str, podcast_name: str, state: dict) -> list:
    """
    检查单个播客的RSS，返回新节目列表
    返回: [(episode_id, episode_data), ...]
    """
    # 用浏览器 UA 绕过 xyzfm.space 的 Tengine UA ACL 黑名单
    headers = {"User-Agent": BROWSER_UA}
    try:
        resp = requests.get(rss_url, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise Exception(f"HTTP 请求失败: {e}")

    feed = feedparser.parse(resp.content)
    new_episodes = []

    processed = set(state.get("processed", []))

    for entry in feed.entries:
        eid = episode_id(entry)
        if eid is None:
            continue
        if eid in processed:
            continue

        # 提取音频URL
        audio_url = None
        for link in entry.get("links", []):
            if link.get("type", "").startswith("audio/"):
                audio_url = link.get("href")
                break
        # 也检查 enclosures
        for enc in entry.get("enclosures", []):
            if enc.get("type", "").startswith("audio/"):
                audio_url = enc.get("href")
                break

        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()

        episode = {
            "id": eid,
            "podcast": podcast_name,
            "title": entry.get("title", "无标题"),
            "summary": entry.get("summary", ""),
            "audio_url": audio_url,
            "published": published or datetime.now(timezone.utc).isoformat(),
            "link": entry.get("link", ""),
        }
        new_episodes.append((eid, episode))

    return new_episodes


def check_all(config: dict) -> list:
    """检查所有播客，返回新节目列表"""
    state = load_state()
    all_new = []

    for podcast in config.get("podcasts", []):
        name = podcast.get("name", "未知播客")
        rss_url = podcast.get("rss_url", "")
        if not rss_url:
            print(f"[跳过] {name}: 无 RSS 地址")
            continue

        print(f"[检查] {name}: {rss_url}")
        try:
            new = check_podcast(rss_url, name, state)
            all_new.extend(new)
            for eid, ep in new:
                state["processed"].append(eid)
                print(f"  [新] {ep['title']} ({ep.get('published', '')[:10]})")
        except Exception as e:
            print(f"  [错误] {name}: {e}")

    save_state(state)
    print(f"[完成] 共发现 {len(all_new)} 个新节目")
    return all_new
