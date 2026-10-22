"""Prepare local evidence; never transcribe, interpret, or upload media."""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys


def sample_times(duration, count):
    if not math.isfinite(duration) or duration <= 0 or not 2 <= count <= 48:
        raise ValueError('Positive duration and 2–48 frames required')
    end = max(0, duration - min(0.1, duration / 10))
    return sorted(set(round(i * end / (count - 1), 6) for i in range(count)))


def parse_times(value, duration):
    times = []
    for item in value.split(','):
        parts = item.strip().split(':')
        if len(parts) not in (1, 2, 3) or any(not p for p in parts):
            raise ValueError('Use seconds, MM:SS, or HH:MM:SS')
        nums = [float(p) for p in parts]
        if any(not math.isfinite(n) or n < 0 for n in nums):
            raise ValueError('Timestamps must be finite and nonnegative')
        if len(nums) > 1 and (any(n >= 60 for n in nums[1:]) or any(not n.is_integer() for n in nums[:-1])):
            raise ValueError('Invalid clock timestamp')
        seconds = sum(n * 60 ** i for i, n in enumerate(reversed(nums)))
        if seconds >= duration:
            raise ValueError('Timestamp must be before the end of the clip')
        times.append(seconds)
    if len(times) > 48:
        raise ValueError('At most 48 timestamps per run')
    return sorted(set(times))


def new_output(path):
    path.mkdir(parents=True, exist_ok=False)


def run(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:] or 'Media command failed')
    return result.stdout


def prepare(source, output, frames=12, at=None, audio=False):
    source = source.resolve(strict=True)
    if not source.is_file():
        raise ValueError('Input must be a local file')
    for tool in ('ffprobe', 'ffmpeg'):
        if not shutil.which(tool):
            raise RuntimeError(f'{tool} is required; install FFmpeg first')
    info = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(source)]))
    duration = float(info.get('format', {}).get('duration', 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Cannot determine a positive media duration')
    streams = info.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')), None)
    sound = next((s for s in streams if s.get('codec_type') == 'audio'), None)
    if not video and not sound:
        raise ValueError('No usable video or audio stream')
    if at and not video:
        raise ValueError('--at requires a video stream')
    times = (parse_times(at, duration) if at else sample_times(duration, frames)) if video else []
    if audio and (not sound or duration > 1800):
        raise ValueError('Audio extraction requires an audio stream and a clip no longer than 30 minutes; trim longer clips first')
    new_output(output)
    manifest = {'duration_seconds': duration, 'video': bool(video), 'audio_present': bool(sound), 'frames': [], 'audio_file': None, 'interpretation': 'Not analyzed. Sampled frames do not establish events between timestamps.'}
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    for index, timestamp in enumerate(times):
        name = f'frame-{index:03d}-{timestamp:.3f}s.jpg'
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n', '-ss', str(timestamp), '-i', str(source), '-map', f'0:{video["index"]}', '-frames:v', '1', '-vf', 'scale=1280:1280:force_original_aspect_ratio=decrease', '-q:v', '2', str(output/name)])
        if not (output/name).is_file():
            raise RuntimeError(f'No frame decoded at {timestamp:.3f}s; try an earlier timestamp')
        manifest['frames'].append({'seconds': timestamp, 'file': name})
        (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    if audio:
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n', '-i', str(source), '-map', f'0:{sound["index"]}', '-vn', '-ac', '1', '-ar', '16000', str(output/'audio.wav')])
        manifest['audio_file'] = 'audio.wav'
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--out', type=Path, required=True, help='A NEW local directory; existing directories are rejected')
    parser.add_argument('--frames', type=int, default=12, help='2–48 overview frames (default 12)')
    parser.add_argument('--at', help='Targeted timestamps, e.g. 2.5,00:03,00:06.2; replaces overview sampling')
    parser.add_argument('--audio', action='store_true', help='Also extract a mono WAV locally; does not transcribe')
    args = parser.parse_args()
    try:
        manifest = prepare(args.input, args.out, args.frames, args.at, args.audio)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    print(json.dumps({'output': str(args.out.resolve()), 'frames': len(manifest['frames']), 'audio_file': manifest['audio_file']}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
