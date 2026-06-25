"""
AstrBot 图像工具箱 - 图像处理核心模块

功能：
1. 旋转  — 图片/GIF任意角度旋转
2. 对称  — 水平/垂直/对角线镜像翻转
3. 变速  — GIF播放速度调整
4. 万花筒 — 经典万花筒/多镜像特效
"""

import io
import math
import logging
from typing import List, Tuple, Union

from PIL import Image, ImageDraw, ImageOps

logger = logging.getLogger(__name__)


# ============================================================
#  通用工具
# ============================================================

def _open_image(data: bytes) -> Image.Image:
    """从字节数据打开图像"""
    return Image.open(io.BytesIO(data))


def _extract_gif_frames(src: Image.Image) -> Tuple[List[Image.Image], List[int], dict]:
    """
    提取GIF的所有帧、帧延时和其他信息。

    Returns:
        (frames, durations, info)
    """
    frames: List[Image.Image] = []
    durations: List[int] = []
    try:
        while True:
            frame = src.convert("RGBA")
            frames.append(frame.copy())
            durations.append(src.info.get("duration", 100))
            src.seek(src.tell() + 1)
    except EOFError:
        pass

    info = {
        "loop": src.info.get("loop", 0),
        "optimize": False,
        "disposal": 2,
    }
    return frames, durations, info


def _frames_to_gif(
    frames: List[Image.Image],
    durations: Union[List[int], int],
    loop: int = 0,
) -> bytes:
    """
    将帧列表保存为GIF字节数据。
    GIF不支持alpha通道，RGBA帧会合成到黑色背景上再转RGB。
    """
    if not frames:
        raise ValueError("没有可处理的帧")

    frames_p: List[Image.Image] = []
    for f in frames:
        if f.mode == "RGBA":
            f_rgb = Image.alpha_composite(
                Image.new("RGBA", f.size, (0, 0, 0, 255)), f
            ).convert("RGB")
        else:
            f_rgb = f.convert("RGB")
        # 量化减少颜色数以减小文件体积
        f_p = f_rgb.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        frames_p.append(f_p)

    buf = io.BytesIO()
    save_kwargs = {
        "format": "GIF",
        "save_all": True,
        "append_images": frames_p[1:],
        "duration": durations,
        "loop": loop,
        "optimize": False,
        "disposal": 2,
    }
    frames_p[0].save(buf, **save_kwargs)
    buf.seek(0)
    return buf.read()


def _is_gif_data(data: bytes) -> bool:
    """检查是否为GIF格式"""
    return data[:6] in (b"GIF87a", b"GIF89a")


# ============================================================
#  1. 旋转 (Rotation)
# ============================================================

def rotate_image(
    data: bytes,
    angle: float = 90,
    expand: bool = True,
    bg_color: Tuple[int, int, int] = (0, 0, 0),
) -> bytes:
    """
    旋转图片。

    Args:
        data: 图片二进制数据
        angle: 旋转角度（正值逆时针）
        expand: 是否放大画布以显示全部内容
        bg_color: 填充背景色 RGB

    Returns:
        处理后的图片二进制数据
    """
    img = _open_image(data)
    img_rgba = img.convert("RGBA")
    rotated = img_rgba.rotate(angle, expand=expand, fillcolor=bg_color + (0,))

    # 转回原始模式
    if img.mode == "RGBA":
        result = rotated
    elif img.mode in ("RGB", "P"):
        result = Image.alpha_composite(
            Image.new("RGBA", rotated.size, bg_color + (255,)), rotated
        ).convert("RGB")
    else:
        result = rotated.convert(img.mode)

    buf = io.BytesIO()
    save_format = "PNG" if img.mode in ("RGBA", "P") else "JPEG"
    result.save(buf, format=save_format)
    buf.seek(0)
    return buf.read()


def rotate_gif(
    data: bytes,
    angle: float = 90,
    expand: bool = True,
    bg_color: Tuple[int, int, int] = (0, 0, 0),
    max_frames: int = 100,
) -> bytes:
    """
    旋转GIF（逐帧旋转）。

    Args:
        data: GIF二进制数据
        angle: 旋转角度
        expand: 是否放大画布
        bg_color: 填充背景色
        max_frames: 最大处理帧数

    Returns:
        处理后的GIF二进制数据
    """
    src = _open_image(data)
    frames, durations, info = _extract_gif_frames(src)

    if len(frames) > max_frames:
        indices = [int(i * len(frames) / max_frames) for i in range(max_frames)]
        frames = [frames[i] for i in indices]
        durations = [durations[i] for i in indices]

    rotated_frames: List[Image.Image] = []
    for f in frames:
        rot = f.rotate(angle, expand=expand, fillcolor=bg_color + (0,))
        rotated_frames.append(rot)

    return _frames_to_gif(rotated_frames, durations, loop=info["loop"])


# ============================================================
#  2. 对称 (Mirror / Flip)
# ============================================================

def mirror_image(
    data: bytes,
    direction: str = "horizontal",
) -> bytes:
    """
    镜像/翻转图片。

    Args:
        data: 图片二进制数据
        direction:
            "horizontal" - 水平翻转（左右镜像）
            "vertical"   - 垂直翻转（上下镜像）
            "both"       - 同时水平和垂直翻转

    Returns:
        处理后的图片二进制数据
    """
    img = _open_image(data)

    if direction == "horizontal":
        flipped = ImageOps.mirror(img)
    elif direction == "vertical":
        flipped = ImageOps.flip(img)
    elif direction == "both":
        flipped = ImageOps.mirror(ImageOps.flip(img))
    else:
        raise ValueError(f"不支持的对称方向: {direction}")

    buf = io.BytesIO()
    save_format = "PNG" if img.mode in ("RGBA", "P") else "JPEG"
    flipped.save(buf, format=save_format)
    buf.seek(0)
    return buf.read()


def mirror_gif(
    data: bytes,
    direction: str = "horizontal",
    max_frames: int = 100,
) -> bytes:
    """
    镜像/翻转GIF。

    Args:
        data: GIF二进制数据
        direction: 对称方向
        max_frames: 最大处理帧数

    Returns:
        处理后的GIF二进制数据
    """
    src = _open_image(data)
    frames, durations, info = _extract_gif_frames(src)

    if len(frames) > max_frames:
        indices = [int(i * len(frames) / max_frames) for i in range(max_frames)]
        frames = [frames[i] for i in indices]
        durations = [durations[i] for i in indices]

    flipped_frames = []
    for f in frames:
        if direction == "horizontal":
            flipped = ImageOps.mirror(f)
        elif direction == "vertical":
            flipped = ImageOps.flip(f)
        elif direction == "both":
            flipped = ImageOps.mirror(ImageOps.flip(f))
        else:
            raise ValueError(f"不支持的对称方向: {direction}")
        flipped_frames.append(flipped)

    return _frames_to_gif(flipped_frames, durations, loop=info["loop"])


# ============================================================
#  3. GIF 变速 (Speed Change)
# ============================================================

def speed_change_gif(
    data: bytes,
    speed: float = 1.0,
    max_frames: int = 200,
) -> bytes:
    """
    调整GIF播放速度。

    Args:
        data: GIF二进制数据
        speed: 速度倍率（>1 加快，<1 减慢，1 不变）
               如 2.0 = 2倍速，0.5 = 半速
        max_frames: 最大处理帧数

    Returns:
        处理后的GIF二进制数据
    """
    src = _open_image(data)
    frames, durations, info = _extract_gif_frames(src)

    if speed <= 0:
        raise ValueError("速度倍率必须大于0")

    n_frames = len(frames)

    # 限制帧数
    if n_frames > max_frames:
        indices = [int(i * n_frames / max_frames) for i in range(max_frames)]
        frames = [frames[i] for i in indices]
        durations = [durations[i] for i in indices]
        n_frames = max_frames

    # 加速：调整帧延时
    new_durations = [max(10, int(d / speed)) for d in durations]

    # 如果加速幅度极大（>5x），丢帧策略保证流畅
    if speed > 5 and n_frames > 10:
        keep_every = max(1, int(speed / 3))
        frames = frames[::keep_every]
        # 补偿延时：丢掉的帧的时长累加到保留帧
        new_durations = [d * keep_every for d in durations[::keep_every]]
        new_durations = [max(10, int(d / speed)) for d in new_durations]

    # 如果减速幅度极大（<0.2x），帧间插值（重复帧 + 降低单帧延时防止超时）
    if speed < 0.2:
        repeat = max(1, int(1.0 / speed / 2))
        repeated_frames = []
        repeated_durations = []
        base_dur = max(10, int(100 / speed / repeat))
        for i in range(n_frames):
            for _ in range(repeat):
                repeated_frames.append(frames[i])
                repeated_durations.append(base_dur)
        frames = repeated_frames
        new_durations = repeated_durations

    return _frames_to_gif(frames, new_durations, loop=info["loop"])


def kaleidoscope_image(
    data: bytes,
    segments: int = 8,
    rotation: float = 0,
) -> bytes:
    """
    对图片应用三角对称万花筒效果。

    Args:
        data: 图片二进制数据
        segments: 万花筒分割数（4-24，偶数）
        rotation: 起始角度偏移（度）

    Returns:
        处理后的图片二进制数据
    """
    img = _open_image(data)
    img_rgba = img.convert("RGBA")
    result = kaleidoscope_triangle(img_rgba, segments=segments, rotation=rotation)

    # 转回原始模式
    if img.mode == "RGBA":
        output = result
    elif img.mode in ("RGB", "P"):
        output = result.convert("RGB")
    else:
        output = result.convert(img.mode)

    buf = io.BytesIO()
    save_format = "PNG" if img.mode in ("RGBA", "P") else "JPEG"
    output.save(buf, format=save_format)
    buf.seek(0)
    return buf.read()


def kaleidoscope_gif(
    data: bytes,
    segments: int = 8,
    rotation_delta: float = 0,
    max_frames: int = 60,
) -> bytes:
    """
    对GIF应用三角对称万花筒效果。
    如果设置了 rotation_delta，每帧会递增旋转角度，生成旋转动画效果。

    Args:
        data: GIF二进制数据
        segments: 万花筒分割数
        rotation_delta: 每帧增加的旋转角度（度），0=不旋转
        max_frames: 最大处理帧数

    Returns:
        处理后的GIF二进制数据
    """
    return kaleidoscope_triangle_gif(
        data,
        segments=segments,
        rotation_delta=rotation_delta,
        max_frames=max_frames,
    )


# ============================================================
#  简化版万花筒（三角对称法 — 速度更快，效果更稳定）
# ============================================================

def kaleidoscope_triangle(
    img: Image.Image,
    segments: int = 8,
    rotation: float = 0,
) -> Image.Image:
    """
    三角对称万花筒算法 —— 更经典、更稳定的万花筒效果。

    原理：
    1. 计算每个扇形的角度
    2. 将图像映射到第一个扇形区域
    3. 通过镜像循环反射填充所有扇形

    Args:
        img: 输入图像（RGBA）
        segments: 分割数（必须为偶数，4/6/8/12/16/24）
        rotation: 旋转角度偏移

    Returns:
        万花筒效果图像
    """
    w, h = img.size
    cx, cy = w / 2, h / 2
    size = max(w, h)
    radius = int(math.hypot(w - cx, h - cy)) + 10

    segments = max(4, segments)
    if segments % 2 != 0:
        segments += 1

    # 基础扇形角度
    angle_step = 360.0 / segments
    half_angle = angle_step / 2.0

    # 创建正方形画布
    canvas_size = radius * 2
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))

    # 把源图贴到画布中心
    paste_x = int((canvas_size - w) / 2)
    paste_y = int((canvas_size - h) / 2)
    canvas.paste(img, (paste_x, paste_y))

    # 以画布中心为基准旋转
    rotated = canvas.rotate(rotation, center=(canvas_size / 2, canvas_size / 2), expand=False)

    # 提取第一个扇形区域的蒙版（从中心到边缘的楔形）
    sector_mask = Image.new("L", (canvas_size, canvas_size), 0)
    draw = ImageDraw(sector_mask)
    # 以垂直向上为0度，映射第一个扇区
    start_a = 90 - half_angle  # PIL pieslice 从3点钟方向开始为0度
    end_a = 90 + half_angle
    draw.pieslice(
        [(0, 0), (canvas_size, canvas_size)],
        start=start_a, end=end_a,
        fill=255,
    )

    # 提取第一个扇形内容
    sector = Image.composite(rotated, Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0)), sector_mask)

    # 对第一个扇形做镜像（对折），使边缘自然衔接
    sector_flipped = sector.transpose(Image.FLIP_LEFT_RIGHT)
    sector_flipped = sector_flipped.rotate(
        -2 * half_angle,
        center=(canvas_size / 2, canvas_size / 2),
        expand=False,
    )
    sector = Image.composite(sector_flipped, sector, sector_mask)

    # 现在 sector 包含了一个"镜像化"的基本楔形
    # 将这个楔形旋转复制到所有 segments 个扇形位置
    result = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    for i in range(segments):
        angle = i * angle_step
        rotated_sector = sector.rotate(angle, center=(canvas_size / 2, canvas_size / 2), expand=False)

        # 创建该扇形的目标蒙版
        target_mask = Image.new("L", (canvas_size, canvas_size), 0)
        draw = ImageDraw(target_mask)
        sa = 90 - half_angle + angle
        ea = 90 + half_angle + angle
        draw.pieslice(
            [(0, 0), (canvas_size, canvas_size)],
            start=sa, end=ea,
            fill=255,
        )
        result = Image.composite(rotated_sector, result, target_mask)

    # 裁剪回原始尺寸并缩放
    crop_box = (
        int(canvas_size / 2 - w / 2),
        int(canvas_size / 2 - h / 2),
        int(canvas_size / 2 + w / 2),
        int(canvas_size / 2 + h / 2),
    )
    result = result.crop(crop_box).resize((w, h), Image.LANCZOS)
    return result


def kaleidoscope_triangle_gif(
    data: bytes,
    segments: int = 8,
    rotation_delta: float = 0,
    max_frames: int = 60,
) -> bytes:
    """
    三角对称万花筒GIF处理。

    Args:
        data: GIF二进制数据
        segments: 分割数
        rotation_delta: 每帧旋转增量
        max_frames: 最大处理帧数

    Returns:
        处理后的GIF二进制数据
    """
    src = _open_image(data)
    frames, durations, info = _extract_gif_frames(src)

    if len(frames) > max_frames:
        indices = [int(i * len(frames) / max_frames) for i in range(max_frames)]
        frames = [frames[i] for i in indices]
        durations = [durations[i] for i in indices]

    result_frames = []
    for i, f in enumerate(frames):
        rot = rotation_delta * i
        k = kaleidoscope_triangle(f, segments=segments, rotation=rot)
        result_frames.append(k)

    return _frames_to_gif(result_frames, durations, loop=info["loop"])