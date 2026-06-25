"""
AstrBot 图片工具箱插件 main.py

功能：
- 旋转 — 任意角度旋转图片/GIF (/旋转 90)
- 对称 — 轴对称：取一半镜像到另一半 (/对称 上)
- 翻转 — 整体镜像翻转 (/翻转 水平)
- 变速 — 调整GIF播放速度 (/变速 2.0)
- 万花筒 — 对称分段式万花筒效果 (/万花筒)
- 裸眼3D — 分层假象裸眼3D效果 (/裸眼3d)
"""

import io
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp

from .image_processor import (
    rotate_image,
    symmetry_image,
    flip_image,
    speed_change,
    kaleidoscope,
    bare_eye_3d,
)


class ImgToolPlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}

        # 裸眼3D 参数
        self.line_spacing = self.config.get("line_spacing", 80)
        self.line_width = self.config.get("line_width", 3)
        self.line_alpha = self.config.get("line_alpha", 200)
        self.line_direction = self.config.get("line_direction", "both")
        self.mask_threshold = self.config.get("mask_threshold", 25)
        self.mask_blur = self.config.get("mask_blur", 7)
        self.foreground_blur = self.config.get("foreground_blur", 0)
        self.max_frames = self.config.get("max_frames", 48)

        # 万花筒参数
        self.kaleidoscope_segments = self.config.get("kaleidoscope_segments", 8)
        self.kaleidoscope_zoom = self.config.get("kaleidoscope_zoom", 1.0)

        # 临时目录
        self.temp_dir = Path(tempfile.gettempdir()) / "astrbot_imgtool"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    # ============================================================
    #  旋转
    # ============================================================

    @filter.command("旋转")
    async def rotate(self, event: AstrMessageEvent, angle: str = "90"):
        """旋转图片/GIF。可指定角度，如 /旋转 90、/旋转 -45。"""
        yield event.plain_result(f"🔄 正在旋转 {angle}°，请稍候...")

        try:
            angle_float = float(angle)
        except ValueError:
            yield event.plain_result("❌ 角度格式错误，请输入数字，如：/旋转 90")
            return

        try:
            image_data = await self._extract_image(event)
            if image_data is None:
                yield event.plain_result("❌ 没有找到图片或GIF。请引用一张图片消息，或直接发送图片并附带指令。")
                return

            output = rotate_image(image_data, angle=angle_float)
            yield event.image_result(self._save_temp_image(output, "rotated"))
        except Exception as e:
            logger.error(f"旋转处理失败: {str(e)}")
            yield event.plain_result(f"❌ 处理失败: {str(e)}")

    # ============================================================
    #  对称 (轴对称) — 取图像一半对称补到另一半
    # ============================================================

    @filter.command("对称")
    async def symmetry(self, event: AstrMessageEvent, direction: str = "上"):
        """轴对称：将图像从中线分开，取一半对称到另一半。
        方向: 上/下/左/右，如 /对称 上、/对称 右"""
        yield event.plain_result("🪞 正在处理轴对称效果，请稍候...")

        dir_map = {
            "上": "top", "下": "bottom", "左": "left", "右": "right",
            "top": "top", "bottom": "bottom", "left": "left", "right": "right",
            "t": "top", "b": "bottom", "l": "left", "r": "right",
        }
        actual_dir = dir_map.get(direction)
        if actual_dir is None:
            yield event.plain_result("❌ 方向格式错误，请输入：上/下/左/右，如：/对称 上")
            return

        try:
            image_data = await self._extract_image(event)
            if image_data is None:
                yield event.plain_result("❌ 没有找到图片或GIF。请引用一张图片消息，或直接发送图片并附带指令。")
                return

            output = symmetry_image(image_data, direction=actual_dir)
            yield event.image_result(self._save_temp_image(output, "symmetry"))
        except Exception as e:
            logger.error(f"对称处理失败: {str(e)}")
            yield event.plain_result(f"❌ 处理失败: {str(e)}")

    # ============================================================
    #  翻转 (整体镜像) — 原 mirror/flip 功能保留
    # ============================================================

    @filter.command("翻转")
    async def flip(self, event: AstrMessageEvent, direction: str = "水平"):
        """整体翻转图片/GIF（镜像）。方向: 水平/垂直，如 /翻转 水平、/翻转 垂直"""
        yield event.plain_result("🪞 正在处理翻转效果，请稍候...")

        dir_map = {
            "水平": "horizontal", "垂直": "vertical",
            "horizontal": "horizontal", "vertical": "vertical",
            "h": "horizontal", "v": "vertical",
        }
        actual_dir = dir_map.get(direction)
        if actual_dir is None:
            yield event.plain_result("❌ 方向格式错误，请输入 水平 或 垂直，如：/翻转 水平")
            return

        try:
            image_data = await self._extract_image(event)
            if image_data is None:
                yield event.plain_result("❌ 没有找到图片或GIF。请引用一张图片消息，或直接发送图片并附带指令。")
                return

            output = flip_image(image_data, direction=actual_dir)
            yield event.image_result(self._save_temp_image(output, "flip"))
        except Exception as e:
            logger.error(f"翻转处理失败: {str(e)}")
            yield event.plain_result(f"❌ 处理失败: {str(e)}")

    # ============================================================
    #  变速
    # ============================================================

    @filter.command("变速")
    async def speed(self, event: AstrMessageEvent, factor: str = "2.0"):
        """调整GIF播放速度。如 /变速 2.0（倍速）、/变速 0.5（半速）。"""
        yield event.plain_result(f"⏩ 正在调整速度为 {factor}x，请稍候...")

        try:
            speed_factor = float(factor)
            if speed_factor <= 0:
                yield event.plain_result("❌ 速度因子必须大于0")
                return
        except ValueError:
            yield event.plain_result("❌ 速度因子格式错误，请输入数字，如：/变速 2.0")
            return

        try:
            image_data = await self._extract_image(event)
            if image_data is None:
                yield event.plain_result("❌ 没有找到图片或GIF。请引用一张GIF消息，或直接发送GIF并附带指令。")
                return

            # 检查是否为GIF
            if not self._is_gif_data(image_data):
                yield event.plain_result("❌ 变速仅支持GIF格式，请发送GIF图片。")
                return

            output = speed_change(image_data, speed=speed_factor)
            yield event.image_result(self._save_temp_image(output, "speed"))
        except Exception as e:
            logger.error(f"变速处理失败: {str(e)}")
            yield event.plain_result(f"❌ 处理失败: {str(e)}")

    # ============================================================
    #  万花筒
    # ============================================================

    @filter.command("万花筒")
    async def kaleidoscope_cmd(self, event: AstrMessageEvent, segments: str = None):
        """对图片或GIF应用万花筒效果。可选参数分段数，如 /万花筒 8。"""
        yield event.plain_result("🔮 正在生成万花筒效果，请稍候...")

        seg = self.kaleidoscope_segments
        if segments:
            try:
                seg = int(segments)
                if seg < 3 or seg > 64:
                    yield event.plain_result("❌ 分段数推荐在 3-64 之间")
                    return
            except ValueError:
                yield event.plain_result("❌ 分段数格式错误，请输入整数，如：/万花筒 8")
                return

        try:
            image_data = await self._extract_image(event)
            if image_data is None:
                yield event.plain_result("❌ 没有找到图片或GIF。请引用一张图片消息，或直接发送图片并附带指令。")
                return

            output = kaleidoscope(
                image_data,
                segments=seg,
                zoom=self.kaleidoscope_zoom,
                max_frames=self.max_frames,
            )
            yield event.image_result(self._save_temp_image(output, "kaleidoscope"))
        except Exception as e:
            logger.error(f"万花筒处理失败: {str(e)}")
            yield event.plain_result(f"❌ 处理失败: {str(e)}")

    # ============================================================
    #  裸眼3D
    # ============================================================

    @filter.command("裸眼3d")
    async def bare_eye_3d_cmd(self, event: AstrMessageEvent):
        """将GIF转换为裸眼3D效果。请引用一条GIF消息或直接发送GIF并附带此指令。"""
        yield event.plain_result("🕶️ 正在处理裸眼3D效果，请稍候...")

        try:
            gif_data = await self._extract_image(event)
            if gif_data is None:
                yield event.plain_result(
                    "❌ 没有找到GIF图片。请引用一条GIF消息，或直接发送GIF并附带指令。"
                )
                return

            if not self._is_gif_data(gif_data):
                # 静态图片也支持裸眼3D（仅画线效果）
                pass

            logger.info(f"开始处理裸眼3D, 线间距={self.line_spacing}, 线宽={self.line_width}")
            output_data = bare_eye_3d(
                gif_data,
                line_spacing=self.line_spacing,
                line_width=self.line_width,
                line_alpha=self.line_alpha,
                line_direction=self.line_direction,
                mask_threshold=self.mask_threshold,
                mask_blur=self.mask_blur,
                foreground_blur=self.foreground_blur,
                max_frames=self.max_frames,
            )

            yield event.image_result(self._save_temp_image(output_data, "bare_eye_3d"))
        except ValueError as e:
            yield event.plain_result(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"裸眼3D处理失败: {str(e)}")
            yield event.plain_result(f"❌ 处理失败: {str(e)}")

    # ============================================================
    #  帮助
    # ============================================================

    @filter.command("图tool", alias={"img_help", "图帮助"})
    async def help_cmd(self, event: AstrMessageEvent):
        """显示图片工具箱帮助信息。"""
        help_text = (
            "🎨 图片工具箱指令\n"
            "────────────────\n"
            "发送或引用一张图片/GIF，附带以下指令：\n\n"
            "🔄 /旋转 [角度]  — 旋转图片，如 /旋转 90\n"
            "🪞 /对称 [方向]  — 轴对称：上/下/左/右\n"
            "🪞 /翻转 [方向]  — 整体翻转：水平/垂直\n"
            "⏩ /变速 [因子]  — GIF变速，如 /变速 2.0\n"
            "🔮 /万花筒 [段数] — 万花筒效果，如 /万花筒 8\n"
            "🕶️ /裸眼3d       — 裸眼3D效果\n"
            "📖 /图tool       — 显示本帮助"
        )
        yield event.plain_result(help_text)

    # ============================================================
    #  图片/GIF 提取 （统一提取方法，支持静态图和GIF）
    # ============================================================

    async def _extract_image(self, event: AstrMessageEvent) -> Optional[bytes]:
        """
        从消息中提取图片或GIF数据。
        支持：
        1. 当前消息中的 Image 组件
        2. File 组件（GIF文件）
        3. 回复消息中的图片/GIF
        4. 消息文本中的图片 URL
        """
        message_chain = event.message_obj.message

        # 1. 直接检查当前消息中的 Image 组件
        for comp in message_chain:
            if isinstance(comp, Comp.Image):
                img_bytes = await self._try_get_image_bytes(comp)
                if img_bytes:
                    return img_bytes

            if isinstance(comp, Comp.File):
                if hasattr(comp, "name") and comp.name:
                    if comp.name.lower().endswith((".gif", ".png", ".jpg", ".jpeg", ".webp")):
                        img_bytes = await self._try_get_image_bytes(comp)
                        if img_bytes:
                            return img_bytes

        # 2. 处理回复消息
        for comp in message_chain:
            if isinstance(comp, Comp.Reply):
                img_bytes = await self._extract_image_from_reply(event, comp)
                if img_bytes:
                    return img_bytes

        # 3. 检查消息字符串中是否包含图片URL
        msg_text = event.message_str
        img_urls = re.findall(
            r"https?://[^\s)]+\.(?:gif|png|jpg|jpeg|webp|bmp)", msg_text, re.I
        )
        for url in img_urls:
            data = await self._download_file(url)
            if data:
                return data

        return None

    async def _extract_image_from_reply(
        self, event: AstrMessageEvent, reply_comp: Comp.Reply
    ) -> Optional[bytes]:
        """从被回复的消息中提取图片/GIF。"""
        platform = event.get_platform_name()
        reply_id = getattr(reply_comp, "id", None)

        if not reply_id:
            return None

        # aiocqhttp (QQ个人号 / OneBot协议)
        if platform == "aiocqhttp":
            try:
                # 方法一：从 raw_message 的 source 段提取
                raw = event.message_obj.raw_message
                if isinstance(raw, dict):
                    source_seg = raw.get("message", [{}]) if isinstance(raw.get("message"), list) else []
                    raw_image_urls = []
                    if isinstance(source_seg, list):
                        for seg in source_seg:
                            if isinstance(seg, dict) and seg.get("type") == "image":
                                url = seg.get("data", {}).get("url", "")
                                if url:
                                    raw_image_urls.append(url)
                    for url in raw_image_urls:
                        data = await self._download_file(url)
                        if data:
                            return data

                # 方法二：通过协议端 API get_msg
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                    AiocqhttpMessageEvent,
                )
                assert isinstance(event, AiocqhttpMessageEvent)
                client = event.bot
                payload = {"message_id": int(reply_id) if str(reply_id).isdigit() else reply_id}
                result = await client.api.call_action("get_msg", **payload)
                raw_msg = result.get("message", [])
                if isinstance(raw_msg, list):
                    for seg in raw_msg:
                        if seg.get("type") == "image":
                            url = seg.get("data", {}).get("url", "")
                            file_path = seg.get("data", {}).get("file", "")
                            if url:
                                data = await self._download_file(url)
                                if data:
                                    return data
                            if file_path and os.path.isfile(file_path):
                                with open(file_path, "rb") as f:
                                    return f.read()
            except Exception as e:
                logger.warning(f"aiocqhttp 获取回复消息失败: {e}")

        # QQ官方接口
        elif platform == "qq_official":
            try:
                from astrbot.core.platform.sources.qq_official.qq_official_message_event import (
                    QQOfficialMessageEvent,
                )
                assert isinstance(event, QQOfficialMessageEvent)
                raw = event.message_obj.raw_message
                if hasattr(raw, "attachments"):
                    for att in raw.attachments:
                        if att.content_type and ("image" in att.content_type.lower() or "gif" in att.content_type.lower()):
                            url = getattr(att, "url", None)
                            if url:
                                data = await self._download_file(url)
                                if data:
                                    return data
            except Exception as e:
                logger.warning(f"qq_official 获取回复消息失败: {e}")

        # Telegram
        elif platform == "telegram":
            try:
                from astrbot.core.platform.sources.telegram.telegram_message_event import (
                    TelegramMessageEvent,
                )
                assert isinstance(event, TelegramMessageEvent)
                raw = event.message_obj.raw_message
                reply_to = getattr(raw, "reply_to_message", None)
                if reply_to:
                    doc = getattr(reply_to, "document", None) or getattr(reply_to, "animation", None)
                    if doc:
                        file_id = getattr(doc, "file_id", None)
                        if file_id:
                            token = self._get_telegram_token(event)
                            if token:
                                file_url = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
                                import aiohttp
                                async with aiohttp.ClientSession() as session:
                                    async with session.get(file_url) as resp:
                                        if resp.status == 200:
                                            j = await resp.json()
                                            if j.get("ok"):
                                                file_path = j["result"]["file_path"]
                                                download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
                                                data = await self._download_file(download_url)
                                                if data:
                                                    return data
            except Exception as e:
                logger.warning(f"telegram 获取回复消息失败: {e}")

        # 未知平台: 尝试从 raw_message 中搜索图片URL
        else:
            try:
                raw = event.message_obj.raw_message
                raw_str = str(raw)
                urls = re.findall(r"https?://[^\s)]+\.(?:gif|png|jpg|jpeg|webp)", raw_str, re.I)
                for url in urls:
                    data = await self._download_file(url)
                    if data:
                        return data
            except Exception as e:
                logger.warning(f"{platform} 获取回复消息失败: {e}")

        return None

    def _get_telegram_token(self, event: AstrMessageEvent) -> Optional[str]:
        """尝试获取 Telegram bot token。"""
        try:
            from astrbot.core.platform.sources.telegram.telegram_message_event import (
                TelegramMessageEvent,
            )
            assert isinstance(event, TelegramMessageEvent)
            raw = event.message_obj.raw_message
            bot = getattr(raw, "get_bot", None) or getattr(raw, "bot", None)
            if bot:
                return getattr(bot, "token", None)
        except Exception:
            pass
        return None

    async def _try_get_image_bytes(self, comp) -> Optional[bytes]:
        """尝试从消息组件中获取图片/GIF字节数据。"""
        if hasattr(comp, "file") and comp.file:
            file_path = comp.file
            if os.path.isfile(file_path):
                try:
                    with open(file_path, "rb") as f:
                        return f.read()
                except Exception:
                    pass
            elif str(file_path).startswith(("http://", "https://")):
                return await self._download_file(file_path)

        if hasattr(comp, "url") and comp.url:
            return await self._download_file(comp.url)

        return None

    async def _download_file(self, url: str) -> Optional[bytes]:
        """下载文件并返回字节数据。"""
        import aiohttp
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception as e:
            logger.warning(f"下载文件失败 {url}: {str(e)}")
        return None

    def _is_gif_data(self, data: bytes) -> bool:
        """检查字节数据是否为GIF格式。"""
        return data[:6] in (b"GIF87a", b"GIF89a")

    def _save_temp_image(self, data: bytes, tag: str) -> str:
        """保存临时文件并返回路径。"""
        ext = ".gif" if self._is_gif_data(data) else ".png"
        temp_path = self.temp_dir / f"output_{tag}_{id(self)}_{os.urandom(4).hex()}{ext}"
        with open(temp_path, "wb") as f:
            f.write(data)
        return str(temp_path)

    async def terminate(self):
        """插件被卸载/停用时清理临时目录。"""
        try:
            import shutil
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass