"""
飞书文档写入模块
将播客笔记写入飞书文档
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
        """获取 tenant_access_token"""
        if self._token and time.time() < self._token_expire - 60:
            return self._token

        url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
        resp = requests.post(url, json={
            "app_id": self.app_id,
            "app_secret": self.app_secret,
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
        """创建飞书文档，返回 document_id"""
        url = f"{BASE_URL}/docx/v1/documents"
        resp = requests.post(url, headers=self._headers(), json={"title": title})
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"创建飞书文档失败: {data}")
        doc_id = data["data"]["document"]["document_id"]
        print(f"  [飞书] 创建文档成功: {title} (id={doc_id})")
        return doc_id

    def _build_text_body(self, text: str, block_type: int = 2) -> dict:
        """构建单个 block 的请求体"""
        body = {"block_type": block_type}

        if block_type == 20:
            body["divider"] = {}
        elif block_type == 3:
            body["heading1"] = {
                "elements": [{"text_run": {"content": text, "text_element_style": {}}}]
            }
        elif block_type == 4:
            body["heading2"] = {
                "elements": [{"text_run": {"content": text, "text_element_style": {}}}]
            }
        elif block_type == 5:
            body["heading3"] = {
                "elements": [{"text_run": {"content": text, "text_element_style": {}}}]
            }
        elif block_type == 15:
            body["quote"] = {
                "elements": [{"text_run": {"content": text, "text_element_style": {}}}]
            }
        elif block_type == 9:
            body["bullet"] = {
                "elements": [{"text_run": {"content": text, "text_element_style": {}}}]
            }
        elif block_type == 11:
            body["ordered"] = {
                "elements": [{"text_run": {"content": text, "text_element_style": {}}}]
            }
        else:
            body["text"] = {
                "elements": [{"text_run": {"content": text, "text_element_style": {}}}]
            }
        return body

    def add_blocks_batch(self, doc_id: str, parent_id: str, blocks: list) -> list:
        """
        批量添加文本块到文档（每批最多50个）

        blocks: [(text, block_type), ...]
        返回所有新块的 block_id 列表
        """
        if not blocks:
            return []

        url = f"{BASE_URL}/docx/v1/documents/{doc_id}/blocks/{parent_id}/children"
        all_ids = []

        # 飞书限制每批最多50个块
        for i in range(0, len(blocks), 50):
            batch = blocks[i:i+50]
            children = []
            for text, block_type in batch:
                children.append(self._build_text_body(text, block_type))

            payload = {"children": children}
            resp = requests.post(url, headers=self._headers(), json=payload)
            data = resp.json()
            if data.get("code") != 0:
                print(f"  [飞书] 批量添加块失败(第{i}-{i+len(batch)}个): {data.get('msg', str(data)[:200])}")
                continue
            ids = [c.get("block_id") for c in data.get("data", {}).get("children", [])]
            all_ids.extend(ids)

        return all_ids

    def write_podcast_note(self, title: str, summary_text: str, full_transcript: str = None,
                           podcast_name: str = "", episode_link: str = "") -> str:
        """
        将播客笔记写入飞书文档

        返回文档链接
        """
        doc_title = f"🎧 {podcast_name} - {title}"
        doc_id = self.create_document(doc_title)
        root_id = doc_id

        # 准备所有要写入的块
        all_blocks = []

        # 元信息
        all_blocks.append((f"来源播客: {podcast_name}", 2))
        if episode_link:
            all_blocks.append((f"原文链接: {episode_link}", 2))
        all_blocks.append(("", 20))

        # 总结内容（Markdown → Feishu 块）
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

        # 如果有完整文字稿，添加在文档末尾
        if full_transcript:
            all_blocks.append(("完整文字稿", 4))
            all_blocks.append(("", 20))

            # 文字稿以 4000 字一段，减少块数量
            max_len = 4000
            for i in range(0, len(full_transcript), max_len):
                chunk = full_transcript[i:i+max_len]
                if chunk.strip():
                    all_blocks.append((chunk, 2))

            print(f"  [飞书] 含文字稿总块数: {len(all_blocks)}, 文字稿字数: {len(full_transcript)}")

        # 批量写入
        add_blocks_batch(doc_id, root_id, all_blocks)

        doc_link = f"https://bytedance.feishu.cn/docx/{doc_id}"
        print(f"  [飞书] 文档链接: {doc_link}")
        return doc_link
