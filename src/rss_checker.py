"""
RSS 播客订阅检查器
使用 xml.etree + requests 解析 RSS，避免 feedparser 兼容性问题
"""
import hashlib
import json
import os
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


STATE_FILE = "state.json"


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed": []}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def episode_id(entry: dict) -> str:
    for key in ["guid", "link", "title"]:
        val = entry.get(key, "")
        if val:
            return hashlib.md5(val.encode()).hexdigest()
    return None


def parse_rss(xml_text: str) -> list:
    """用 xml.etree 解析 RSS XML，返回条目列表"""
    # RSS 可能包含 HTML entities，需要先清理
    xml_clean = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;)', '&amp;', xml_text)
    root = ET.fromstring(xml_clean)
    items = []

    for item in root.iter("item"):
        entry = {
            "title": _text(item, "title"),
            "link": _text(item, "link"),
            "guid": _text(item, "guid"),
            "summary": _text(item, "description"),
            "published": _text(item, "pubDate"),
            "duration": _text(item, "duration", ns={"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}, xpath="itunes:duration"),
        }

        # 音频 enclosure
        enc = item.find("enclosure")
        if enc is not None:
            entry["audio_url"] = enc.get("url", "")

        # content:encoded (更多文字内容)
        for el in item:
            if el.tag.endswith("encoded") and "content" in el.tag:
                text = (el.text or "").strip()
                if text and len(text) > len(entry.get("summary", "")):
                    entry["summary"] = text

        items.append(entry)

    return items


def _text(parent, tag, ns=None, xpath=None):
    if xpath:
        el = parent.find(xpath, ns)
    else:
        el = parent.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""


def check_podcast(rss_url: str, podcast_name: str, state: dict) -> list:
    """检查单个播客的 RSS，返回新节目列表"""
    print(f"  [RSS] 下载 {rss_url}")
    resp = requests.get(rss_url, timeout=30)
    resp.raise_for_status()

    entries = parse_rss(resp.text)
    print(f"  [RSS] 解析到 {len(entries)} 个条目")

    processed = set(state.get("processed", []))
    new_episodes = []

    for entry in entries:
        eid = episode_id(entry)
        if eid is None or eid in processed:
            continue

        episode = {
            "id": eid,
            "podcast": podcast_name,
            "title": entry.get("title", "无标题"),
            "summary": entry.get("summary", ""),
            "audio_url": entry.get("audio_url", None),
            "published": entry.get("published", ""),
            "link": entry.get("link", ""),
        }
        new_episodes.append((eid, episode))

    return new_episodes


def check_all(config: dict) -> list:
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
                print(f"  [新] {ep['title'][:50]}")
        except Exception as e:
            print(f"  [错误] {name}: {e}")

    save_state(state)
    print(f"[完成] 共发现 {len(all_new)} 个新节目")
    return all_new
