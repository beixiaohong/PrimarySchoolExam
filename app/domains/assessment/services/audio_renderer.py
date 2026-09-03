"""音频渲染服务

用 edge-tts 为英语听写题生成音频，保存到 output/audio/ 目录。
返回相对路径（如 /output/audio/xxx.mp3），前端用 <audio> 播放。
"""
import asyncio
import uuid

from app.config import OUTPUT_DIR

# 目录锚定共享内核的 OUTPUT_DIR（= 仓库根 output/），理由同 figure_renderer：
# 迁入 app/domains/assessment/services/ 后 __file__ 深度 +1，数层数会指到 app/domains/output，
# 而 /output 静态挂载指仓库根 output/，音频会全部变成死链。
AUDIO_DIR = OUTPUT_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


async def _render_async(text: str, voice: str = "en-US-AriaNeural") -> str:
    """异步生成音频文件"""
    import edge_tts

    filename = f"{uuid.uuid4().hex[:12]}.mp3"
    filepath = AUDIO_DIR / filename
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(filepath))
    return f"/output/audio/{filename}"


def render_audio(text: str, voice: str = "en-US-AriaNeural") -> str:
    """
    同步接口：生成音频文件，返回 web 路径。
    text: 要朗读的文本（单词、词组或句子）
    voice: 发音人（默认美式女声）
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在已有事件循环中（如 FastAPI 内部），用 nest_asyncio 或新线程
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(asyncio.run, _render_async(text, voice)).result()
            return result
        else:
            return loop.run_until_complete(_render_async(text, voice))
    except RuntimeError:
        return asyncio.run(_render_async(text, voice))
    except Exception:
        return ""


def render_word_audio(word: str) -> str:
    """单词朗读"""
    return render_audio(word, "en-US-AriaNeural")


def render_sentence_audio(sentence: str) -> str:
    """句子朗读（语速稍慢）"""
    return render_audio(sentence, "en-US-GuyNeural")
