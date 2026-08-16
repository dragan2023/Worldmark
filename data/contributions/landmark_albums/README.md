# 地标相册共创目录

每个已发布地标的相册由本目录中的本地图片和 `manifest.json` 共同维护。网页只读取本地图片链接，不嵌入第三方图片地址。

## 1. 图片存放

将图片放到 `images/<门类>/<英文或拼音地标目录>/`。支持 `jpg`、`jpeg`、`png`、`webp`、`avif`；建议横图宽度至少 1600px，单张控制在 2MB 以内。

仅提交原创、公共领域或具有明确可再分发许可的图片。不得提交作品剧照、游戏截图、海报或授权状态不明的网络图片。

## 2. 登记相册

在 `manifest.json` 的 `albums` 对象内增加一个条目，键名为 `<ip_type>:<地标名称>`，图片路径相对于 `images/`：

```json
{
  "albums": {
    "literature:百草园与三味书屋": [
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

`alt` 必填；`caption`、`credit`、`license`、`source_url` 可选。带 `source_url` 时必须填写 HTTP/HTTPS 地址。保存后，相册会自动出现在对应地标详情页。
