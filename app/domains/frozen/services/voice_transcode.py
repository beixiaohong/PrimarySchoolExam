"""IM 语音消息转码：统一转 MP3（D6 决策）。

背景
----
前端 `MediaRecorder` 在各浏览器产物不一致：Chrome/Edge/Firefox 产出 `audio/webm`，
Safari 产出 `audio/mp4`。原样存储会带来跨端播放兼容问题与时长解析差异，
故由后端统一转码为标准 MP3（单声道 44.1kHz / 64kbps），前端 `<audio>` 通用可播。

🚨 项目红线（务必遵守）
----------------------
ffmpeg / ffprobe 是**外部阻塞调用**，绝不允许在持有 DB 会话期间执行
（历史教训：持连做外部调用导致连接池耗尽、全站卡死，见提交 267c32c）。
调用方必须按「分段短会话」模式：先落盘 → 关闭会话 → 转码 → 再开短会话回填。
本模块自身只做文件处理，不接触 Session。

降级策略
--------
ffmpeg 未安装 / 超时 / 转码失败 → 抛 `TranscodeError`，由调用方按原格式保存，
语音消息仍可正常发送与播放（`<audio>` 原生支持 webm/mp4），功能不中断。
"""
import logging
import os
import shutil
import subprocess
import uuid

from app.config import FFMPEG_PATH, FFPROBE_PATH, FFMPEG_TIMEOUT

logger = logging.getLogger(__name__)

# 允许的音频入参类型（上传白名单用；转码后统一为 audio/mpeg）
AUDIO_MIME_TYPES = {
    "audio/webm", "audio/mp4", "audio/mpeg", "audio/ogg",
    "audio/wav", "audio/x-wav", "audio/x-m4a", "audio/aac",
}
# 音频大小上限（转码前）：60s 的 webm 通常 < 1MB，留一倍余量
MAX_AUDIO_SIZE = 2 * 1024 * 1024


class TranscodeError(Exception):
    """转码不可用或失败（调用方应降级为原样保存）。"""


def is_audio(mime: str) -> bool:
    return (mime or "").split(";")[0].strip().lower() in AUDIO_MIME_TYPES


def _probe_duration(path: str):
    """用 ffprobe 读取音频时长（秒，float）。失败返回 None，不抛异常。"""
    try:
        out = subprocess.run(
            [FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
        )
        if out.returncode == 0 and out.stdout.strip():
            return float(out.stdout.strip())
    except FileNotFoundError:
        raise TranscodeError("ffprobe 未安装")
    except (subprocess.TimeoutExpired, ValueError, OSError) as e:
        logger.warning("[voice] ffprobe 读取时长失败: %s", e)
    return None


def transcode_to_mp3(src_path: str, upload_root: str):
    """把音频文件转码为 MP3，返回 (mp3_path, duration_sec|None)。

    转码失败一律抛 `TranscodeError`；源文件**不删除**，由调用方决定降级或清理。
    """
    if shutil.which(FFMPEG_PATH) is None:
        raise TranscodeError(f"ffmpeg 未安装（FFMPEG_PATH={FFMPEG_PATH}）")

    dst_name = f"{uuid.uuid4()}.mp3"
    dst_path = os.path.join(upload_root, dst_name)
    cmd = [
        FFMPEG_PATH, "-y", "-i", src_path,
        "-vn",                 # 丢弃可能存在的封面流
        "-ac", "1",            # 单声道（语音无需立体声，省一半体积）
        "-ar", "44100",
        "-b:a", "64k",
        "-f", "mp3",
        dst_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise TranscodeError("ffmpeg 转码超时")
    except FileNotFoundError:
        raise TranscodeError("ffmpeg 未安装")

    if proc.returncode != 0 or not os.path.exists(dst_path):
        raise TranscodeError(f"ffmpeg 转码失败: {(proc.stderr or '')[:200]}")

    # 清理原始文件（转码成功后 webm/mp4 无保留价值）
    try:
        os.remove(src_path)
    except OSError:
        pass

    return dst_path, _probe_duration(dst_path)
