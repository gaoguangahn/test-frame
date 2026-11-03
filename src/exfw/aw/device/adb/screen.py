import os
import subprocess
import time
from contextlib import contextmanager

import cv2
import numpy as np

from .base.mixin_base import AdbMixinBase


class AdbScreenMixin(AdbMixinBase):
    def screenshot(self, scale_factor: float = 1.0) -> np.ndarray:
        """安卓设备截图"""

        try:
            image = self.device.screenshot(format="opencv")
            if image is None:
                self.logger.error("device.screenshot failed")
                raise

            if not isinstance(image, np.ndarray):
                image = np.asarray(image)

            if scale_factor != 1.0:
                image = cv2.resize(
                    image, dsize=(0, 0), fx=scale_factor, fy=scale_factor
                )

            return image
        except Exception as e:
            self.logger.error(f"screenshot failed: {e}")
            raise

    def start_snap(
        self, video_path: str, bit_rate: str = "4M", max_size: int = 1080
    ) -> subprocess.Popen | None:
        """开始屏幕录屏"""
        try:
            ext = os.path.splitext(video_path)[1].lower()

            if ext == ".mkv":
                record_format = "mkv"
            elif ext == ".mp4":
                record_format = None
            else:
                raise ValueError("video_path must end with .mkv or .mp4")

            video_dir = os.path.dirname(video_path)
            if video_dir:
                os.makedirs(video_dir, exist_ok=True)

            if os.path.exists(video_path):
                try:
                    os.remove(video_path)
                except OSError:
                    pass

            cmd = [
                self.scrcpy_path,
                "--no-audio",
                "--no-window",
                "--no-control",
                "--serial",
                self.serial,
                "--record",
                video_path,
                "--force-adb-forward",
                "--video-bit-rate",
                bit_rate,
                "--max-size",
                str(max_size),
            ]

            if record_format == "mkv":
                cmd += ["--record-format", "mkv"]

            record_proc = subprocess.Popen(
                cmd,
                startupinfo=subprocess.STARTUPINFO(),
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            time.sleep(2)
            return record_proc
        except Exception:
            self.logger.exception("start_snap: failed")
            raise

    def stop_snap(self, record_proc: subprocess.Popen, timeout: int = 5):
        """停止指定的录屏"""
        if record_proc is None or record_proc.poll() is not None:
            return

        try:
            record_proc.terminate()
            record_proc.wait(timeout=timeout)
        except Exception:
            try:
                record_proc.kill()
            except Exception as e:
                self.logger.error(f"stop_snap: kill failed, {e}")
                raise

    @contextmanager
    def recording(
        self,
        video_path: str,
        bit_rate: str = "4M",
        max_size: int = 1080,
        timeout: int = 5,
    ):
        """录屏上下文管理器"""
        proc = self.start_snap(
            video_path=video_path, bit_rate=bit_rate, max_size=max_size
        )
        try:
            yield proc
        finally:
            if proc is not None:
                self.stop_snap(proc, timeout=timeout)
