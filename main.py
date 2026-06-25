"""
AstrBot 图像工具箱插件 main.py

功能：
- 旋转   — 图片/GIF任意角度旋转
- 对称   — 水平/垂直/对角线镜像翻转
- 变速   — GIF播放速度调节
- 万花筒 — 经典万花筒/多镜像特效

用法示例：
  /旋转 90          ← 旋转90度
  /对称 水平         ← 水平翻转
  /变速 2.0          ← 2倍速
  /万花筒 8          ← 8段万花筒
"""

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp

from .image_processor import (
    rotate_image,
    rotate_gif,
    mirror_image,
    mirror_gif,
    speed_change_gif,
    kaleidoscope_image,
    kaleidoscope_gif,
    kaleidoscope_triangle_gif,
    _is_gif_data,
)


class ImageToolPlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        # 最大处理帧数
        self.max_frames = self.config.get("max_frames", 100)
        # 万花筒默认分割数
        self.kaleidoscope_segments = self.config.get("kaleidoscope_segments", 8)
        # 临时目录
        self.temp_dir = Path(tempfile.gettempdir()) / "astrbot_imgtool"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    # ============================================================
    #  命令1：旋转 (Rotate)
    # ============================================================

    @filter.command("旋转")
    async def cmd_rotate(self, event: AstrMessageEvent, *extra_args):
        """
        旋转图片/GIF。
        用法: /旋转 <角度>
        示例: /旋转 90, /旋转 -45, /旋转 180
        """
        parts = event.message_str.strip().split(maxsplit=1)
        angle = 90  # 默认角度

        if len(parts) >= 2:
            try:
                angle = float(parts[1])
            except ValueError:
                yield event.plain_result("❌ 角度格式错误，请输入数字，如 90、-45、180")
                return

        yield event.plain_result(f"🔄 正在旋转 {angle}°...")

        try:
            data = await self._extract_image(event)
            if data is None:
                yield event.plain_result("❌ 没有找到图片/GIF。请发送图片并附带指令，或回复一条图片消息。")
                return

            if _is_gif_data(data):
                logger.info(f"旋转GIF: angle={angle}, max_frames={self.max_frames}")
                output = rotate_gif(data, angle=angle, max_frames=self.max_frames)
            else:
                logger.info(f"旋转图片: angle={angle}")
                output = rotate_image(data, angle=angle)

            await self._send_result(event, output)

        except ValueError as e:
            yield event.plain_result(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"旋转处理失败: {str(e)}")
            yield event.plain_result(f"❌ 处理失败: {str(e)}")

    # ============================================================
    #  命令2：对称 (Mirror / Flip)
    # ============================================================

    @filter.command("对称")
    async def cmd_mirror(self, event: AstrMessageEvent, *extra_args):
        """
        镜像/翻转图片/GIF。
        用法: /对称 <方向>
        方向: 水平(默认), 垂直, 上下, both(同时翻转)
        示例: /对称 水平, /对称 垂直, /对称 both
        """
        parts = event.message_str.strip().split(maxsplit=1)
        direction = "horizontal"  # 默认水平

        if len(parts) >= 2:
            raw = parts[1].strip().lower()
            direction_map = {
                "水平": "horizontal",
                "左右": "horizontal",
                "horizontal": "horizontal",
                "h": "horizontal",
                "垂直": "vertical",
                "上下": "vertical",
                "vertical": "vertical",
                "v": "vertical",
                "both": "both",
                "全部": "both",
                "全": "both",
                "b": "both",
            }
            direction = direction_map.get(raw, "horizontal")

        dir_label = {"horizontal": "水平", "vertical": "垂直", "both": "双向"}.get(direction, direction)
        yield event.plain_result(f"🪞 正在执行{dir_label}对称...")

        try:
            data = await self._extract_image(event)
            if data is None:
                yield event.plain_result("❌ 没有找到图片/GIF。请发送图片并附带指令，或回复一条图片消息。")
                return

            if _is_gif_data(data):
                logger.info(f"对称GIF: direction={direction}")
                output = mirror_gif(data, direction=direction, max_frames=self.max_frames)
            else:
                logger.info(f"对称图片: direction={direction}")
                output = mirror_image(data, direction=direction)

            await self._send_result(event, output)

        except ValueError as e:
            yield event.plain_result(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"对称处理失败: {str(e)}")
            yield event.plain_result(f"❌ 处理失败: {str(e)}")

    # ============================================================
    #  命令3：变速 (Speed — GIF only)
    # ============================================================

    @filter.command("变速")
    async def cmd_speed(self, event: AstrMessageEvent, *extra_args):
        """
        调整GIF播放速度。
        用法: /变速 <倍率>
        示例: /变速 2.0 (2倍速), /变速 0.5 (半速), /变速 3 (3倍速)
        """
        parts = event.message_str.strip().split(maxsplit=1)
        speed = 1.0  # 默认不变

        if len(parts) >= 2:
            try:
                speed = float(parts[1])
                if speed <= 0:
                    yield event.plain_result("❌ 速度必须大于0")
                    return
            except ValueError:
                yield event.plain_result("❌ 速度格式错误，请输入数字，如 2.0、0.5、3")
                return

        yield event.plain_result(f"⏩ 正在调整速度至 {speed}x...")

        try:
            data = await self._extract_image(event)
            if data is None:
                yield event.plain_result("❌ 没有找到GIF。请发送GIF并附带指令，或回复一条GIF消息。")
                return

            if not _is_gif_data(data):
                yield event.plain_result("❌ 变速仅支持GIF格式")
                return

            logger.info(f"变速GIF: speed={speed}")
            output = speed_change_gif(data, speed=speed, max_frames=self.max_frames)

            await self._send_result(event, output)

        except ValueError as e:
            yield event.plain_result(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"变速处理失败: {str(e)}")
            yield event.plain_result(f"❌ 处理失败: {str(e)}")

    # ============================================================
    #  命令4：万花筒 (Kaleidoscope)
    # ============================================================

    @filter.command("万花筒")
    async def cmd_kaleidoscope(self, event: AstrMessageEvent, *extra_args):
        """
        对图片/GIF应用万花筒效果。
        用法: /万花筒 [分割数] [旋转增量]
        示例:
          /万花筒           ← 8段经典万花筒
          /万花筒 12        ← 12段
          /万花筒 8 2       ← 8段，每帧旋转2°
        """
        parts = event.message_str.strip().split(maxsplit=2)
        segments = self.kaleidoscope_segments
        rotation_delta = 0.0

        if len(parts) >= 2:
            try:
                segments = int(parts[1])
                if segments < 4:
                    yield event.plain_result("❌ 分割数至少为4")
                    return
                if segments > 24:
                    yield event.plain_result("❌ 分割数最多为24")
                    return
            except ValueError:
                yield event.plain_result("❌ 分割数格式错误，请输入整数，如 4、8、12")
                return

        if len(parts) >= 3:
            try:
                rotation_delta = float(parts[2])
            except ValueError:
                yield event.plain_result("❌ 旋转增量格式错误，请输入数字，如 0、2、5")
                return

        if rotation_delta > 0:
            yield event.plain_result(f"🌸 正在生成 {segments}段 旋转万花筒动画...")
        else:
            yield event.plain_result(f"🌸 正在生成 {segments}段 万花筒效果...")

        try:
            data = await self._extract_image(event)
            if data is None:
                yield event.plain_result("❌ 没有找到图片/GIF。请发送图片并附带指令，或回复一条图片消息。")
                return

            if _is_gif_data(data):
                if rotation_delta > 0:
                    logger.info(f"万花筒GIF(动画): segments={segments}, rotation_delta={rotation_delta}")
                    output = kaleidoscope_gif(
                        data,
                        segments=segments,
                        rotation_delta=rotation_delta,
                        max_frames=self.max_frames,
                    )
                else:
                    logger.info(f"万花筒GIF(三角对称): segments={segments}")
                    output = kaleidoscope_triangle_gif(
                        data,
                        segments=segments,
                        rotation_delta=0,
                        max_frames=self.max_frames,
                    )
            else:
                logger.info(f"万花筒图片: segments={segments}")
                output = kaleidoscope_image(data, segments=segments, rotation=rotation_delta)

            await self._send_result(event, output)

        except ValueError as e:
            yield event.plain_result(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"万花筒处理失败: {str(e)}")
            yield event.plain_result(f"❌ 处理失败: {str(e)}")

    # ============================================================
    #  图像提取工具（参考 3dgif 插件的实现）
    # ============================================================

    async def _extract_image(self, event: AstrMessageEvent) -> Optional[bytes]:
        """
        从消息中提取图片/GIF数据。
        查找顺序：
        1. 当前消息链中的 Image 或 File 组件
        2. 回复消息 → 调用平台API获取被回复消息的内容
        3. 消息文本中的图片/GIF URL
        """
        message_chain = event.message_obj.message

        # 1. 直接检查当前消息中的 Image / File 组件
        for comp in message_chain:
            if isinstance(comp, Comp.Image):
                img_bytes = await self._try_get_bytes(comp)
                if img_bytes:
                    return img_bytes

            if isinstance(comp, Comp.File):
                if hasattr(comp, "name") and comp.name:
                    name_lower = comp.name.lower()
                    if name_lower.endswith((".gif", ".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                        img_bytes = await self._try_get_bytes(comp)
                        if img_bytes:
                            return img_bytes

        # 2. 处理回复消息
        for comp in message_chain:
            if isinstance(comp, Comp.Reply):
                img_bytes = await self._extract_from_reply(event, comp)
                if img_bytes:
                    return img_bytes

        # 3. 检查消息文本中的图片 URL
        msg_text = event.message_str
        urls = re.findall(r"https?://[^\s)]+\.(?:gif|png|jpg|jpeg|webp|bmp)(?:\?[^\s)]*)?", msg_text, re.I)
        for url in urls:
            data = await self._download_file(url)
            if data and len(data) > 100:
                return data

        return None

    async def _extract_from_reply(self, event: AstrMessageEvent, reply_comp: Comp.Reply) -> Optional[bytes]:
        """从被回复的消息中提取图片，兼容多平台"""
        platform = event.get_platform_name()
        reply_id = getattr(reply_comp, "id", None)

        if not reply_id:
            return None

        # ---- aiocqhttp (OneBot) ----
        if platform == "aiocqhttp":
            try:
                raw = event.message_obj.raw_message
                if isinstance(raw, dict):
                    source_seg = raw.get("message", [{}]) if isinstance(raw.get("message"), list) else []
                    for seg in source_seg if isinstance(source_seg, list) else []:
                        if isinstance(seg, dict) and seg.get("type") in ("image", "file"):
                            url = seg.get("data", {}).get("url", "")
                            if url:
                                data = await self._download_file(url)
                                if data and len(data) > 100:
                                    return data

                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                    AiocqhttpMessageEvent,
                )
                assert isinstance(event, AiocqhttpMessageEvent)
                client = event.bot
                payload = {"message_id": int(reply_id) if str(reply_id).isdigit() else reply_id}
                result = await client.api.call_action("get_msg", **payload)
                raw_msg = result.get("message", [])
                for seg in raw_msg if isinstance(raw_msg, list) else []:
                    if seg.get("type") == "image":
                        url = seg.get("data", {}).get("url", "")
                        file_path = seg.get("data", {}).get("file", "")
                        if url:
                            data = await self._download_file(url)
                            if data and len(data) > 100:
                                return data
                        if file_path and os.path.isfile(file_path):
                            with open(file_path, "rb") as f:
                                data = f.read()
                            if len(data) > 100:
                                return data
            except Exception as e:
                logger.warning(f"aiocqhttp 获取回复消息失败: {e}")

        # ---- QQ官方接口 ----
        elif platform == "qq_official":
            try:
                from astrbot.core.platform.sources.qq_official.qq_official_message_event import (
                    QQOfficialMessageEvent,
                )
                assert isinstance(event, QQOfficialMessageEvent)
                raw = event.message_obj.raw_message
                if hasattr(raw, "attachments"):
                    for att in raw.attachments:
                        url = getattr(att, "url", None)
                        if url:
                            data = await self._download_file(url)
                            if data and len(data) > 100:
                                return data
            except Exception as e:
                logger.warning(f"qq_official 获取回复消息失败: {e}")

        # ---- Telegram ----
        elif platform == "telegram":
            try:
                from astrbot.core.platform.sources.telegram.telegram_message_event import (
                    TelegramMessageEvent,
                )
                assert isinstance(event, TelegramMessageEvent)
                raw = event.message_obj.raw_message
                reply_to = getattr(raw, "reply_to_message", None)
                if reply_to:
                    file_id = None
                    # 优先处理 document/animation（GIF/文件）
                    doc = getattr(reply_to, "document", None) or getattr(reply_to, "animation", None)
                    if doc:
                        file_id = getattr(doc, "file_id", None)
                    # 照片单独处理（photo 是列表，最后一张分辨率最高）
                    if not file_id:
                        photos = getattr(reply_to, "photo", None)
                        if photos:
                            file_id = photos[-1].file_id
                    if file_id:
                        token = self._get_telegram_token(event)
                        if token:
                            import aiohttp
                            file_url = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
                            async with aiohttp.ClientSession() as session:
                                async with session.get(file_url) as resp:
                                    if resp.status == 200:
                                        j = await resp.json()
                                        if j.get("ok"):
                                            fp = j["result"]["file_path"]
                                            dl = f"https://api.telegram.org/file/bot{token}/{fp}"
                                            data = await self._download_file(dl)
                                            if data and len(data) > 100:
                                                return data
            except Exception as e:
                logger.warning(f"telegram 获取回复消息失败: {e}")

        # ---- 未知平台: raw_message 字符串中搜索 ----
        else:
            try:
                raw_str = str(event.message_obj.raw_message)
                urls = re.findall(r"https?://[^\s)]+\.(?:gif|png|jpg|jpeg|webp|bmp)", raw_str, re.I)
                for url in urls:
                    data = await self._download_file(url)
                    if data and len(data) > 100:
                        return data
            except Exception as e:
                logger.warning(f"{platform} 获取回复消息失败: {e}")

        return None

    def _get_telegram_token(self, event: AstrMessageEvent) -> Optional[str]:
        """获取 Telegram bot token"""
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

    async def _try_get_bytes(self, comp) -> Optional[bytes]:
        """尝试从消息组件获取图像字节数据"""
        # file 属性（本地文件路径）
        if hasattr(comp, "file") and comp.file:
            fp = comp.file
            if os.path.isfile(fp):
                try:
                    with open(fp, "rb") as f:
                        data = f.read()
                    if len(data) > 100:
                        return data
                except Exception:
                    pass
            elif str(fp).startswith(("http://", "https://")):
                return await self._download_file(fp)

        # url 属性
        if hasattr(comp, "url") and comp.url:
            return await self._download_file(comp.url)

        return None

    async def _download_file(self, url: str) -> Optional[bytes]:
        """下载文件"""
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception as e:
            logger.warning(f"下载失败 {url}: {str(e)}")
        return None

    async def _send_result(self, event: AstrMessageEvent, data: bytes):
        """保存临时文件并发送结果，然后清理"""
        # 根据数据判断扩展名
        ext = ".gif" if _is_gif_data(data) else ".png"
        temp_path = self.temp_dir / f"imgtool_{id(event)}{ext}"
        with open(temp_path, "wb") as f:
            f.write(data)

        yield event.image_result(str(temp_path))

        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass

    async def terminate(self):
        """插件卸载时清理临时目录"""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass