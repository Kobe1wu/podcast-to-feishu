"""
飞书文档写入模块
创建文档后自动设置共享权限，文档直接出现在你的飞书里
"""
import json
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
        """设置文档为组织内可编辑，自动出现在你的飞书里且你拥有编辑权限"""
        url = f"{BASE_URL}/drive/v1/permissions/{doc_id}/public?type=docx"
        resp = requests.patch(url, headers=self._headers(), json={
            "link_share_entity": "tenant_editable",
            "external_access_entity": "closed",
        })
        data = resp.json()
        if data.get("code") != 0:
            print(f"  [飞书][警告] 设置共享权限失败: code={data.get('code')} msg={data.get('msg')}")
            return False
        print(f"  [飞书] 已设置组织内可编辑，文档将出现在你的飞书里并可编辑")
        return True

    def _verify_collaborator(self, doc_id, open_id):
        """查询协作者列表，确认 open_id 确实被加进去了（不靠返回值盲信）。

        注意：飞书权限变更可能是异步生效的，所以这里会延时重试几次，
        并把原始响应片段打出来，便于区分『真的没加上』和『查太快/分页导致误报』。
        """
        url = f"{BASE_URL}/drive/v1/permissions/{doc_id}/members?type=docx&page_size=100"
        last_summary = "未知"
        for attempt in range(1, 4):
            if attempt > 1:
                time.sleep(3)
            try:
                resp = requests.get(url, headers=self._headers())
                data = resp.json()
                if data.get("code") != 0:
                    last_summary = f"查询失败 code={data.get('code')} msg={data.get('msg')}"
                    print(f"  [飞书] 协作者校验(第{attempt}次): {last_summary}")
                    continue
                payload = data.get("data") or {}
                # 注意：飞书该接口返回的是 items（不是 members），此前读错字段导致一直误报"0 个协作者"
                items = payload.get("items")
                if items is None:
                    items = payload.get("members", [])
                hit = any(m.get("member_id") == open_id for m in items)
                last_summary = f"共 {len(items)} 个协作者，{'命中 ✓' if hit else '未命中'}"
                print(f"  [飞书] 协作者校验(第{attempt}次): {last_summary}")
                if attempt == 1:
                    # 首次打印原始响应片段，便于定位是接口语义问题还是真的没加上
                    print(f"  [飞书] 原始响应: {str(data)[:400]}")
                if hit:
                    return True
            except Exception as e:
                last_summary = f"异常 {type(e).__name__}: {e}"
                print(f"  [飞书] 协作者校验(第{attempt}次): {last_summary}")

        print(f"  [飞书] ★3 次查询均未见到该 open_id★（{last_summary}）")
        return False

    def add_collaborator(self, doc_id, open_id, perm="full_access"):
        """把你本人加为文档协作者（按 open_id），文档进入“与我共享”并推送通知，
        这样手机端飞书无需复制链接即可直接看到/打开。

        失败会重试一次，成功后主动查询协作者列表做校验——不再静默吞掉错误。
        返回 True/False 便于调用方和自检脚本判断。"""
        open_id = (open_id or "").strip()
        if not open_id:
            print("  [飞书][严重] open_id 为空，无法添加协作者 —— "
                  "文档不会出现在你的飞书『与我共享』，手机端必须先手动打开链接一次才能看到。")
            return False

        url = f"{BASE_URL}/drive/v1/permissions/{doc_id}/members?type=docx&need_notification=true"
        last_err = None
        for attempt in range(1, 3):
            try:
                resp = requests.post(url, headers=self._headers(), json={
                    "member_type": "openid",
                    "member_id": open_id,
                    "perm": perm,
                })
                data = resp.json()
                if data.get("code") == 0:
                    print(f"  [飞书] 已把你加为协作者（open_id {open_id[:8]}…），文档将出现在你的飞书里")
                    return self._verify_collaborator(doc_id, open_id)
                last_err = f"code={data.get('code')} msg={data.get('msg')}"
            except Exception as e:
                last_err = f"异常 {type(e).__name__}: {e}"
            print(f"  [飞书] 添加协作者第 {attempt} 次失败: {last_err}")
            if attempt < 2:
                time.sleep(2)

        print(f"  [飞书][严重] 添加协作者最终失败: {last_err} —— "
              f"手机端飞书看不到该文档，需手动打开链接一次才会出现")
        return False

    def send_message(self, open_id, title, doc_link, podcast_name=""):
        """用机器人给你发一条消息（含文档链接）。

        为什么需要它：文档设了『组织内可编辑』，你的权限来自组织而非『某人分享给我』，
        飞书未必会把它列进『与我共享』——这正是"必须先在浏览器打开一次才看得到"的原因。
        主动发消息可以保证手机端一定收到通知、点开即是文档，是最可靠的兜底。
        若应用未开通 im:message 权限会失败，但不影响文档本身。"""
        open_id = (open_id or "").strip()
        if not open_id:
            print("  [飞书] open_id 为空，跳过消息推送")
            return False

        url = f"{BASE_URL}/im/v1/messages?receive_id_type=open_id"
        lines = [f"新播客笔记：{title}"]
        if podcast_name:
            lines.append(f"来自：{podcast_name}")
        lines.append(doc_link)
        try:
            resp = requests.post(url, headers=self._headers(), json={
                "receive_id": open_id,
                "msg_type": "text",
                "content": json.dumps({"text": "\n".join(lines)}),
            })
            data = resp.json()
            if data.get("code") == 0:
                print("  [飞书] 已通过机器人消息推送文档链接（手机端会收到通知，点开即达）")
                return True
            print(f"  [飞书] 消息推送失败: code={data.get('code')} msg={data.get('msg')}")
            print("        → 需在飞书开放平台给应用开通 im:message 权限并发布新版本；不影响文档本身。")
            return False
        except Exception as e:
            print(f"  [飞书] 消息推送异常: {type(e).__name__}: {e}")
            return False

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

        # 把你本人加为协作者，文档出现在你的飞书“与我共享”并推送通知（手机端可直接打开）
        user_open_id = (os.environ.get("FEISHU_USER_OPEN_ID") or "").strip()
        if not user_open_id:
            print("  [飞书][严重] FEISHU_USER_OPEN_ID 未配置或为空 —— 文档不会进入你的飞书『与我共享』，"
                  "手机端必须先手动打开链接一次才能看到。"
                  "请在仓库 Settings > Secrets and variables > Actions 中配置该值（形如 ou_xxxx）。")
        else:
            self.add_collaborator(doc_id, user_open_id)

        link = f"https://bytedance.feishu.cn/docx/{doc_id}"
        # 兜底：主动发消息，确保手机端一定收到通知（不依赖『与我共享』列表的展示行为）
        if user_open_id:
            self.send_message(user_open_id, title, link, podcast_name)
        print(f"  [飞书] 文档链接: {link}")
        return link
