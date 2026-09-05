================================================================
飞书权限自检 —— 验证『文档能否出现在你的飞书里』
================================================================

[1/5] 检查环境变量
  OK    FEISHU_APP_ID = cli_aa…(长度20)
  OK    FEISHU_APP_SECRET = f0c7cJ…(长度32)
  OK    FEISHU_USER_OPEN_ID = ou_36a…(长度35)

[2/5] 获取 tenant_access_token
  OK    token 获取成功

[3/5] 创建测试文档
  [飞书] 文档创建成功: 自检-可删除
  OK    document_id = NPoFdI7MXokVJvxsVvmckE6anOh
       链接 https://bytedance.feishu.cn/docx/NPoFdI7MXokVJvxsVvmckE6anOh

[4/5] 设置共享权限 + 把你加为协作者
  [飞书] 已设置组织内可编辑，文档将出现在你的飞书里并可编辑
  [飞书] 已把你加为协作者（open_id ou_36afd…），文档将出现在你的飞书里
  [飞书] 协作者校验(第1次): 共 0 个协作者，未命中
  [飞书] 原始响应: {'code': 0, 'data': {'items': [{'member_id': 'cli_aaa8550a26389cd2', 'member_type': 'appid', 'perm': 'full_access', 'perm_type': 'container'}, {'member_id': 'ou_36afdeb8f9f6a6a20782af93caa5ef55', 'member_type': 'openid', 'perm': 'full_access', 'perm_type': 'container'}]}, 'msg': 'Success'}
  [飞书] 协作者校验(第2次): 共 0 个协作者，未命中
  [飞书] 协作者校验(第3次): 共 0 个协作者，未命中
  [飞书] ★3 次查询均未见到该 open_id★（共 0 个协作者，未命中）

================================================================
自检结论
================================================================
✗ 协作者未成功添加 —— 这正是手机端看不到文档的原因。
  → 若报错 code=99991672/99991663：应用缺少权限或权限未生效，
     去飞书开放平台为该应用勾选 drive:permission（及 docs 相关）权限，
     然后【创建并发布新版本】，权限才会真正生效。
  → 若报错含 invalid member / user not exist：FEISHU_USER_OPEN_ID 值不对，重新获取。

明细: 共享权限=OK  协作者=失败
================================================================

[5/5] 清理测试文档
  OK    测试文档已删除
