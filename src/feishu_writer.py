"""
飞书文档写入模块
创建文档后自动设置共享权限，文档直接出现在你的飞书里
"""
import os
import requests
import time


BASE_URL = "https://open.feishu.cn/open-apis"

# 飞书 block_type 正确值
# 2=Text, 3=Heading1, 4=Heading2, 5=Heading3
# 12=Bullet, 13=Ordered, 15=Quote, 22=Divider
BLOCK_TEXT = 2
BLOCK_H1 = 3
BLOCK_H2 = 4
BLOCK_H3 = 5
BLOCK_BULLET = 12
BLOCK_ORDERED = 13
BLOCK_QUOTE = 15
BLOCK_DIVIDER = 22


class FeishuClient:

    def __init__(self, app_id=None, app_secret=None):
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET")
        if not self.app_id or not self.app_secret:
            raise ValueError("请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        self._token = None
        self._token_expire = 0

    def _get_token(self):
        if self._token and time.time() < self._token_expire - 60:
            return self._token
        resp = requests.post(f"{BASE_URL}/auth/v3/tenant_access_token/internal", json={
            "app_id": self.app_id, "app_secret": self.app_secret,
        })
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"获取 Token 失败: {data}")
        self._token = data["tenant_access_token"]
        self._token_expire = time.time() + data.get("expire", 7200)
        return self._token

    def _headers(self):
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    def create_document(self, title):
        resp = requests.post(f"{BASE_URL}/docx/v1/documents", headers=self._headers(), json={"title": title})
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"创建文档失败: {data}")
        doc_id = data["data"]["document"]["document_id"]
        print(f"  [飞书] 文档创建成功: {title}")
        return doc_id

    def set_public_sharing(self, doc_id):
        """设置文档为组织内可查看，自动出现在你的飞书文档列表"""
        url = f"{BASE_URL}/drive/v1/permissions/{doc_id}/public?type=docx"
        resp = requests.patch(url, headers=self._headers(), json={
            "link_share_entity": "tenant_readable",
            "external_access_entity": "open",
        })
        data = resp.json()
        if data.get("code") != 0:
            print(f"  [飞书] 设置共享权限失败（不影响使用）: {data.get('msg', '')}")
        else:
            print(f"  [飞书] 已设置组织内共享，文档将出现在你的飞书里")

    def _build_block(self, text, block_type):
        """构建飞书文档块"""
        if block_type == BLOCK_DIVIDER:
            return {"block_type": BLOCK_DIVIDER, "divider": {}}

        type_names = {
            BLOCK_TEXT: "text", BLOCK_H1: "heading1", BLOCK_H2: "heading2",
            BLOCK_H3: "heading3", BLOCK_BULLET: "bullet", BLOCK_ORDERED: "ordered",
            BLOCK_QUOTE: "quote",
        }
        key = type_names.get(block_type, "text")
        return {
            "block_type": block_type,
            key: {"elements": [{"text_run": {"content": text, "text_element_style": {}}}]}
        }

    def add_blocks(self, doc_id, parent_id, blocks):
        """批量添加块，每批最多50个"""
        if not blocks:
            return
        url = f"{BASE_URL}/docx/v1/documents/{doc_id}/blocks/{parent_id}/children"
        for i in range(0, len(blocks), 50):
            batch = blocks[i:i+50]
            children = [self._build_block(text, bt) for text, bt in batch]
            resp = requests.post(url, headers=self._headers(), json={"children": children})
            data = resp.json()
            if data.get("code") != 0:
                print(f"  [飞书] 写入块失败(#{i}): {data.get('msg', str(data)[:150])}")

    def write_podcast_note(self, title, summary_text, full_transcript=None,
                           podcast_name="", episode_link=""):
        doc_id = self.create_document(f"{podcast_name} - {title}")

        blocks = []
        blocks.append((f"来源播客: {podcast_name}", BLOCK_TEXT))
        if episode_link:
            blocks.append((f"原文链接: {episode_link}", BLOCK_TEXT))
        blocks.append(("", BLOCK_DIVIDER))

        for line in summary_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("## ") or line.startswith("### "):
                blocks.append((line.split(" ", 1)[1].strip(), BLOCK_H2))
            elif line.startswith("# "):
                blocks.append((line.split(" ", 1)[1].strip(), BLOCK_H1))
            elif line.startswith("> "):
                blocks.append((line[2:].strip(), BLOCK_QUOTE))
            elif line.startswith("- ") or line.startswith("* "):
                blocks.append((line[2:].strip(), BLOCK_BULLET))
            elif len(line) > 2 and line[0].isdigit() and ". " in line[:4]:
                blocks.append((line.split(". ", 1)[1], BLOCK_ORDERED))
            else:
                blocks.append((line, BLOCK_TEXT))

        print(f"  [飞书] 总结块数: {len(blocks)}")

        if full_transcript:
            blocks.append(("完整文字稿", BLOCK_H2))
            blocks.append(("", BLOCK_DIVIDER))
            for i in range(0, len(full_transcript), 4000):
                chunk = full_transcript[i:i+4000]
                if chunk.strip():
                    blocks.append((chunk, BLOCK_TEXT))
            print(f"  [飞书] 总块数: {len(blocks)}, 文字稿: {len(full_transcript)} 字")

        self.add_blocks(doc_id, doc_id, blocks)
        self.set_public_sharing(doc_id)

        link = f"https://bytedance.feishu.cn/docx/{doc_id}"
        print(f"  [飞书] 文档链接: {link}")
        return link
