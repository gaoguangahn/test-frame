from typing import Any


def build_image_message(image_base64: str, mime: str = "image/png") -> dict[str, Any]:
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{image_base64}"},
    }
