"""测试用真实极小图片。

阶段03 起上传要做真实解码校验，假 PNG 字节（只有魔数）不再能被接受，
因此这里用 Pillow 生成体积很小的真实文件，并保留一个独立的损坏样本。
"""

from __future__ import annotations

import io

from PIL import Image


def make_image_bytes(image_format: str = "PNG", size: tuple[int, int] = (4, 3)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (196, 74, 52)).save(buffer, format=image_format)
    return buffer.getvalue()


REAL_PNG_BYTES = make_image_bytes("PNG")
REAL_JPEG_BYTES = make_image_bytes("JPEG")
REAL_WEBP_BYTES = make_image_bytes("WEBP")
# 只有 PNG 魔数和一段垃圾数据：能通过扩展名检查，但无法解码
CORRUPT_IMAGE_BYTES = b"\x89PNG\r\n\x1a\n" + b"not-a-real-png-body"
