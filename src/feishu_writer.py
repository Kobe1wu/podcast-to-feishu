"""
飞书文档写入模块
创建文档后自动授权，让文档直接出现在你的飞书里
"""
import os
import requests
import time


BASE_URL = "https://open.feishu.cn/open-apis"


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
        resp = requests.post(url, json={
            "app_id": self.app_id, "app_secret": self.app_secret,
        })
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"获取飞书 Token 失败: {data}")
        self._token = data["tenant_access_token"]
        self._token_expire = time.time() + data.get("expire", 7200)
        return self._token

    def _headers(self) -> dict:
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
        print(f"  [飞书] 创建文档成功: {title}")
        return doc_id

    def share_to_all_members(self, doc_id: str):
        """
        将文档开放给整个企业/组织的所有成员，这样文档会自动出现在你的飞书里
        无需再点链接才能看到
        """
        url = f"{BASE_URL}/drive/v1/permissions/{doc_id}/members?type=docx"
        resp = requests.post(url, headers=self._headers(), json={
            "member_type": "open",
            "perm": "full_access",
        })
        data = resp.json()
        if data.get("code") != 0:
            print(f"  [飞书] 设置权限失败（不影响使用）: {data.get('msg', str(data)[:100])}")
        else:
            print(f"  [飞书] 已开放文档访问权限，文档已出现在你的飞书里")

    def _build_text_body(self, text: str, block_type: int = 2) -> dict:
        body = {"block_type": block_type}
        elem = {"elements": [{"text_run": {"content": text, "text_element_style": {}}}]}
        type_map = {2: "text", 3: "heading1", 4: "heading2", 5: "heading3",
                    9: "bullet", 11: "ordered", 15: "quote", 20: "divider"}
        key = type_map.get(block_type, "text")
        body[key] = elem if key != "divider" else {}
        return body

    def add_blocks_batch(self, doc_id: str, parent_id: str, blocks: list) -> list:
        if not blocks:
            return []
        url = f"{BASE_URL}/docx/v1/documents/{doc_id}/blocks/{parent_id}/children"
        all_ids = []

        for i in range(0, len(blocks), 50):
            batch = blocks[i:i+50]
            children = [self._build_text_body(text, bt) for text, bt in batch]
            resp = requests.post(url, headers=self._headers(), json={"children": children})
            data = resp.json()
            if data.get("code") != 0:
                print(f"  [飞书] 批量添加块失败(#{i}): {data.get('msg', str(data)[:200])}")
                continue
            ids = [c.get("block_id") for c in data.get("data", {}).get("children", [])]
            all_ids.extend(ids)
        return all_ids

    def write_podcast_note(self, title: str, summary_text: str, full_transcript: str = None,
                           podcast_name: str = "", episode_link: str = "") -> str:
        doc_title = f"{podcast_name} - {title}"
        doc_id = self.create_document(doc_title)
        root_id = doc_id

        all_blocks = []

        # 元信息
        all_blocks.append((f"来源播客: {podcast_name}", 2))
        if episode_link:
            all_blocks.append((f"原文链接: {episode_link}", 2))
        all_blocks.append(("", 20))

        # 总结内容
        for line in summary_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("## ") or line.startswith("### "):
                all_blocks.append((line.split(" ", 1)[1].strip(), 4))
            elif line.startswith("# "):
                all_blocks.append((line.split(" ", 1)[1].strip(), 3))
            elif line.startswith("> "):
                all_blocks.append((line[2:].strip(), 15))
            elif line.startswith("- ") or line.startswith("* "):
                all_blocks.append((line[2:].strip(), 9))
            elif line[0].isdigit() and ". " in line[:4]:
                all_blocks.append((line.split(". ", 1)[1], 11))
            else:
                all_blocks.append((line, 2))

        print(f"  [飞书] 总结块数: {len(all_blocks)}")

        # 完整文字稿
        if full_transcript:
            all_blocks.append(("完整文字稿", 4))
            all_blocks.append(("", 20))
            max_len = 4000
            for i in range(0, len(full_transcript), max_len):
                chunk = full_transcript[i:i+max_len]
                if chunk.strip():
                    all_blocks.append((chunk, 2))
            print(f"  [飞书] 总块数: {len(all_blocks)}, 文字稿: {len(full_transcript)} 字")

        # 批量写入
        self.add_blocks_batch(doc_id, root_id, all_blocks)

        # 关键：开放权限，让文档自动出现在你的飞书里
        self.share_to_all_members(doc_id)

        doc_link = f"https://bytedance.feishu.cn/docx/{doc_id}"
        print(f"  [飞书] 文档链接: {doc_link}")
        return doc_link
