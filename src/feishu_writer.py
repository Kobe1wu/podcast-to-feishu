"""
飞书文档写入模块
将播客笔记写入飞书文档
"""
import os
import re
import requests
import time
from typing import Optional

BASE_URL = "https://open.feishu.cn/open-apis"


def clean_html(text: str) -> str:
    """清洗 HTML 标签和特殊字符，返回纯文本"""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    import html
    text = html.unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    return text


class FeishuClient:
    """飞书 API 客户端"""

    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET")
        if not self.app_id or not self.app_secret:
            raise ValueError("请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET 环境变量")
        self._token = None
        self._token_expire = 0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expire - 60:
            return self._token
        url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
        resp = requests.post(url, json={"app_id": self.app_id, "app_secret": self.app_secret})
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"获取飞书 Token 失败: {data}")
        self._token = data["tenant_access_token"]
        self._token_expire = time.time() + data.get("expire", 7200)
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    def create_document(self, title: str) -> str:
        url = f"{BASE_URL}/docx/v1/documents"
        resp = requests.post(url, headers=self._headers(), json={"title": title})
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"创建飞书文档失败: {data}")
        doc_id = data["data"]["document"]["document_id"]
        print(f"  [飞书] 创建文档成功: {title} (id={doc_id})")
        return doc_id

    def _make_text_block(self, text: str, block_type: int) -> dict:
        """构建 block body，block_type 是整数"""
        text = clean_html(text)
        text_run = {"content": text}

        if block_type == 20:
            return {"block_type": 20, "divider": {}}

        body = {"block_type": block_type}

        if block_type in (3, 4, 5):
            level_map = {3: 1, 4: 2, 5: 3}
            body["heading" + str(level_map[block_type])] = {"elements": [{"text_run": text_run}]}
        elif block_type == 15:
            body["quote"] = {"elements": [{"text_run": text_run}]}
        elif block_type in (9, 11):
            key = "bullet" if block_type == 9 else "ordered"
            body[key] = {"elements": [{"text_run": text_run}]}
        else:  # block_type == 2, plain text
            body["text"] = {"elements": [{"text_run": text_run}]}

        return body

    def add_text_block(self, doc_id: str, parent_id: str, text: str,
                       block_type: int = 2, heading_level: int = None) -> str:
        url = f"{BASE_URL}/docx/v1/documents/{doc_id}/blocks/{parent_id}/children"
        body = self._make_text_block(text, block_type)
        payload = {"children": [body]}

        resp = requests.post(url, headers=self._headers(), json=payload)
        data = resp.json()
        if data.get("code") != 0:
            print(f"  [飞书] 添加块失败: {data}, text[:50]={text[:50]}")
            # Print the request for debugging
            import json as j
            print(f"  [DEBUG] payload: {j.dumps(payload, ensure_ascii=False)[:300]}")
            return None
        children = data.get("data", {}).get("children", [])
        if children:
            return children[0].get("block_id")
        return None

    def write_podcast_note(self, title: str, summary_text: str,
                           full_transcript: str = None,
                           podcast_name: str = "",
                           episode_link: str = "") -> str:
        doc_title = f"🎧 {podcast_name} - {title}"
        doc_id = self.create_document(doc_title)
        root_id = doc_id

        self.add_text_block(doc_id, root_id, f"来源播客: {podcast_name}", block_type=2)
        if episode_link:
            self.add_text_block(doc_id, root_id, f"原文链接: {episode_link}", block_type=2)
        self.add_text_block(doc_id, root_id, "", block_type=20)

        for line in summary_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("## "):
                self.add_text_block(doc_id, root_id, line[3:].strip(), block_type=4)
            elif line.startswith("# "):
                self.add_text_block(doc_id, root_id, line[2:].strip(), block_type=3)
            elif line.startswith("> "):
                self.add_text_block(doc_id, root_id, line[2:].strip(), block_type=15)
            elif line.startswith("- "):
                self.add_text_block(doc_id, root_id, line[2:].strip(), block_type=9)
            elif line.startswith("* "):
                self.add_text_block(doc_id, root_id, line[2:].strip(), block_type=9)
            elif line[0].isdigit() and ". " in line[:4]:
                self.add_text_block(doc_id, root_id, line.split(". ", 1)[1], block_type=11)
            else:
                self.add_text_block(doc_id, root_id, line, block_type=2)

        if full_transcript:
            self.add_text_block(doc_id, root_id, "", block_type=20)
            self.add_text_block(doc_id, root_id, "完整文字稿", block_type=4)
            max_len = 2000
            for i in range(0, len(full_transcript), max_len):
                chunk = full_transcript[i:i+max_len]
                if chunk.strip():
                    self.add_text_block(doc_id, root_id, chunk, block_type=2)

        doc_link = f"https://bytedance.feishu.cn/docx/{doc_id}"
        print(f"  [飞书] 文档链接: {doc_link}")
        return doc_link
