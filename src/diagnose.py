"""
飞书权限自检脚本（诊断用，不处理播客）

用途：当"文档生成了但手机端飞书看不到"时，用它端到端验证可见性链路：
  环境变量 → tenant_access_token → 建文档 → 设共享 → 加你为协作者 → 校验 → 清理

用法：
  在 GitHub Actions 手动触发 workflow，mode 选 diagnose；
  或本地执行：python src/diagnose.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from feishu_writer import FeishuClient, BASE_URL

REQUIRED_ENVS = ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_USER_OPEN_ID"]


def mask(v: str) -> str:
    v = (v or "").strip()
    if not v:
        return "(空)"
    return f"{v[:6]}…(长度{len(v)})"


def check_env() -> bool:
    print("\n[1/5] 检查环境变量")
    ok = True
    for k in REQUIRED_ENVS:
        v = (os.environ.get(k) or "").strip()
        if v:
            print(f"  OK    {k} = {mask(v)}")
        else:
            print(f"  ✗     {k} 缺失或为空  <-- 这会导致文档不出现在你的飞书里")
            ok = False
    return ok


def get_token(client) -> bool:
    print("\n[2/5] 获取 tenant_access_token")
    try:
        client._get_token()
        print("  OK    token 获取成功")
        return True
    except Exception as e:
        print(f"  ✗     token 获取失败: {e}")
        return False


def try_delete(client, doc_id):
    print("\n[5/5] 清理测试文档")
    try:
        r = requests.delete(f"{BASE_URL}/drive/v1/files/{doc_id}?type=docx",
                            headers=client._headers(), timeout=30)
        d = r.json()
        if d.get("code") == 0:
            print("  OK    测试文档已删除")
        else:
            print(f"  !     删除失败（可手动删掉那个『自检-可删除』文档）: "
                  f"code={d.get('code')} msg={d.get('msg')}")
    except Exception as e:
        print(f"  !     删除异常（可手动删掉那个『自检-可删除』文档）: {e}")


def main():
    print("=" * 64)
    print("飞书权限自检 —— 验证『文档能否出现在你的飞书里』")
    print("=" * 64)

    env_ok = check_env()

    try:
        client = FeishuClient()
    except Exception as e:
        print(f"\n[致命] 无法初始化飞书客户端: {e}")
        print("请检查 FEISHU_APP_ID / FEISHU_APP_SECRET 是否正确配置在 Secrets 中。")
        return 1

    if not get_token(client):
        return 1

    print("\n[3/5] 创建测试文档")
    try:
        doc_id = client.create_document("自检-可删除")
    except Exception as e:
        print(f"  ✗     创建文档失败: {e}")
        return 1
    print(f"  OK    document_id = {doc_id}")
    print(f"       链接 https://bytedance.feishu.cn/docx/{doc_id}")

    print("\n[4/5] 设置共享权限 + 把你加为协作者")
    share_ok = client.set_public_sharing(doc_id)
    open_id = (os.environ.get("FEISHU_USER_OPEN_ID") or "").strip()
    collab_ok = client.add_collaborator(doc_id, open_id) if open_id else False

    # 兜底通道：机器人主动发消息（不依赖『与我共享』列表的展示行为）
    msg_ok = False
    if open_id:
        print("\n[4.5/5] 测试机器人消息推送（兜底通道）")
        msg_ok = client.send_message(open_id, "自检：文档可见性验证",
                                     f"https://bytedance.feishu.cn/docx/{doc_id}")

    # 汇总
    print("\n" + "=" * 64)
    print("自检结论")
    print("=" * 64)
    if not env_ok:
        print("✗ 环境变量缺失（尤其是 FEISHU_USER_OPEN_ID）。")
        print("  → 到仓库 Settings > Secrets and variables > Actions 补齐后重跑。")
        print("  → open_id 获取方式：飞书开放平台开通 contact:user.id:readonly，")
        print("     用手机号调 contact/v3/users/batch_get_id 换取（形如 ou_xxxx），并记得发布新版本。")
    elif collab_ok and msg_ok:
        print("✓ 协作者已加入 + 机器人消息可送达 —— 双通道都通，")
        print("  新文档既在『与我共享』里，手机端也会直接收到通知。")
    elif collab_ok and not msg_ok:
        print("△ 协作者添加成功（权限链路正常），但机器人消息推送不可用。")
        print("  → 文档应当出现在飞书『与我共享』中；若手机端仍看不到，")
        print("     说明该文档走的是『组织内可编辑』，权限来自组织而非个人分享，")
        print("     飞书可能不把它归入『与我共享』。")
        print("  → 建议开通 im:message 权限，用消息推送作为可靠兜底。")
    else:
        print("✗ 协作者未成功添加 —— 这正是手机端看不到文档的原因。")
        print("  → 若报错 code=99991672/99991663：应用缺少权限或权限未生效，")
        print("     去飞书开放平台为该应用勾选 drive:permission（及 docs 相关）权限，")
        print("     然后【创建并发布新版本】，权限才会真正生效。")
        print("  → 若报错含 invalid member / user not exist：FEISHU_USER_OPEN_ID 值不对，重新获取。")
    print(f"\n明细: 共享权限={'OK' if share_ok else '失败'}  "
          f"协作者={'OK' if collab_ok else '失败'}  "
          f"消息推送={'OK' if msg_ok else '失败'}")
    print("=" * 64)

    try_delete(client, doc_id)
    return 0 if (env_ok and collab_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
