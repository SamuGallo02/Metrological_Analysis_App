"""Enhancing a video frame by frame.

Every frame keeps its original timestamp, so variable-frame-rate recordings (such as the
ones BlueOS Cockpit makes) stay in sync with their telemetry subtitles. Audio is copied
unchanged, except uncompressed audio going into an MP4, which is encoded to AAC.
"""

import contextlib
import os
import shutil
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction

import av

SUBTITLE_EXTENSIONS = (".ass", ".srt")


def default_output(src, model_id):
    return f"{os.path.splitext(src)[0]}_{model_id}.mp4"


def copy_subtitles(src, dst):
    """Copy a subtitle file next to the input (same name, .ass/.srt) next to the output, so players load it."""
    copied = []
    for ext in SUBTITLE_EXTENSIONS:
        sub = os.path.splitext(src)[0] + ext
        if os.path.exists(sub):
            target = os.path.splitext(dst)[0] + ext
            shutil.copyfile(sub, target)
            copied.append(target)
    return copied


def duration(src):
    """Length of a video in seconds (None if the file doesn't say)."""
    with av.open(src) as inp:
        return inp.duration / av.time_base if inp.duration else None


def read_frame(src, seconds):
    """The first frame at or after ``seconds`` as a BGR array, or None if the video is shorter."""
    with av.open(src) as inp:
        stream = inp.streams.video[0]
        inp.seek(int(seconds * av.time_base))  # lands on the keyframe before
        for frame in inp.decode(stream):
            if frame.time is not None and frame.time >= seconds - 1e-6:
                return frame.to_ndarray(format="bgr24")
    return None


def _format_duration(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m // 60}:{m % 60:02d}:{s:02d}" if m >= 60 else f"{m}:{s:02d}"


def enhance_video(src, dst, model, values, crf=18, start=0.0, duration=None, jobs=4, progress=print,
                  report=None):
    """Run ``model`` on every frame of ``src`` from ``start`` for ``duration`` seconds; returns the frame count.

    Frames are processed ``jobs`` at a time; the networks themselves still run one at a time,
    but the colour transforms around them run in parallel. ``progress`` gets a text line every
    5 seconds; ``report(done, total)`` is called after every frame (``total`` may be None), and
    can stop the work by raising: the half-written output is then removed.
    """
    with av.open(src) as inp:
        out = av.open(dst, "w")
        try:
            done = _enhance(inp, out, model, values, crf, start, duration, jobs, progress, report)
        except BaseException:
            # Closing a half-written file can fail too, and that error would hide the real one.
            with contextlib.suppress(av.FFmpegError):
                out.close()
            with contextlib.suppress(FileNotFoundError):  # not created if no frame was written
                os.remove(dst)
            raise
        out.close()
    return done


def _enhance(inp, out, model, values, crf, start, duration, jobs, progress, report):
    vin = inp.streams.video[0]
    vin.thread_type = "AUTO"
    vout = out.add_stream("libx264", rate=vin.average_rate, options={"crf": str(crf), "preset": "medium"})
    vout.width, vout.height, vout.pix_fmt = vin.width, vin.height, "yuv420p"
    vout.codec_context.time_base = vin.time_base
    audio, reencode = {}, set()
    for s in inp.streams.audio:
        # Cameras often record uncompressed (PCM) audio in .MOV files, which MP4 cannot hold
        # (ffmpeg writes it, but players cannot open the file): encode that to AAC, copy the rest.
        if s.codec_context.name.startswith("pcm_") and out.format.name != "mov":
            # Cameras may not say which channel is which; "2c" etc. is the standard layout for the count.
            audio[s.index] = out.add_stream("aac", rate=s.rate, layout=f"{s.layout.nb_channels}c")
            reencode.add(s.index)
        else:
            audio[s.index] = out.add_stream_from_template(s)

    length = inp.duration / av.time_base if inp.duration else float("inf")
    end = min(length, start + duration) if duration is not None else length
    total = round((end - start) * vin.average_rate) if end != float("inf") else None
    if start:
        inp.seek(int(start * av.time_base))
    shift = {s.index: round(start / s.time_base) for s in (vin, *inp.streams.audio)}

    pending = deque()
    done = 0
    began = last_report = time.perf_counter()

    def write_next():
        nonlocal done, last_report
        future, pts = pending.popleft()
        frame = av.VideoFrame.from_ndarray(future.result(), format="bgr24").reformat(format="yuv420p")
        frame.pts, frame.time_base = pts, vin.time_base
        out.mux(vout.encode(frame))
        done += 1
        if report:
            report(done, total)
        now = time.perf_counter()
        if now - last_report >= 5:
            last_report = now
            rate = done / (now - began)
            where = f"{done}/{total} frames ({100 * done / total:.0f}%)" if total else f"{done} frames"
            left = f", {_format_duration((total - done) / rate)} left" if total and total > done else ""
            progress(f"  {where}  {rate:.1f} frames/s{left}")

    with ThreadPoolExecutor(jobs) as pool:
        finished = False
        for packet in inp.demux(vin, *inp.streams.audio):
            if packet.stream.type == "audio":
                if packet.stream.index in reencode:
                    for sound in packet.decode():
                        if start <= sound.time < end:
                            sound.pts = round((sound.time - start) * sound.sample_rate)
                            sound.time_base = Fraction(1, sound.sample_rate)
                            out.mux(audio[packet.stream.index].encode(sound))
                elif packet.pts is not None and start <= packet.pts * packet.stream.time_base < end:
                    packet.pts -= shift[packet.stream.index]
                    packet.dts -= shift[packet.stream.index]
                    packet.stream = audio[packet.stream.index]
                    out.mux(packet)
                continue
            for frame in packet.decode():
                if frame.time < start:
                    continue  # decoded from the keyframe before the start
                if frame.time >= end:
                    finished = True
                    break
                image = frame.to_ndarray(format="bgr24")
                pending.append((pool.submit(model.run, image, values), frame.pts - shift[vin.index]))
                while len(pending) >= 2 * jobs:
                    write_next()
            if finished:
                break
        while pending:
            write_next()
    out.mux(vout.encode())
    for index in reencode:
        out.mux(audio[index].encode())
    return done
