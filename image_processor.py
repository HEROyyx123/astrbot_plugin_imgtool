"""
图片/GIF 多功能处理核心模块

支持功能：
1. 旋转 — 任意角度旋转图片/GIF
2. 对称 — 水平或垂直镜像翻转
3. 变速 — 调整GIF播放速度
4. GIF往返 — GIF正序播放结束后倒序播放再拼接
5. 裸眼3D — 分层假象裸眼3D效果（移植自 astrbot_plugin_3dgif）
"""

import io
import logging
from typing import List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)


# ============================================================
#  通用工具函数
# ============================================================

def _load_gif_frames(
    data: bytes,
    max_frames: int = 0,
) -> Tuple[List[Image.Image], List[int], dict]:
    """
    从二进制数据加载GIF的所有帧、帧延和原始info。

    Returns:
        (frames, durations, info)
    """
    src = Image.open(io.BytesIO(data))
    frames: List[Image.Image] = []
    durations: List[int] = []

    try:
        while True:
            frame = src.convert("RGBA")
            frames.append(frame.copy())
            duration = src.info.get("duration", 100)
            durations.append(duration)
            src.seek(src.tell() + 1)
    except EOFError:
        pass

    n = len(frames)
    if n < 1:
        raise ValueError("无法读取图像帧")

    # 均匀采样
    if max_frames > 0 and n > max_frames:
        indices = [int(i * n / max_frames) for i in range(max_frames)]
        frames = [frames[i] for i in indices]
        durations = [durations[i] for i in indices]

    return frames, durations, src.info


def _frames_to_gif(
    frames: List[Image.Image],
    durations: List[int],
    orig_info: dict,
    loop: Optional[int] = None,
    optimize: bool = False,
) -> bytes:
    """将帧列表保存为GIF二进制数据。"""
    if not frames:
        raise ValueError("没有帧可供保存")

    # 量化
    frames_p: List[Image.Image] = []
    for f in frames:
        if f.mode == "RGBA":
            f_rgb = Image.alpha_composite(
                Image.new("RGBA", f.size, (0, 0, 0, 255)), f
            ).convert("RGB")
        else:
            f_rgb = f.convert("RGB")
        f_p = f_rgb.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        frames_p.append(f_p)

    loop_info = loop if loop is not None else orig_info.get("loop", 0)

    buf = io.BytesIO()
    save_kwargs = {
        "format": "GIF",
        "save_all": True,
        "append_images": frames_p[1:],
        "duration": durations if len(durations) > 1 else 100,
        "loop": loop_info,
        "optimize": optimize,
        "disposal": 2,
    }
    frames_p[0].save(buf, **save_kwargs)
    buf.seek(0)
    return buf.read()


def _is_gif_data(data: bytes) -> bool:
    """检查字节数据是否为GIF格式。"""
    return data[:6] in (b"GIF87a", b"GIF89a")


def _ensure_image_mode(img: Image.Image, mode: str = "RGBA") -> Image.Image:
    """确保图片处于指定模式。"""
    if img.mode != mode:
        return img.convert(mode)
    return img


def _process_gif_frames(
    data: bytes,
    processor_fn,
    max_frames: int = 0,
    **kwargs,
) -> bytes:
    """
    通用GIF逐帧处理函数。

    Args:
        data: GIF 二进制数据
        processor_fn: 处理单帧的 callback: fn(frame: RGBA Image, **kwargs) -> RGBA Image
        max_frames: 最大帧数，0 表示不限制
        **kwargs: 传递给 processor_fn 的额外参数

    Returns:
        处理后的GIF二进制数据
    """
    frames, durations, info = _load_gif_frames(data, max_frames=max_frames)
    processed = [processor_fn(f, **kwargs) for f in frames]
    return _frames_to_gif(processed, durations, info)


def _process_single_frame_or_gif(data: bytes, processor_fn, **kwargs) -> bytes:
    """
    通用处理入口：自动判断是静态PNG/JPG还是GIF，分别处理。

    Args:
        data: 图像二进制数据
        processor_fn: 单帧处理函数 fn(frame: RGBA Image, **kwargs) -> RGBA Image
        **kwargs: 额外参数

    Returns:
        处理后的图像二进制数据
    """
    if _is_gif_data(data):
        return _process_gif_frames(data, processor_fn, **kwargs)
    # 处理静态图片
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    result = processor_fn(img, **kwargs)
    # 保存为 PNG（保持透明度）
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


# ============================================================
#  1. 旋转 (Rotate)
# ============================================================

def _rotate_frame(frame: Image.Image, angle: float = 90) -> Image.Image:
    """旋转单帧。"""
    return frame.rotate(angle, expand=True, resample=Image.BICUBIC)


def rotate_image(
    data: bytes,
    angle: float = 90,
) -> bytes:
    """
    旋转图片/GIF。

    Args:
        data: 图像二进制数据
        angle: 旋转角度（度），正数=逆时针，负数=顺时针

    Returns:
        处理后的图像二进制数据
    """
    return _process_single_frame_or_gif(data, _rotate_frame, angle=angle)


# ============================================================
#  2. 轴对称 (Symmetry) — 取图像一半对称填补另一半
#    上对称: 保留上半部 → 镜像到下半部
#    下对称: 保留下半部 → 镜像到上半部
#    左对称: 保留左半部 → 镜像到右半部
#    右对称: 保留右半部 → 镜像到左半部
# ============================================================

def _symmetry_frame(frame: Image.Image, direction: str = "top") -> Image.Image:
    """轴对称单帧。"""
    w, h = frame.size
    frame_rgba = frame.convert("RGBA")
    result = Image.new("RGBA", (w, h))

    if direction == "top":
        # 取上半部，垂直翻转后补到下半部
        half_h = h // 2
        top_half = frame_rgba.crop((0, 0, w, half_h))
        mirrored = top_half.transpose(Image.FLIP_TOP_BOTTOM)
        result.paste(frame_rgba.crop((0, 0, w, half_h)), (0, 0))
        result.paste(mirrored, (0, half_h))

    elif direction == "bottom":
        # 取下半部，垂直翻转后补到上半部
        half_h = h // 2
        bottom_half = frame_rgba.crop((0, half_h, w, h))
        mirrored = bottom_half.transpose(Image.FLIP_TOP_BOTTOM)
        result.paste(mirrored, (0, 0))
        result.paste(frame_rgba.crop((0, half_h, w, h)), (0, half_h))

    elif direction == "left":
        # 取左半部，水平翻转后补到右半部
        half_w = w // 2
        left_half = frame_rgba.crop((0, 0, half_w, h))
        mirrored = left_half.transpose(Image.FLIP_LEFT_RIGHT)
        result.paste(frame_rgba.crop((0, 0, half_w, h)), (0, 0))
        result.paste(mirrored, (half_w, 0))

    elif direction == "right":
        # 取右半部，水平翻转后补到左半部
        half_w = w // 2
        right_half = frame_rgba.crop((half_w, 0, w, h))
        mirrored = right_half.transpose(Image.FLIP_LEFT_RIGHT)
        result.paste(mirrored, (0, 0))
        result.paste(frame_rgba.crop((half_w, 0, w, h)), (half_w, 0))

    else:
        raise ValueError(f"不支持的对称方向: {direction}，可选: top/bottom/left/right")

    return result


def symmetry_image(
    data: bytes,
    direction: str = "top",
) -> bytes:
    """
    将图片/GIF进行轴对称（取一半对称到另一半）。

    Args:
        data: 图像二进制数据
        direction: "top" 上对称 / "bottom" 下对称 / "left" 左对称 / "right" 右对称

    Returns:
        处理后的图像二进制数据
    """
    return _process_single_frame_or_gif(data, _symmetry_frame, direction=direction)


# ============================================================
#  3. 翻转 (Mirror/Flip) — 整体镜像翻转，保留原功能
# ============================================================

def _flip_frame(frame: Image.Image, direction: str = "horizontal") -> Image.Image:
    """翻转单帧。"""
    if direction == "horizontal":
        return frame.transpose(Image.FLIP_LEFT_RIGHT)
    elif direction == "vertical":
        return frame.transpose(Image.FLIP_TOP_BOTTOM)
    else:
        raise ValueError(f"不支持的翻转方向: {direction}")


def flip_image(
    data: bytes,
    direction: str = "horizontal",
) -> bytes:
    """
    将图片/GIF进行整体翻转（镜像）。

    Args:
        data: 图像二进制数据
        direction: "horizontal" 水平翻转 / "vertical" 垂直翻转

    Returns:
        处理后的图像二进制数据
    """
    return _process_single_frame_or_gif(data, _flip_frame, direction=direction)


# ============================================================
#  4. 变速 (Speed change)
# ============================================================

def speed_change(
    data: bytes,
    speed: float = 1.0,
) -> bytes:
    """
    调整GIF播放速度。
    速度因子 > 1 加速，< 1 减速。

    Args:
        data: GIF 二进制数据
        speed: 速度因子。0.5=半速（慢一倍），2.0=倍速（快一倍）

    Returns:
        处理后的GIF二进制数据
    """
    if not _is_gif_data(data):
        # 静态图片无法变速，直接返回
        return data

    frames, durations, info = _load_gif_frames(data)
    # 调整每帧延迟（至少 20ms）
    new_durations = [max(20, int(d / speed)) for d in durations]
    # 如果总的帧时长太短或太长，也保持合理范围
    return _frames_to_gif(frames, new_durations, info)


# ============================================================
#  5. GIF往返 (Roundtrip) — 正序+倒序拼接
# ============================================================

def gif_roundtrip(
    data: bytes,
) -> bytes:
    """
    GIF往返效果：正序播放结束后倒序播放，然后拼接起来。
    效果类似"正向播放→倒放→正向播放→倒放…"的循环。

    Args:
        data: GIF 二进制数据

    Returns:
        处理后的GIF二进制数据（帧数翻倍）
    """
    if not _is_gif_data(data):
        # 静态图片不支持往返，直接返回
        return data

    frames, durations, info = _load_gif_frames(data)

    if len(frames) <= 1:
        return _frames_to_gif(frames, durations, info)

    # 正序帧 + 倒序帧（去掉首尾各1帧以避免重复）
    reversed_frames = frames[-2:0:-1]  # 去掉第一帧和最后一帧
    reversed_durations = durations[-2:0:-1]

    combined_frames = frames + reversed_frames
    combined_durations = durations + reversed_durations

    return _frames_to_gif(combined_frames, combined_durations, info)


# ============================================================
#  6. 裸眼3D (Bare-eye 3D) — 移植自 astrbot_plugin_3dgif
# ============================================================

def compute_background(frames: List[Image.Image]) -> Image.Image:
    """
    从多帧计算静态背景（中位数合成）。
    """
    import numpy as np
    w, h = frames[0].size
    frames_arr = np.stack([np.array(f.convert("RGBA")) for f in frames], axis=0)
    bg_arr = np.median(frames_arr, axis=0).astype(np.uint8)
    return Image.fromarray(bg_arr, "RGBA")


def draw_dividing_lines(
    img: Image.Image,
    spacing: int = 80,
    line_width: int = 3,
    color: Tuple[int, int, int] = (255, 255, 255),
    line_alpha: int = 200,
    direction: str = "both",
) -> Image.Image:
    """在图像上画分割白线。"""
    if img.mode == "RGBA":
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        w, h = img.size
        line_color_rgba = color + (line_alpha,)

        if direction in ("horizontal", "both"):
            y = spacing if spacing > 0 else h // 4
            while y < h:
                draw.line([(0, y), (w, y)], fill=line_color_rgba, width=line_width)
                y += spacing
        if direction in ("vertical", "both"):
            x = spacing if spacing > 0 else w // 4
            while x < w:
                draw.line([(x, 0), (x, h)], fill=line_color_rgba, width=line_width)
                x += spacing
        return Image.alpha_composite(img, overlay)
    else:
        result = img.copy()
        draw = ImageDraw.Draw(result)
        w, h = img.size
        line_color_rgb = color + (255,) if len(color) == 3 else color
        if direction in ("horizontal", "both"):
            y = spacing if spacing > 0 else h // 4
            while y < h:
                draw.line([(0, y), (w, y)], fill=line_color_rgb, width=line_width)
                y += spacing
        if direction in ("vertical", "both"):
            x = spacing if spacing > 0 else w // 4
            while x < w:
                draw.line([(x, 0), (x, h)], fill=line_color_rgb, width=line_width)
                x += spacing
        return result


def extract_foreground_mask(
    frame: Image.Image,
    background: Image.Image,
    threshold: int = 25,
    blur_radius: int = 7,
) -> Image.Image:
    """通过帧差法提取前景蒙版。"""
    frame_gray = frame.convert("L")
    bg_gray = background.convert("L")
    diff = ImageChops.difference(frame_gray, bg_gray)
    mask = diff.point(lambda p: 255 if p > threshold else 0)
    if blur_radius > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    mask = mask.point(lambda p: 255 if p > 50 else 0)
    mask = mask.filter(ImageFilter.MinFilter(3))
    mask = mask.filter(ImageFilter.MaxFilter(3))
    return mask


def create_3d_frame(
    frame: Image.Image,
    background: Image.Image,
    line_spacing: int = 80,
    line_width: int = 3,
    line_color: Tuple[int, int, int] = (255, 255, 255),
    line_alpha: int = 200,
    line_direction: str = "both",
    mask_threshold: int = 25,
    mask_blur: int = 7,
    foreground_blur: int = 0,
) -> Image.Image:
    """创建单帧裸眼3D效果。"""
    frame_rgba = frame.convert("RGBA")
    bg_rgba = background.convert("RGBA")

    bg_with_lines = draw_dividing_lines(
        bg_rgba, spacing=line_spacing, line_width=line_width,
        color=line_color, line_alpha=line_alpha, direction=line_direction,
    )

    mask = extract_foreground_mask(
        frame_rgba, bg_rgba, threshold=mask_threshold, blur_radius=mask_blur,
    )

    foreground = frame_rgba
    if foreground_blur > 0:
        foreground = foreground.filter(ImageFilter.GaussianBlur(radius=foreground_blur))

    return Image.composite(foreground, bg_with_lines, mask)


def bare_eye_3d(
    data: bytes,
    line_spacing: int = 80,
    line_width: int = 3,
    line_color: tuple = (255, 255, 255),
    line_alpha: int = 200,
    line_direction: str = "both",
    mask_threshold: int = 25,
    mask_blur: int = 7,
    foreground_blur: int = 0,
    max_frames: int = 48,
    loop: Optional[int] = None,
) -> bytes:
    """
    将GIF转换为裸眼3D效果（分层假象法）。

    Args:
        data: GIF二进制数据
        line_spacing: 分割白线间距
        line_width: 分割白线宽度
        line_color: 线条颜色 RGB
        line_alpha: 线条透明度
        line_direction: 线条方向
        mask_threshold: 前景检测阈值
        mask_blur: 前景蒙版模糊半径
        foreground_blur: 前景高斯模糊
        max_frames: 最大处理帧数
        loop: GIF循环次数

    Returns:
        处理后的GIF二进制数据
    """
    if not _is_gif_data(data):
        # 静态图片直接画线
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        result = draw_dividing_lines(
            img, spacing=line_spacing, line_width=line_width,
            color=line_color, line_alpha=line_alpha, direction=line_direction,
        )
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        buf.seek(0)
        return buf.read()

    # 加载GIF帧
    frames, durations, info = _load_gif_frames(data, max_frames=max_frames)

    if len(frames) == 1:
        # 单帧GIF = 静态图，直接画线
        result = draw_dividing_lines(
            frames[0], spacing=line_spacing, line_width=line_width,
            color=line_color, line_alpha=line_alpha, direction=line_direction,
        )
        result_frames = [result]
    else:
        # 计算静态背景
        background = compute_background(frames)
        result_frames = []
        for i, frame in enumerate(frames):
            syn = create_3d_frame(
                frame, background,
                line_spacing=line_spacing, line_width=line_width,
                line_color=line_color, line_alpha=line_alpha,
                line_direction=line_direction,
                mask_threshold=mask_threshold, mask_blur=mask_blur,
                foreground_blur=foreground_blur,
            )
            result_frames.append(syn)

    return _frames_to_gif(result_frames, durations, info, loop=loop)


# ============================================================
#  7. 高级组合效果
# ============================================================

def apply_fx_pipeline(
    data: bytes,
    rotate_angle: Optional[float] = None,
    mirror_direction: Optional[str] = None,
    speed: Optional[float] = None,
    **bare_eye_3d_kwargs,
) -> bytes:
    """
    按顺序应用多重效果（管道模式）。

    效果顺序：旋转 → 对称 → 变速 → 裸眼3D
    注意：裸眼3D会覆盖前面的视觉效果，推荐单独使用。
    """
    result = data

    if rotate_angle is not None:
        result = _process_gif_frames(result, _rotate_frame, angle=rotate_angle)

    if mirror_direction is not None:
        result = _process_gif_frames(result, _symmetry_frame, direction=mirror_direction)

    if speed is not None:
        result = speed_change(result, speed=speed)

    if bare_eye_3d_kwargs:
        result = bare_eye_3d(result, **bare_eye_3d_kwargs)

    return result