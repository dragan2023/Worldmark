# 地标相册共创目录

每个已发布地标的相册由本目录中的本地图片和 `manifest.json` 共同维护。网页只读取本地图片链接，不嵌入第三方图片地址。

## 1. 图片存放

将图片放到 `images/<门类>/<英文或拼音地标目录>/`。支持 `jpg`、`jpeg`、`png`、`webp`、`avif`；建议横图宽度至少 1600px，单张控制在 2MB 以内。

通过网页编辑器上传时，服务端会用 Pillow 真实解码校验：文件内容必须与声明的格式一致，单张不超过 8 MiB，像素不超过 4000 万，损坏或截断的文件会被拒绝。

仅提交原创、公共领域或具有明确可再分发许可的图片。不得提交作品剧照、游戏截图、海报或授权状态不明的网络图片。

## 2. 登记相册

在 `manifest.json` 的 `albums` 对象内增加一个条目，键名为 **`landmark:<地标 ID>`**（数据库主键，改名不影响归属），图片路径相对于 `images/`：

```json
{
  "albums": {
    "landmark:12": [
      {
        "file": "literature/luxun-former-residence/courtyard-01.jpg",
        "alt": "百草园与三味书屋的院落外观",
        "caption": "院落外景",
        "credit": "图片作者或机构名称",
        "license": "CC BY 4.0",
        "source_url": "https://example.org/photo-source"
      }
    ]
  }
}
```

`alt` 必填；`caption`、`credit`、`license`、`source_url` 可选。带 `source_url` 时必须填写 HTTP/HTTPS 地址。

旧键 `<ip_type>:<地标名称>` 仅在迁移完成前作为兼容读取路径保留：地标改名后会读不到旧键，同类型同名地标也会互相串图，因此新条目一律使用 `landmark:<id>`。

历史键迁移使用只读演练后再决定是否执行（正式数据修改需单独授权）：

```powershell
# 默认 dry-run：只输出「可迁移 / 多义 / 未匹配」清单，不改任何文件
.\.venv\Scripts\python.exe scripts\migrate_album_keys.py --json album-key-report.json
```

## 3. 访问规则

- 正式图片只服务「所属地标当前公开」或「请求者是该地标贡献者/管理员」的请求；待审、已撤回、已软删地标的图片即使知道旧 URL 也读不到。
- 编辑器的暂存目录 `uploads/landmark_albums/<地标 ID>/` 不再是匿名静态目录：必须登录且是该地标的贡献者或管理员，`_meta.json` 等非图片文件一律不可读。
- 未被任何 `albums` 条目引用的图片不会对外发布，可安全用于本地草稿或 `_trash` 回收站。
