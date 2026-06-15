"""
飞书文档写入模块 - 字节版飞书兼容
"""
import os, re, requests, time, json

BASE_URL = "https://open.feishu.cn/open-apis"

# 字节飞书已验证可用的 block_type
BLOCK_TEXT = "2"      # 纯文本 ✅
BLOCK_H1 = "3"        # 一级标题
BLOCK_H2 = "4"        # 二级标题


def clean_html(text: str) -> str:
    if not text: return ""
    text = re.sub(r'<[^>]+>', '', text)
    import html; text = html.unescape(text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


class FeishuClient:
    def __init__(self, app_id=None, app_secret=None):
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET")
        if not self.app_id or not self.app_secret:
            raise ValueError("请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        self._token = None; self._token_expire = 0

    def _get_token(self):
        if self._token and time.time() < self._token_expire - 60: return self._token
        r = requests.post(f"{BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id":self.app_id,"app_secret":self.app_secret})
        d = r.json()
        if d.get("code") != 0: raise Exception(f"Token失败:{d}")
        self._token = d["tenant_access_token"]
        self._token_expire = time.time() + d.get("expire",7200)
        return self._token

    def _h(self): return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    def create_document(self, title: str):
        r = requests.post(f"{BASE_URL}/docx/v1/documents", headers=self._h(), json={"title": title})
        d = r.json()
        if d.get("code") != 0: raise Exception(f"创建文档失败:{d}")
        doc_id = d["data"]["document"]["document_id"]
        print(f"  [飞书] 文档创建成功: (id={doc_id})")
        return doc_id, doc_id

    def add_block(self, doc_id, parent_id, text, block_type=BLOCK_TEXT):
        text = clean_html(text)
        body = {"block_type": block_type}
        if block_type == BLOCK_H1:
            body["heading1"] = {"elements": [{"text_run": {"content": text}}]}
        elif block_type == BLOCK_H2:
            body["heading2"] = {"elements": [{"text_run": {"content": text}}]}
        else:
            body["text"] = {"elements": [{"text_run": {"content": text}}]}

        url = f"{BASE_URL}/docx/v1/documents/{doc_id}/blocks/{parent_id}/children"
        r = requests.post(url, headers=self._h(), json={"children": [body]})
        d = r.json()
        if d.get("code") != 0:
            print(f"  [飞书] 写入失败 [{block_type}]: {json.dumps(d, ensure_ascii=False)[:200]}")
            return None
        return d.get("data",{}).get("children",[{}])[0].get("block_id")

    def write_podcast_note(self, title, summary_text, full_transcript=None,
                           podcast_name="", episode_link=""):
        doc_title = f"\U0001F3A7 {podcast_name} - {title}"
        doc_id, root_id = self.create_document(doc_title)

        # 头部信息
        self.add_block(doc_id, root_id, f"来源播客: {podcast_name}")
        if episode_link:
            self.add_block(doc_id, root_id, f"原文链接: {episode_link}")
        self.add_block(doc_id, root_id, "━━━━━━━━━━━━━━━━━━")

        # 总结内容 - 全部用纯文本，Markdown 格式的标题转成带前缀的文本
        for line in summary_text.split("\n"):
            line = line.strip()
            if not line: continue
            if line.startswith("## "):
                self.add_block(doc_id, root_id, line[3:].strip(), BLOCK_H2)
            elif line.startswith("# "):
                self.add_block(doc_id, root_id, line[2:].strip(), BLOCK_H1)
            elif line.startswith("- ") or line.startswith("* "):
                self.add_block(doc_id, root_id, "• " + line[2:].strip())
            elif line[0].isdigit() and ". " in line[:4]:
                self.add_block(doc_id, root_id, line)
            elif line.startswith("> "):
                self.add_block(doc_id, root_id, "「" + line[2:].strip() + "」")
            else:
                self.add_block(doc_id, root_id, line)

        # 完整文字稿
        if full_transcript:
            self.add_block(doc_id, root_id, "━━━━━━━━━━━━━━━━━━")
            self.add_block(doc_id, root_id, "完整文字稿", BLOCK_H2)
            for i in range(0, len(full_transcript), 2000):
                chunk = full_transcript[i:i+2000]
                if chunk.strip(): self.add_block(doc_id, root_id, chunk)

        link = f"https://bytedance.feishu.cn/docx/{doc_id}"
        print(f"  [飞书] 文档链接: {link}")
        return link
