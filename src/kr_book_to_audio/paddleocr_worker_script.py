from __future__ import annotations

PADDLEOCR_WORKER_SCRIPT = r'''#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse
import json
import os
import sys


try:
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
except (AttributeError, OSError):
    pass


def collect_strings(value):
    out = []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {'rec_texts', 'texts'} and isinstance(item, list):
                out.extend(str(text) for text in item if str(text).strip())
            elif key in {'text', 'rec_text'} and isinstance(item, str):
                out.append(item)
            else:
                out.extend(collect_strings(item))
    elif isinstance(value, (list, tuple)):
        if len(value) == 2 and isinstance(value[1], (list, tuple)) and value[1] and isinstance(value[1][0], str):
            out.append(value[1][0])
        else:
            for item in value:
                out.extend(collect_strings(item))
    else:
        maybe_json = getattr(value, 'json', None)
        if maybe_json is not None:
            try:
                decoded = json.loads(maybe_json) if isinstance(maybe_json, str) else maybe_json
                out.extend(collect_strings(decoded))
            except Exception:
                pass
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True)
    args = parser.parse_args(argv)
    request_path = Path(args.request)
    request = json.loads(request_path.read_text(encoding='utf-8'))
    image = Path(request['image'])
    output = Path(request['output'])
    run_id = str(request.get('run_id') or '').strip()
    if not run_id:
        raise RuntimeError('OCR worker request is missing run_id')
    det_name = str(request['text_detection_model_name'])
    det = Path(request['text_detection_model_dir'])
    rec_name = str(request['text_recognition_model_name'])
    rec = Path(request['text_recognition_model_dir'])
    cpu_threads = max(1, min(4, int(request.get('cpu_threads') or 2)))
    if not image.is_file():
        raise RuntimeError(f'Image is missing: {image}')
    for model in (det, rec):
        if not model.is_dir() or not any(model.iterdir()):
            raise RuntimeError(f'PaddleOCR model directory is missing or empty: {model}')
    os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
    os.environ['FLAGS_use_mkldnn'] = '0'
    from paddleocr import PaddleOCR
    engine = PaddleOCR(
        text_detection_model_name=det_name,
        text_detection_model_dir=str(det),
        text_recognition_model_name=rec_name,
        text_recognition_model_dir=str(rec),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device='cpu',
        enable_mkldnn=False,
        cpu_threads=cpu_threads,
    )
    if hasattr(engine, 'predict'):
        result = engine.predict(input=str(image))
    else:
        result = engine.ocr(str(image), cls=False)
    lines = [line.strip() for line in collect_strings(result) if str(line).strip()]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'run_id': run_id, 'text': '\n'.join(lines), 'lines': lines}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'ok': True, 'run_id': run_id, 'line_count': len(lines), 'output': str(output)}, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
'''
