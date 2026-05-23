# SHOJIKI 故障报告 - 工厂使用指南

> 中国工厂员工向 SHOJIKI 日本端报告故障/改进需求的指南。

## 概要

每个产品有专用的报告仓库:

| 产品 | 仓库 |
|---|---|
| SH-J001 | https://github.com/eda0825-spec/shojiki-defects-j001 |
| SH-J002 | https://github.com/eda0825-spec/shojiki-defects-j002 |

工厂员工只能访问自己负责的产品仓库。

## 第一次准备 (只做一次)

### 1. 注册 GitHub 账号

1. 打开 <https://github.com/signup>
2. 用工厂邮箱注册 (建议用工作邮箱便于通知)
3. 填写用户名 (例: `shojiki-factory-zhang`)
4. 完成邮箱验证

### 2. 告知日本管理员你的 GitHub 用户名

通过现有沟通渠道 (邮件/微信) 告诉日本端你的 GitHub 用户名。
日本端会将你加入对应产品的协作者。

### 3. 接受邀请

收到邀请邮件后点击 "Accept invitation"，或访问:
- J001 工厂: <https://github.com/eda0825-spec/shojiki-defects-j001/invitations>
- J002 工厂: <https://github.com/eda0825-spec/shojiki-defects-j002/invitations>

## 日常报告方法

### 方法 A: 表单页面 (推荐)

<https://eda0825-spec.github.io/shojiki-rakuten-stats/defects.html>

1. 选择产品 (SH-J001 / SH-J002)
2. 填写表单
   - 来源 (工厂检查 / 客户评论 等)
   - 严重度 (高 / 中 / 低)
   - 部位 (可多选)
   - 症状 (用日语和中文都写最好；如果只能写中文，用中文写)
   - 视频链接 (如果有大于 10MB 的视频)
3. 点击 "提交到 GitHub"
4. GitHub 页面打开 (新标签页)，自动填好内容
5. 如果还没登录会要求登录
6. 拖拽照片到正文 (10MB 以内)
7. 点击 "Submit new issue"

### 方法 B: 直接在 GitHub 上报告

1. 打开仓库的 Issues 页面 (上面的链接)
2. 点击右上 "New issue" 按钮
3. 选择 "不具合・改善要望 / 故障·改进需求"
4. 按表单填写
5. 拖拽图片
6. 提交

## 视频的处理

GitHub Issue 中视频附件最大 **10MB**。超过的话:

1. 上传到 **WeTransfer** (<https://wetransfer.com/>) 或类似服务
   - 免费可上传 2GB
   - 国内能访问
   - 生成的链接 7 天有效
2. 复制链接
3. 粘贴到表单的 "视频链接" 字段
4. 日本端会下载查看

可替代服务:
- **Mega** (<https://mega.nz/>) - 永久存储
- **微云** (Tencent Cloud) - 国内速度好
- **百度网盘** - 国内常用 (日本端需要安装)

## 报告时的好习惯

✅ **症状要具体**
- 坏: "电池有问题"
- 好: "充电 30 分钟后只显示 50%, 实际使用 5 分钟就关机。批次 2026-W18, 大约 10 台中有 2 台"

✅ **照片至少 1 张**
- 故障位置特写
- 整体外观
- 序列号/批次号的标签

✅ **视频展示症状的发生过程**
- 30 秒到 1 分钟最佳
- 包含声音 (异响等情况)
- 横屏拍摄

✅ **批次号一定填**
- 没有批次号就无法定位是哪个生产周期的问题

## 严重度的判断

| 等级 | 例子 |
|---|---|
| **高** | 起火、漏电、零件脱落致伤、闻到糊味/烟 |
| **中** | 不能充电、电机不转、明显异响、按钮失灵 |
| **低** | 偶尔卡顿、外观划痕、配件少件 |

不确定就选 "中"。

## 提交后的流程

1. 提交后 Issue 编号会生成 (例: `#15`)
2. 日本端会在 Issue 中添加评论 (邮件会通知你)
3. 看到评论后用日语或中文回复均可
4. 处理完成后日本端会关闭 Issue 并写明处理结果

## 通知设置

为不漏掉日本端的回复:

1. GitHub 右上角 → Settings → Notifications
2. "Email" 勾选 "Comments on Issues and Pull Requests"
3. 或者下载 **GitHub Mobile** 手机应用，推送通知

## 安装 GitHub Mobile (建议)

- iOS: App Store 搜 "GitHub"
- Android: 各应用市场搜 "GitHub" (国内可能需要 APK 直装)
  - 官方 APK: <https://github.com/mobile>

用手机 App 后:
- 现场拍照 → 直接附件上传
- 推送通知即时收到日本端回复
- 离线时也能阅读

## 看其他人提的故障

<https://eda0825-spec.github.io/shojiki-rakuten-stats/defects-dashboard.html>

可以看到所有产品的故障一览，按严重度/部位/状态筛选。

## 关于评论

日本顾客在 楽天/Amazon 上对您工厂生产的产品写的评论，也有专门的看板:
<https://eda0825-spec.github.io/shojiki-rakuten-stats/>

AI 已经做了分类和中文翻译，可以直接阅读。

---

有任何问题随时通过 Issue 或微信问日本端。
