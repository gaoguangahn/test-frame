import base64
import json
import re
from io import BytesIO

import cv2
import numpy as np
from PIL import Image


def resize_image_by_scale(image: np.ndarray, scale: float = 0.5) -> np.ndarray:
    """按固定比例缩放图片，保持输入仍为整屏截图。"""

    if scale <= 0:
        raise ValueError("scale must be greater than 0")

    if scale == 1:
        return image

    h, w = image.shape[:2]
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))

    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def image_to_base64(image: np.ndarray) -> str:
    """
    np.ndarray -> base64 png
    """
    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)

    # 如果是 BGR，转成 RGB
    if len(image.shape) == 3 and image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    pil_img = Image.fromarray(image)
    buf = BytesIO()
    pil_img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _extract_json_text(text: str) -> str:
    """从模型返回文本中提取 JSON 字符串。"""

    stripped_text = (text or "").strip()

    fence_match = re.search(
        r"```(?:json)?\s*(.*?)\s*```",
        stripped_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fence_match:
        return fence_match.group(1).strip()

    object_start = stripped_text.find("{")
    object_end = stripped_text.rfind("}")

    if object_start != -1 and object_end != -1 and object_end > object_start:
        return stripped_text[object_start : object_end + 1]

    return stripped_text



def _normalize_center(center: list[int | float]) -> list[float] | None:
    """将模型输出的 1~1000 坐标归一化为 0~1。"""

    x, y = float(center[0]), float(center[1])

    # 新提示词要求输出 1~1000；保留对历史 0~1 缓存/返回的兼容。
    if 0 <= x <= 1 and 0 <= y <= 1:
        return [x, y]

    if 0 <= x <= 1000 and 0 <= y <= 1000:
        return [x / 1000, y / 1000]

    return None



def parse_layout(text: str) -> dict[str, list[list[float]]]:
    """解析模型返回的键盘布局 JSON。

    兼容模型直接返回 JSON，以及返回 ```json ... ``` Markdown 代码块的情况。
    """

    data = json.loads(_extract_json_text(text))
    results = data.get("results", [])

    key_map: dict[str, list[list[float]]] = {}

    for item in results:
        if not isinstance(item, list) or len(item) != 2:
            continue

        label, center = item
        if not isinstance(label, str):
            continue

        if (
            not isinstance(center, list)
            or len(center) != 2
            or not all(isinstance(v, (int, float)) for v in center)
        ):
            continue

        center = _normalize_center(center)
        if center is None:
            continue

        key_map.setdefault(label, []).append(center)

    return key_map
