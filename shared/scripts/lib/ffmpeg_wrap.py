"""Thin ffmpeg wrapper that catches the -91 dB silence trap.

podcastcut 反馈记录 2026-02-02: a successful ffmpeg invocation that
emits a silent file is the most insidious failure mode. Every cut
pipeline writes goes through here; volumedetect verifies the output
has a peak above audio_constants.MIN_OUTPUT_PEAK_DB.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from . import audio_constants


@dataclass
class FFmpegError(Exception):
    cmd_args: list[str]
    returncode: int
    tail: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"ffmpeg failed (rc={self.returncode}):\n{self.tail}"


_VOLUMEDETECT_RE = re.compile(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB")


def run_ffmpeg(
    args: Sequence[str],
    *,
    log_path: Path,
    skip_volumedetect: bool = False,
) -> None:
    """Run ffmpeg; capture full stderr to log_path; verify output peak.

    The output path is assumed to be the LAST positional arg (ffmpeg convention).
    Set skip_volumedetect=True for synthesizers (sine, anullsrc) where the
    "input" is a generator and the verification step is upstream of usage.
    """
    full_args = ["ffmpeg", "-y", "-hide_banner", *args]
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        full_args,
        capture_output=True,
        text=True,
    )
    log_path.write_text(
        f"$ {' '.join(full_args)}\n\n"
        f"--- STDOUT ---\n{proc.stdout}\n"
        f"--- STDERR ---\n{proc.stderr}\n",
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise FFmpegError(
            cmd_args=list(full_args),
            returncode=proc.returncode,
            tail=_tail(proc.stderr, 20),
        )

    if skip_volumedetect:
        return
    output_path = Path(args[-1])
    peak = volumedetect_max_db(output_path)
    if peak <= audio_constants.MIN_OUTPUT_PEAK_DB:
        raise FFmpegError(
            cmd_args=list(full_args),
            returncode=0,
            tail=(
                f"silence trap: output {output_path} max_volume={peak} dB "
                f"<= {audio_constants.MIN_OUTPUT_PEAK_DB} dB"
            ),
        )


def volumedetect_max_db(path: Path) -> float:
    """Run ffmpeg volumedetect on path and return max_volume in dB."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "volumedetect",
            "-vn",
            "-sn",
            "-dn",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise FFmpegError(
            cmd_args=["ffmpeg", "volumedetect", str(path)],
            returncode=proc.returncode,
            tail=_tail(proc.stderr, 20),
        )
    match = _VOLUMEDETECT_RE.search(proc.stderr)
    if not match:
        raise FFmpegError(
            cmd_args=["ffmpeg", "volumedetect", str(path)],
            returncode=proc.returncode,
            tail="volumedetect produced no max_volume line",
        )
    return float(match.group(1))


def _tail(text: str, n_lines: int) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n_lines:])
