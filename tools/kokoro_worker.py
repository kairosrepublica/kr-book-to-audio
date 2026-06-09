from __future__ import annotations
from pathlib import Path
import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True)
    args = parser.parse_args(argv)
    request = json.loads(Path(args.request).read_text(encoding='utf-8'))
    text = str(request['text'])
    voice = str(request['voice'])
    speed = float(request.get('speed', 1.0))
    output = Path(request['output'])
    output.parent.mkdir(parents=True, exist_ok=True)
    lang_code = 'z' if voice.startswith(('zf_', 'zm_')) else ('b' if voice.startswith(('bf_', 'bm_')) else 'a')
    repo_id = 'hexgrad/Kokoro-82M-v1.1-zh' if lang_code == 'z' else 'hexgrad/Kokoro-82M'
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
        pipeline = KPipeline(lang_code=lang_code, repo_id=repo_id)
        audio_chunks = []
        for _graphemes, _phonemes, audio in pipeline(text, voice=voice, speed=speed, split_pattern=r'\n+'):
            if audio is not None:
                audio_chunks.append(np.asarray(audio, dtype=np.float32))
        if not audio_chunks:
            raise RuntimeError('Kokoro produced no audio chunks.')
        sf.write(str(output), np.concatenate(audio_chunks), 24000, format='WAV')
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
