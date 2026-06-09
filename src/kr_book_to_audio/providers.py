from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Iterable
import asyncio
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
from .subprocess_utils import run_hidden_cli

ProviderProgressCallback = Callable[[dict[str, object]], None]
EDGE_NO_AUDIO_TIMEOUT_SECONDS = float(os.environ.get('KR_B2A_EDGE_NO_AUDIO_TIMEOUT_SECONDS', '120'))
EDGE_TOTAL_PART_TIMEOUT_SECONDS = float(os.environ.get('KR_B2A_EDGE_TOTAL_PART_TIMEOUT_SECONDS', '720'))


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    kind: str
    label: str
    transport: str
    status: str
    enabled: bool
    credential_env: str | None = None
    endpoint_env: str | None = None
    notes: str = ''

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProviderUnavailable(RuntimeError):
    pass


class ProviderStalled(RuntimeError):
    pass


class ProviderTimedOut(RuntimeError):
    pass


class ExternalAPIContract:
    """Reserved extension contract for future remote providers.

    Implementations must read credentials from environment variables or an
    Owner-local secret store. API keys must never be persisted in job manifests,
    public configuration, logs or GitHub payloads.
    """
    spec: ProviderSpec

    def assert_configured(self) -> None:
        if not self.spec.enabled:
            raise ProviderUnavailable(f'{self.spec.label} is reserved but not enabled in this release.')
        if self.spec.credential_env and not os.environ.get(self.spec.credential_env):
            raise ProviderUnavailable(f'Missing required Owner-local credential: {self.spec.credential_env}')


def _emit(progress: ProviderProgressCallback | None, **payload: object) -> None:
    if progress:
        progress(payload)


class TTSProvider:
    spec: ProviderSpec

    def list_voices(self) -> list[dict[str, str]]:
        raise NotImplementedError

    def synthesize(
        self,
        text: str,
        out_path: Path,
        *,
        voice: str,
        rate: str,
        pitch: str,
        volume: str,
        progress: ProviderProgressCallback | None = None,
    ) -> None:
        raise NotImplementedError


class EdgeTTSProvider(TTSProvider):
    spec = ProviderSpec(
        provider_id='edge-tts',
        kind='tts',
        label='Microsoft Edge Online TTS · edge-tts',
        transport='online-no-api-key',
        status='enabled',
        enabled=True,
        notes='Default online provider. Streams audio bytes with product-level stall and total-Part watchdogs.',
    )

    def list_voices(self) -> list[dict[str, str]]:
        try:
            import edge_tts
        except ImportError as exc:
            raise ProviderUnavailable('edge-tts is not installed. Run: pip install -U edge-tts') from exc
        voices = asyncio.run(edge_tts.list_voices())
        normalized = []
        for voice in voices:
            short = str(voice.get('ShortName', '')).strip()
            if not short:
                continue
            normalized.append({
                'short_name': short,
                'locale': str(voice.get('Locale', '')),
                'gender': str(voice.get('Gender', '')),
                'friendly_name': str(voice.get('FriendlyName', short)),
            })
        return sorted(normalized, key=lambda item: (item['locale'], item['short_name']))

    async def _stream_to_file(
        self,
        text: str,
        out_path: Path,
        *,
        voice: str,
        rate: str,
        pitch: str,
        volume: str,
        progress: ProviderProgressCallback | None,
        no_audio_timeout_seconds: float,
        total_timeout_seconds: float,
    ) -> None:
        try:
            import edge_tts
        except ImportError as exc:
            raise ProviderUnavailable('edge-tts is not installed. Run: pip install -U edge-tts') from exc
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        last_audio = started
        bytes_received = 0
        _emit(progress, provider_id=self.spec.provider_id, stage='connecting', elapsed_seconds=0.0, bytes_received=0, last_audio_seconds_ago=0.0)
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
        iterator = communicate.stream().__aiter__()
        try:
            with out_path.open('wb') as handle:
                while True:
                    now = time.monotonic()
                    elapsed = now - started
                    remaining_total = total_timeout_seconds - elapsed
                    if remaining_total <= 0:
                        raise ProviderTimedOut(
                            f'Edge Online TTS exceeded the total Part timeout of {int(total_timeout_seconds)} seconds. '
                            'Possible causes: slow or unstable network, provider-side throttling, or an unusually slow remote response.'
                        )
                    wait_seconds = min(no_audio_timeout_seconds, remaining_total)
                    try:
                        message = await asyncio.wait_for(iterator.__anext__(), timeout=wait_seconds)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError as exc:
                        stalled_for = time.monotonic() - last_audio
                        if time.monotonic() - started >= total_timeout_seconds:
                            raise ProviderTimedOut(
                                f'Edge Online TTS exceeded the total Part timeout of {int(total_timeout_seconds)} seconds.'
                            ) from exc
                        raise ProviderStalled(
                            f'Edge Online TTS received no audio bytes for {int(stalled_for)} seconds. '
                            'Possible causes: slow or unstable network, provider connection failure, or provider-side throttling.'
                        ) from exc
                    now = time.monotonic()
                    elapsed = now - started
                    message_type = str(message.get('type') or '').lower() if isinstance(message, dict) else ''
                    data = message.get('data') if isinstance(message, dict) else None
                    if message_type == 'audio' and isinstance(data, (bytes, bytearray)) and data:
                        handle.write(bytes(data))
                        bytes_received += len(data)
                        last_audio = now
                        _emit(
                            progress,
                            provider_id=self.spec.provider_id,
                            stage='receiving-audio',
                            elapsed_seconds=round(elapsed, 3),
                            bytes_received=bytes_received,
                            last_audio_seconds_ago=0.0,
                        )
                    else:
                        stalled_for = now - last_audio
                        _emit(
                            progress,
                            provider_id=self.spec.provider_id,
                            stage='waiting-for-audio',
                            elapsed_seconds=round(elapsed, 3),
                            bytes_received=bytes_received,
                            last_audio_seconds_ago=round(stalled_for, 3),
                        )
                        if stalled_for >= no_audio_timeout_seconds:
                            raise ProviderStalled(
                                f'Edge Online TTS received no audio bytes for {int(stalled_for)} seconds. '
                                'Possible causes: slow or unstable network, provider connection failure, or provider-side throttling.'
                            )
            if bytes_received <= 0:
                raise ProviderStalled('Edge Online TTS completed without returning audio bytes.')
            _emit(
                progress,
                provider_id=self.spec.provider_id,
                stage='provider-completed',
                elapsed_seconds=round(time.monotonic() - started, 3),
                bytes_received=bytes_received,
                last_audio_seconds_ago=round(time.monotonic() - last_audio, 3),
            )
        except Exception:
            out_path.unlink(missing_ok=True)
            raise

    def synthesize(
        self,
        text: str,
        out_path: Path,
        *,
        voice: str,
        rate: str,
        pitch: str,
        volume: str,
        progress: ProviderProgressCallback | None = None,
        no_audio_timeout_seconds: float | None = None,
        total_timeout_seconds: float | None = None,
    ) -> None:
        asyncio.run(self._stream_to_file(
            text,
            out_path,
            voice=voice,
            rate=rate,
            pitch=pitch,
            volume=volume,
            progress=progress,
            no_audio_timeout_seconds=float(no_audio_timeout_seconds or EDGE_NO_AUDIO_TIMEOUT_SECONDS),
            total_timeout_seconds=float(total_timeout_seconds or EDGE_TOTAL_PART_TIMEOUT_SECONDS),
        ))


class KokoroLocalProvider(TTSProvider):
    spec = ProviderSpec(
        provider_id='kokoro-local',
        kind='tts',
        label='Kokoro Local TTS · offline fallback',
        transport='local-process',
        status='enabled-when-installed',
        enabled=True,
        notes='Offline fallback. Install the Owner-local runtime with tools/setup_local_tts_foundation.py.',
    )

    @staticmethod
    def _foundation():
        from .local_tts import kokoro_foundation
        return kokoro_foundation()

    def list_voices(self) -> list[dict[str, str]]:
        from .local_tts import KOKORO_VOICES
        return [dict(item) for item in KOKORO_VOICES]

    def synthesize(
        self,
        text: str,
        out_path: Path,
        *,
        voice: str,
        rate: str,
        pitch: str,
        volume: str,
        progress: ProviderProgressCallback | None = None,
    ) -> None:
        from .local_tts import kokoro_speed_from_rate
        foundation = self._foundation()
        foundation.assert_ready()
        if pitch != '+0Hz':
            raise ProviderUnavailable('Kokoro Local currently supports the default Pitch +0Hz only.')
        if volume != '+0%':
            raise ProviderUnavailable('Kokoro Local currently supports the default Volume +0% only.')
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        _emit(progress, provider_id=self.spec.provider_id, stage='local-worker-started', elapsed_seconds=0.0, bytes_received=0, last_audio_seconds_ago=0.0)
        if not shutil.which('ffmpeg'):
            raise ProviderUnavailable('Kokoro Local requires FFmpeg on PATH to encode MP3 output.')
        with tempfile.TemporaryDirectory(prefix='kr-b2a-kokoro-request-') as temp_dir:
            wav_path = Path(temp_dir) / 'worker-output.wav'
            request = {
                'text': text,
                'voice': voice,
                'speed': kokoro_speed_from_rate(rate),
                'output': str(wav_path),
            }
            request_path = Path(temp_dir) / 'request.json'
            request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            result = run_hidden_cli(
                [str(foundation.python), str(foundation.worker), '--request', str(request_path)],
                capture_output=True,
                text=True,
                check=False,
                env=foundation.worker_env(),
                timeout=float(os.environ.get('KR_B2A_KOKORO_TOTAL_TIMEOUT_SECONDS', '1800')),
            )
            if result.returncode != 0:
                out_path.unlink(missing_ok=True)
                detail = (result.stderr or result.stdout or '').strip()
                raise ProviderUnavailable(f'Kokoro Local worker failed: {detail or "unknown error"}')
            if not wav_path.exists() or wav_path.stat().st_size <= 0:
                raise ProviderUnavailable('Kokoro Local worker completed without writing WAV output.')
            encoded = run_hidden_cli(
                ['ffmpeg', '-y', '-v', 'error', '-i', str(wav_path), '-codec:a', 'libmp3lame', '-q:a', '2', str(out_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if encoded.returncode != 0:
                out_path.unlink(missing_ok=True)
                raise ProviderUnavailable(f'Kokoro Local FFmpeg MP3 encoding failed: {(encoded.stderr or encoded.stdout or "").strip()}')
        if not out_path.exists() or out_path.stat().st_size <= 0:
            raise ProviderUnavailable('Kokoro Local MP3 encoding completed without writing audio output.')
        _emit(
            progress,
            provider_id=self.spec.provider_id,
            stage='local-worker-completed',
            elapsed_seconds=round(time.monotonic() - started, 3),
            bytes_received=int(out_path.stat().st_size),
            last_audio_seconds_ago=0.0,
        )


class ReservedTTSAPIProvider(ExternalAPIContract, TTSProvider):
    def __init__(self, spec: ProviderSpec):
        self.spec = spec

    def list_voices(self) -> list[dict[str, str]]:
        self.assert_configured()
        raise ProviderUnavailable(f'{self.spec.label} adapter is reserved but not implemented.')

    def synthesize(self, text: str, out_path: Path, *, voice: str, rate: str, pitch: str, volume: str, progress: ProviderProgressCallback | None = None) -> None:
        self.assert_configured()
        raise ProviderUnavailable(f'{self.spec.label} adapter is reserved but not implemented.')


TTS_PROVIDER_SPECS: dict[str, ProviderSpec] = {
    'edge-tts': EdgeTTSProvider.spec,
    'kokoro-local': KokoroLocalProvider.spec,
    'qwen3-tts-local': ProviderSpec('qwen3-tts-local', 'tts', 'Qwen3-TTS Local benchmark', 'local-process', 'benchmark-foundation', False, None, None, 'Downloaded as a high-quality benchmark foundation; not an operational v2.4.0 provider.'),
    'azure-speech-api': ProviderSpec('azure-speech-api', 'tts', 'Azure Speech API', 'external-api', 'reserved', False, 'AZURE_SPEECH_KEY', 'AZURE_SPEECH_ENDPOINT', 'Reserved API adapter slot.'),
    'openai-tts-api': ProviderSpec('openai-tts-api', 'tts', 'OpenAI TTS API', 'external-api', 'reserved', False, 'OPENAI_API_KEY', None, 'Reserved API adapter slot.'),
    'custom-http-tts-api': ProviderSpec('custom-http-tts-api', 'tts', 'Custom HTTP TTS API', 'external-api', 'reserved', False, 'KR_B2A_TTS_API_KEY', 'KR_B2A_TTS_API_ENDPOINT', 'Reserved generic API adapter slot.'),
    'piper-local': ProviderSpec('piper-local', 'tts', 'Piper local TTS', 'local-process', 'reserved', False, None, None, 'Reserved lightweight offline adapter slot.'),
}


def get_tts_provider(provider_id: str = 'edge-tts') -> TTSProvider:
    if provider_id == 'edge-tts':
        return EdgeTTSProvider()
    if provider_id == 'kokoro-local':
        return KokoroLocalProvider()
    spec = TTS_PROVIDER_SPECS.get(provider_id)
    if not spec:
        raise ProviderUnavailable(f'Unknown TTS provider: {provider_id}')
    return ReservedTTSAPIProvider(spec)


def enabled_tts_specs() -> list[ProviderSpec]:
    return [spec for spec in TTS_PROVIDER_SPECS.values() if spec.enabled]


class OCRProvider:
    spec: ProviderSpec
    page_checkpoint_capable = False

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def recognize_pdf_to_text(self, source: Path, *, language: str, output_dir: Path, pages: Iterable[int] | None = None) -> str:
        raise NotImplementedError


class PaddleOCRProvider(OCRProvider):
    page_checkpoint_capable = True
    spec = ProviderSpec('paddleocr-ppocrv5', 'ocr', 'PaddleOCR · PP-OCRv5', 'local-python', 'enabled-when-discovered', True, notes='Local OCR provider. Models may download on first use.')

    def available(self) -> tuple[bool, str]:
        if importlib.util.find_spec('paddleocr') is None:
            return False, 'Python package paddleocr is not installed.'
        if not shutil.which('pdftoppm'):
            return False, 'Poppler pdftoppm is not available on PATH.'
        return True, 'PaddleOCR Python package and pdftoppm detected.'

    @staticmethod
    def _lang(language: str) -> str:
        return {'chinese': 'ch', 'english': 'en', 'mixed': 'ch', 'other': 'en'}.get(language, 'ch')

    @staticmethod
    def _collect_strings(value: Any) -> list[str]:
        out: list[str] = []
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'rec_texts', 'texts'} and isinstance(item, list):
                    out.extend(str(text) for text in item if str(text).strip())
                elif key in {'text', 'rec_text'} and isinstance(item, str):
                    out.append(item)
                else:
                    out.extend(PaddleOCRProvider._collect_strings(item))
        elif isinstance(value, (list, tuple)):
            if len(value) == 2 and isinstance(value[1], (list, tuple)) and value[1] and isinstance(value[1][0], str):
                out.append(value[1][0])
            else:
                for item in value:
                    out.extend(PaddleOCRProvider._collect_strings(item))
        else:
            maybe_json = getattr(value, 'json', None)
            if maybe_json is not None:
                try:
                    decoded = json.loads(maybe_json) if isinstance(maybe_json, str) else maybe_json
                    out.extend(PaddleOCRProvider._collect_strings(decoded))
                except Exception:
                    pass
        return out

    def _recognize_image(self, image: Path, language: str) -> str:
        available, reason = self.available()
        if not available:
            raise ProviderUnavailable(reason)
        from paddleocr import PaddleOCR
        engine = PaddleOCR(lang=self._lang(language))
        if hasattr(engine, 'predict'):
            result = engine.predict(input=str(image))
        else:
            result = engine.ocr(str(image), cls=True)
        lines = [line.strip() for line in self._collect_strings(result) if line and line.strip()]
        return '\n'.join(lines)

    def recognize_pdf_to_text(self, source: Path, *, language: str, output_dir: Path, pages: Iterable[int] | None = None) -> str:
        available, reason = self.available()
        if not available:
            raise ProviderUnavailable(reason)
        output_dir.mkdir(parents=True, exist_ok=True)
        pages_to_run = list(pages or [])
        if pages_to_run:
            images = []
            for page in pages_to_run:
                prefix = output_dir / f'page-{int(page):04d}'
                run_hidden_cli(['pdftoppm', '-f', str(page), '-l', str(page), '-singlefile', '-png', '-r', '250', str(source), str(prefix)], check=True, capture_output=True)
                images.append(prefix.with_suffix('.png'))
        else:
            prefix = output_dir / 'page'
            run_hidden_cli(['pdftoppm', '-png', '-r', '250', str(source), str(prefix)], check=True, capture_output=True)
            images = sorted(output_dir.glob('page-*.png'))
        return '\f'.join(self._recognize_image(image, language) for image in images)


class TesseractOCRProvider(OCRProvider):
    page_checkpoint_capable = True
    spec = ProviderSpec('tesseract-local', 'ocr', 'Tesseract local OCR', 'local-process', 'enabled-when-discovered', True, notes='Local fallback OCR provider.')

    def available(self) -> tuple[bool, str]:
        if not shutil.which('tesseract'):
            return False, 'tesseract is not available on PATH.'
        if not shutil.which('pdftoppm'):
            return False, 'Poppler pdftoppm is not available on PATH.'
        return True, 'tesseract and pdftoppm detected.'

    @staticmethod
    def _lang(language: str) -> str:
        return {'chinese': 'chi_sim+eng', 'english': 'eng', 'mixed': 'chi_sim+eng', 'other': 'eng'}.get(language, 'eng')

    def installed_languages(self) -> set[str]:
        if not shutil.which('tesseract'):
            return set()
        result = run_hidden_cli(['tesseract', '--list-langs'], capture_output=True, text=True, check=False)
        return {line.strip() for line in result.stdout.splitlines()[1:] if line.strip()}

    def recognize_pdf_to_text(self, source: Path, *, language: str, output_dir: Path, pages: Iterable[int] | None = None) -> str:
        available, reason = self.available()
        if not available:
            raise ProviderUnavailable(reason)
        output_dir.mkdir(parents=True, exist_ok=True)
        languages = self._lang(language)
        requested = set(languages.split('+'))
        missing = requested - self.installed_languages()
        if missing:
            raise ProviderUnavailable(f'Tesseract language packs missing: {sorted(missing)}')
        pages_to_run = list(pages or [])
        if pages_to_run:
            images = []
            for page in pages_to_run:
                prefix = output_dir / f'page-{int(page):04d}'
                run_hidden_cli(['pdftoppm', '-f', str(page), '-l', str(page), '-singlefile', '-png', '-r', '250', str(source), str(prefix)], check=True, capture_output=True)
                images.append(prefix.with_suffix('.png'))
        else:
            prefix = output_dir / 'page'
            run_hidden_cli(['pdftoppm', '-png', '-r', '250', str(source), str(prefix)], check=True, capture_output=True)
            images = sorted(output_dir.glob('page-*.png'))
        out = []
        for image in images:
            result = run_hidden_cli(['tesseract', str(image), 'stdout', '-l', languages], capture_output=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode('utf-8', 'replace'))
            out.append(result.stdout.decode('utf-8', 'replace'))
        return '\f'.join(out)


class OCRmyPDFProvider(OCRProvider):
    page_checkpoint_capable = False
    spec = ProviderSpec('ocrmypdf-tesseract', 'ocr', 'OCRmyPDF · Tesseract searchable PDF', 'local-process', 'enabled-when-discovered', True, notes='Adds a searchable text layer. Text is extracted by the normal PDF path afterwards.')

    def available(self) -> tuple[bool, str]:
        if not shutil.which('ocrmypdf'):
            return False, 'ocrmypdf is not available on PATH.'
        if not shutil.which('tesseract'):
            return False, 'tesseract is not available on PATH.'
        return True, 'ocrmypdf and tesseract detected.'

    def recognize_pdf_to_text(self, source: Path, *, language: str, output_dir: Path, pages: Iterable[int] | None = None) -> str:
        raise ProviderUnavailable('OCRmyPDF is a searchable-PDF adapter. Use create_searchable_pdf().')

    def create_searchable_pdf(self, source: Path, output_pdf: Path, *, language: str) -> Path:
        available, reason = self.available()
        if not available:
            raise ProviderUnavailable(reason)
        langs = {'chinese': 'chi_sim+eng', 'english': 'eng', 'mixed': 'chi_sim+eng', 'other': 'eng'}.get(language, 'eng')
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        run_hidden_cli(['ocrmypdf', '--skip-text', '--deskew', '-l', langs, str(source), str(output_pdf)], check=True)
        return output_pdf


class ReservedOCRAPIProvider(ExternalAPIContract, OCRProvider):
    def __init__(self, spec: ProviderSpec):
        self.spec = spec

    def available(self) -> tuple[bool, str]:
        return False, f'{self.spec.label} is reserved but disabled.'

    def recognize_pdf_to_text(self, source: Path, *, language: str, output_dir: Path, pages: Iterable[int] | None = None) -> str:
        self.assert_configured()
        raise ProviderUnavailable(f'{self.spec.label} adapter is reserved but not implemented.')


OCR_PROVIDER_SPECS: dict[str, ProviderSpec] = {
    'native-text': ProviderSpec('native-text', 'ocr', 'Native text layer', 'native', 'enabled', True, notes='No OCR needed.'),
    'paddleocr-ppocrv5': PaddleOCRProvider.spec,
    'tesseract-local': TesseractOCRProvider.spec,
    'ocrmypdf-tesseract': OCRmyPDFProvider.spec,
    'openai-vision-api': ProviderSpec('openai-vision-api', 'ocr', 'OpenAI Vision API', 'external-api', 'reserved', False, 'OPENAI_API_KEY', None, 'Reserved cloud OCR fallback slot. Disabled by default.'),
    'claude-vision-api': ProviderSpec('claude-vision-api', 'ocr', 'Claude Vision API', 'external-api', 'reserved', False, 'ANTHROPIC_API_KEY', None, 'Reserved cloud OCR fallback slot. Disabled by default.'),
    'custom-http-ocr-api': ProviderSpec('custom-http-ocr-api', 'ocr', 'Custom HTTP OCR API', 'external-api', 'reserved', False, 'KR_B2A_OCR_API_KEY', 'KR_B2A_OCR_API_ENDPOINT', 'Reserved generic API adapter slot.'),
    'paddleocr-vl': ProviderSpec('paddleocr-vl', 'ocr', 'PaddleOCR-VL', 'local-python', 'reserved', False, notes='Reserved complex-layout adapter slot.'),
}


def get_ocr_provider(provider_id: str) -> OCRProvider:
    if provider_id == 'paddleocr-ppocrv5':
        return PaddleOCRProvider()
    if provider_id == 'tesseract-local':
        return TesseractOCRProvider()
    if provider_id == 'ocrmypdf-tesseract':
        return OCRmyPDFProvider()
    spec = OCR_PROVIDER_SPECS.get(provider_id)
    if not spec:
        raise ProviderUnavailable(f'Unknown OCR provider: {provider_id}')
    return ReservedOCRAPIProvider(spec)


def provider_registry_snapshot() -> dict[str, list[dict[str, Any]]]:
    ocr = []
    for provider_id, spec in OCR_PROVIDER_SPECS.items():
        payload = spec.to_dict()
        try:
            payload['page_checkpoint_capable'] = bool(get_ocr_provider(provider_id).page_checkpoint_capable)
        except Exception:
            payload['page_checkpoint_capable'] = False
        ocr.append(payload)
    return {
        'tts': [spec.to_dict() for spec in TTS_PROVIDER_SPECS.values()],
        'ocr': ocr,
    }


def registry_snapshot() -> dict[str, list[dict[str, Any]]]:
    """Return a JSON-safe provider registry snapshot for diagnostics and portable smoke tests."""
    return {
        'tts': [spec.to_dict() for spec in TTS_PROVIDER_SPECS.values()],
        'ocr': [spec.to_dict() for spec in OCR_PROVIDER_SPECS.values()],
    }
