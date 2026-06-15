"""
飞书文档写入模块
"""
import os
import re
import requests
import time

BASE_URL = "https://open.feishu.cn/open-apis"

# Feishu Docx block_type 必须用字符串
BLOCK_TEXT = "2"
BLOCK_H1 = "3"
BLOCK_H2 = "4"
BLOCK_H3 = "5"
BLOCK_BULLET = "9"
BLOCK_ORDERED = "10"
BLOCK_QUOTE = "12"
BLOCK_DIVIDER = "15"


def clean_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    import html
    text = html.unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


class FeishuClient:
    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET")
        if not self.app_id or not self.app_secret:
            raise ValueError("请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
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

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def create_document(self, title: str) -> str:
        url = f"{BASE_URL}/docx/v1/documents"
        resp = requests.post(url, headers=self._headers(), json={"title": title})
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"创建飞书文档失败: {data}")
        doc_id = data["data"]["document"]["document_id"]
        print(f"  [飞书] 创建文档成功: {title} (id={doc_id})")
        return doc_id

    def _make_block(self, text: str, block_type: str) -> dict:
        text = clean_html(text)
        body = {"block_type": block_type}

        if block_type == BLOCK_DIVIDER:
            body["divider"] = {}
        elif block_type in (BLOCK_H1, BLOCK_H2, BLOCK_H3):
            level_map = {BLOCK_H1: 1, BLOCK_H2: 2, BLOCK_H3: 3}
            body["heading" + str(level_map[block_type])] = {
                "elements": [{"text_run": {"content": text}}]
            }
        elif block_type == BLOCK_QUOTE:
            body["quote"] = {"elements": [{"text_run": {"content": text}}]}
        elif block_type in (BLOCK_BULLET, BLOCK_ORDERED):
            key = "bullet" if block_type == BLOCK_BULLET else "ordered"
            body[key] = {"elements": [{"text_run": {"content": text}}]}
        else:
            body["text"] = {"elements": [{"text_run": {"content": text}}]}

        return body

    def add_text_block(self, doc_id: str, parent_id: str, text: str,
                       block_type: str = BLOCK_TEXT) -> str:
        url = f"{BASE_URL}/docx/v1/documents/{doc_id}/blocks/{parent_id}/children"
        body = self._make_block(text, block_type)
        payload = {"children": [body]}

        resp = requests.post(url, headers=self._headers(), json=payload)
        data = resp.json()
        if data.get("code") != 0:
            import json
            print(f"  [飞书] 添加块失败: {json.dumps(data, ensure_ascii=False)[:200]}")
            return None
        children = data.get("data", {}).get("children", [])
        return children[0].get("block_id") if children else None

    def write_podcast_note(self, title: str, summary_text: str,
                           full_transcript: str = None,
                           podcast_name: str = "",
                           episode_link: str = "") -> str:
        doc_title = f"🎧 {podcast_name} - {title}"
        doc_id = self.create_document(doc_title)
        root_id = doc_id

        self.add_text_block(doc_id, root_id, f"来源播客: {podcast_name}")
        if episode_link:
            self.add_text_block(doc_id, root_id, f"原文链接: {episode_link}")
        self.add_text_block(doc_id, root_id, "", BLOCK_DIVIDER)

        for line in summary_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("## "):
                self.add_text_block(doc_id, root_id, line[3:].strip(), BLOCK_H2)
            elif line.startswith("# "):
                self.add_text_block(doc_id, root_id, line[2:].strip(), BLOCK_H1)
            elif line.startswith("> "):
                self.add_text_block(doc_id, root_id, line[2:].strip(), BLOCK_QUOTE)
            elif line.startswith("- ") or line.startswith("* "):
                self.add_text_block(doc_id, root_id, line[2:].strip(), BLOCK_BULLET)
            elif line[0].isdigit() and ". " in line[:4]:
                self.add_text_block(doc_id, root_id, line.split(". ", 1)[1], BLOCK_ORDERED)
            else:
                self.add_text_block(doc_id, root_id, line)

        if full_transcript:
            self.add_text_block(doc_id, root_id, "", BLOCK_DIVIDER)
            self.add_text_block(doc_id, root_id, "完整文字稿", BLOCK_H2)
            for i in range(0, len(full_transcript), 2000):
                chunk = full_transcript[i:i+2000]
                if chunk.strip():
                    self.add_text_block(doc_id, root_id, chunk)

        doc_link = f"https://bytedance.feishu.cn/docx/{doc_id}"
        print(f"  [飞书] 文档链接: {doc_link}")
        return doc_link
