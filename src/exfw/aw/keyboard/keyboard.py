import json
import logging
from logging import Logger
from pathlib import Path
from typing import Any

import numpy as np

from exfw.aw.device import AdbDriver
from exfw.common.llm import LLMClient

from .util import image_to_base64, parse_layout, resize_image_by_scale


class Keyboard:
    def __init__(
        self,
        driver: AdbDriver,
        resources_dir: Path,
        client: LLMClient | None = None,
        logger: Logger | None = None,
    ):
        self.client = client or LLMClient()
        self.driver = driver
        self.logger = logger or logging.getLogger("exfw.Keyboard")

        self.resources_dir = resources_dir
        self.width, self.height = driver.width, driver.height
        self.cached_key_map: dict[str, list[list[float]]] = {}

        self.prompt = self._load_prompt()

    @staticmethod
    def _load_prompt() -> str:
        prompt_file = Path(__file__).resolve().parent / "prompt.md"
        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()

    def init_by_model(self, model: str) -> bool:
        """
        按设备型号初始化键盘布局。

        资源目录结构示例：

        resources/
        └── keyboard/
            └── HONOR-TEST/
                ├── letter.png
                ├── digit.png
                └── layout.json
        """
        model_res_dir = self.resources_dir / "keyboard" / model
        json_path = model_res_dir / "layout.json"
        letter_path = model_res_dir / "letter.png"
        digit_path = model_res_dir / "digit.png"

        # 步骤 1：尝试直接加载已有的 JSON 坐标
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.update_cache(data)
                self.logger.info(f"成功从本地缓存加载设备 {model} 的键盘坐标")
                return True
            except Exception as e:
                self.logger.warning(f"读取缓存文件 {json_path} 失败: {e}")

        # 步骤 2：如果没有 JSON，检查图片是否存在
        if not (letter_path.exists() and digit_path.exists()):
            self.logger.warning(
                f"设备 {model} 资源不完整（需 letter.png 和 digit.png），无法进行初始化"
            )
            return False

        # 步骤 3：调用 LLM 进行识别
        try:
            self.logger.info(f"未发现缓存，开始通过 LLM 识别设备 {model} 的键盘资源...")
            import cv2

            # 识别字母页
            letter_img = cv2.imread(str(letter_path))
            if letter_img is not None:
                self.recognize(letter_img)

            # 识别数字页
            digit_img = cv2.imread(str(digit_path))
            if digit_img is not None:
                self.recognize(digit_img)

            # 步骤 4：识别成功后，保存 JSON 坐标，实现“自进化”
            if self.can_keyboard_input():
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(self.cached_key_map, f, ensure_ascii=False, indent=4)
                self.logger.info(
                    f"设备 {model} 布局识别完成，坐标已持久化至 {json_path}"
                )
                return True
            else:
                self.logger.error(f"设备 {model} 识别结果不完整，未保存 JSON")
                return False

        except Exception as e:
            self.logger.error(f"解析设备 {model} 资源时发生异常: {e}")
            self.clear_cache()
            return False

    def _build_user_content(self, full_image_base64: str) -> list[dict[str, Any]]:
        return [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{full_image_base64}"},
            },
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "intent": "识别键盘中所有可见按键的位置，输出相对整张图的归一化坐标",
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    def update_cache(self, new_map: dict[str, list[list[float]]]):
        """
        合并新识别到的按键布局到全局缓存中
        """
        for label, centers in new_map.items():
            self.cached_key_map.setdefault(label, [])
            for center in centers:
                if center not in self.cached_key_map[label]:
                    self.cached_key_map[label].append(center)

    def recognize(self, image: np.ndarray) -> dict[str, list[list[float]]]:
        """
        输入 np 格式图片，内部先缩放，再发送给模型
        返回当前图片解析出来的 key_map
        """

        self.logger.info("开始识别键盘布局...")

        resized = resize_image_by_scale(image, scale=0.5)

        full_base64 = image_to_base64(resized)

        messages = [
            {
                "role": "system",
                "content": self.prompt,
            },
            {
                "role": "user",
                "content": self._build_user_content(full_base64),
            },
        ]

        resp = self.client.chat(messages=messages, max_tokens=4096, stream=False)

        if resp.error:
            self.logger.error("模型识别失败: %s", resp.error)
            raise RuntimeError(resp.error)

        try:
            new_map = parse_layout(resp.text)
        except Exception:
            self.logger.exception("解析模型返回失败，原文: %r", resp.text)
            raise

        self.logger.info("解析完成，本次识别到按键种类数: %d", len(new_map))

        self.update_cache(new_map)

        return new_map

    def clear_cache(self):
        self.cached_key_map = {}

    def has_key(self, key: str) -> bool:
        return key in self.cached_key_map and len(self.cached_key_map[key]) > 0

    def has_all_keys(self, keys: list[str]) -> bool:
        return all(self.has_key(k) for k in keys)

    def can_keyboard_input(self) -> bool:
        """
        判断当前缓存是否支持“字母页 + 数字页”切换输入
        """
        # letters = list("abcdefghijklmnopqrstuvwxyz")
        # digits = list("123456789")

        return self.has_all_keys(["123", "返回"])

    def get_key_center(self, ch: str) -> list[float] | None:
        """
        根据字符获取第一个匹配到的中心点坐标
        """
        centers = self.cached_key_map.get(ch)
        if not centers:
            return None
        return centers[0]

    def press(self, ch: str):
        """
        点击单个字符对应的按键
        """
        center = self.get_key_center(ch)
        if center is None:
            self.logger.warning(f"找不到按键: {ch}, 使用 driver.set_text(ch) 代替")
            self.driver.set_text(ch)
            return

        self.driver.click(point=center)

    def input_text(self, text: str):
        """
        优先使用键盘点击输入；
        如果缓存不完整，则退化为 driver.input(text)
        支持字母数字交叉输入，例如 adb123efg
        """
        if not self.can_keyboard_input():
            self.logger.warning("当前缓存不支持键盘输入，退化为 driver.set_text(text)")
            self.driver.set_text(text)
            return

        current_mode = "letter"

        for ch in text:
            if ch.isdigit():
                if current_mode != "digit":
                    self.press("123")
                    current_mode = "digit"
                self.press(ch)

            elif ch.isalpha():
                if current_mode != "letter":
                    self.press("返回")
                    current_mode = "letter"

                lower_ch = ch.lower()
                self.press(lower_ch)

            else:
                self.driver.set_text(ch)
