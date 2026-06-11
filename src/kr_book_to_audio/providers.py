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
from .subprocess_utils import popen_hidden_cli, run_hidden_cli

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
            worker_timeout = float(os.environ.get('KR_B2A_KOKORO_TOTAL_TIMEOUT_SECONDS', '1800'))
            stdout_path = Path(temp_dir) / 'worker.stdout.txt'
            stderr_path = Path(temp_dir) / 'worker.stderr.txt'
            with stdout_path.open('w', encoding='utf-8') as stdout_handle, stderr_path.open('w', encoding='utf-8') as stderr_handle:
                process = popen_hidden_cli(
                    [str(foundation.python), str(foundation.worker), '--request', str(request_path)],
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    text=True,
                    env=foundation.worker_env(),
                )
                while process.poll() is None:
                    elapsed = time.monotonic() - started
                    if elapsed >= worker_timeout:
                        process.terminate()
                        try:
                            process.wait(timeout=3.0)
                        except Exception:
                            process.kill()
                            process.wait(timeout=3.0)
                        out_path.unlink(missing_ok=True)
                        raise ProviderTimedOut(
                            f'Kokoro Local exceeded the total Part timeout of {int(worker_timeout)} seconds. '
                            'The local worker was terminated safely. Try a shorter Part or inspect the diagnostic ZIP.'
                        )
                    _emit(
                        progress,
                        provider_id=self.spec.provider_id,
                        stage='local-worker-running',
                        elapsed_seconds=round(elapsed, 3),
                        bytes_received=int(wav_path.stat().st_size) if wav_path.exists() else 0,
                        last_audio_seconds_ago=0.0,
                    )
                    time.sleep(1.0)
                returncode = int(process.returncode or 0)
            stdout = stdout_path.read_text(encoding='utf-8', errors='replace') if stdout_path.exists() else ''
            stderr = stderr_path.read_text(encoding='utf-8', errors='replace') if stderr_path.exists() else ''
            if returncode != 0:
                out_path.unlink(missing_ok=True)
                detail = (stderr or stdout or '').strip()
                raise ProviderUnavailable(f'Kokoro Local worker failed: {detail or "unknown error"}')
            if not wav_path.exists() or wav_path.stat().st_size <= 0:
                raise ProviderUnavailable('Kokoro Local worker completed without writing WAV output.')
            _emit(
                progress,
                provider_id=self.spec.provider_id,
                stage='local-worker-encoding',
                elapsed_seconds=round(time.monotonic() - started, 3),
                bytes_received=int(wav_path.stat().st_size),
                last_audio_seconds_ago=0.0,
            )
            encoded = run_hidden_cli(
                ['ffmpeg', '-y', '-v', 'error', '-i', str(wav_path), '-codec:a', 'libmp3lame', '-q:a', '2', str(out_path)],
                capture_output=True,
                text=True,
                check=False,
                timeout=float(os.environ.get('KR_B2A_FFMPEG_ENCODE_TIMEOUT_SECONDS', '180')),
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

    def recognize_pdf_to_text(
        self,
        source: Path,
        *,
        language: str,
        output_dir: Path,
        pages: Iterable[int] | None = None,
        progress: ProviderProgressCallback | None = None,
    ) -> str:
        raise NotImplementedError


class PaddleOCRProvider(OCRProvider):
    page_checkpoint_capable = True

    def __init__(self, profile: str = 'server') -> None:
        self.profile = profile if profile in {'server', 'mobile'} else 'server'
        provider_id = 'paddleocr-ppocrv5' if self.profile == 'server' else 'paddleocr-ppocrv5-mobile'
        label = 'PaddleOCR PP-OCRv5 · server accuracy' if self.profile == 'server' else 'PaddleOCR PP-OCRv5 · mobile fallback'
        self.spec = ProviderSpec(
            provider_id,
            'ocr',
            label,
            'local-process',
            'enabled-when-installed',
            True,
            notes='Governed offline local OCR Provider. Models are archived before deployment and normal use is offline-only.',
        )

    @staticmethod
    def _foundation():
        from .local_ocr import local_ocr_foundation
        return local_ocr_foundation()

    def available(self) -> tuple[bool, str]:
        foundation = self._foundation()
        if foundation.paddle_ready(self.profile):
            return True, f'PaddleOCR {self.profile} profile detected in the governed local OCR runtime.'
        return False, f'PaddleOCR {self.profile} profile is not deployed. Use Install / repair local OCR foundation.'

    def _recognize_image(self, image: Path, *, output_dir: Path) -> str:
        foundation = self._foundation()
        foundation.assert_paddle_ready(self.profile)
        output_dir.mkdir(parents=True, exist_ok=True)
        det, rec = foundation.paddle_model_paths(self.profile)
        request_path = output_dir / (image.stem + '.request.json')
        response_path = output_dir / (image.stem + '.response.json')
        request_path.write_text(json.dumps({
            'image': str(image),
            'output': str(response_path),
            'text_detection_model_name': f'PP-OCRv5_{self.profile}_det',
            'text_detection_model_dir': str(det),
            'text_recognition_model_name': f'PP-OCRv5_{self.profile}_rec',
            'text_recognition_model_dir': str(rec),
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        result = run_hidden_cli(
            [str(foundation.paddle_python), str(foundation.paddle_worker), '--request', str(request_path)],
            capture_output=True,
            text=True,
            check=False,
            env=foundation.offline_env(),
            timeout=float(os.environ.get('KR_B2A_PADDLEOCR_PAGE_TIMEOUT_SECONDS', '600')),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or '').strip()
            raise ProviderUnavailable(f'PaddleOCR local worker failed: {detail or "unknown error"}')
        if not response_path.is_file():
            raise ProviderUnavailable('PaddleOCR local worker did not write a response JSON file.')
        payload = json.loads(response_path.read_text(encoding='utf-8'))
        return str(payload.get('text') or '')

    def recognize_pdf_to_text(
        self,
        source: Path,
        *,
        language: str,
        output_dir: Path,
        pages: Iterable[int] | None = None,
        progress: ProviderProgressCallback | None = None,
    ) -> str:
        available, reason = self.available()
        if not available:
            raise ProviderUnavailable(reason)
        foundation = self._foundation()
        output_dir.mkdir(parents=True, exist_ok=True)
        pages_to_run = list(pages or [])
        if not pages_to_run:
            raise ProviderUnavailable('PaddleOCR page-level execution requires an explicit page list.')
        out: list[str] = []
        total = len(pages_to_run)
        for offset, page in enumerate(pages_to_run, start=1):
            prefix = output_dir / f'page-{int(page):04d}'
            run_hidden_cli(
                [str(foundation.pdftoppm), '-f', str(page), '-l', str(page), '-singlefile', '-png', '-r', '250', str(source), str(prefix)],
                check=True,
                capture_output=True,
                env=foundation.offline_env(),
            )
            _emit(progress, provider_id=self.spec.provider_id, state='ocr-page-rendered', page=int(page), page_offset=offset, total_pages=total)
            text = self._recognize_image(prefix.with_suffix('.png'), output_dir=output_dir)
            out.append(text)
            _emit(progress, provider_id=self.spec.provider_id, state='ocr-page-recognized', page=int(page), page_offset=offset, total_pages=total, text_chars=len(text))
        return '\f'.join(out)


class TesseractOCRProvider(OCRProvider):
    page_checkpoint_capable = True

    def __init__(self, profile: str = 'fast') -> None:
        self.profile = profile if profile in {'fast', 'best'} else 'fast'
        provider_id = 'tesseract-local' if self.profile == 'fast' else 'tesseract-local-best'
        label = 'Tesseract local OCR · fast fallback' if self.profile == 'fast' else 'Tesseract local OCR · best accuracy'
        self.spec = ProviderSpec(provider_id, 'ocr', label, 'local-process', 'enabled-when-installed', True, notes='Governed offline local OCR fallback Provider.')

    @staticmethod
    def _foundation():
        from .local_ocr import local_ocr_foundation
        return local_ocr_foundation()

    def available(self) -> tuple[bool, str]:
        foundation = self._foundation()
        if foundation.tesseract_ready(self.profile):
            return True, f'Tesseract {self.profile} profile and Poppler detected in the governed local OCR runtime.'
        return False, f'Tesseract {self.profile} profile is not deployed. Use Install / repair local OCR foundation.'

    @staticmethod
    def _lang(language: str) -> str:
        return {'chinese': 'chi_sim+eng', 'english': 'eng', 'mixed': 'chi_sim+eng', 'other': 'eng', 'uncertain': 'chi_sim+eng'}.get(language, 'chi_sim+eng')

    def installed_languages(self) -> set[str]:
        foundation = self._foundation()
        if not foundation.tesseract.is_file():
            return set()
        result = run_hidden_cli([str(foundation.tesseract), '--tessdata-dir', str(foundation.tessdata(self.profile)), '--list-langs'], capture_output=True, text=True, check=False, env=foundation.tesseract_env(self.profile))
        return {line.strip() for line in result.stdout.splitlines()[1:] if line.strip()}

    def recognize_pdf_to_text(
        self,
        source: Path,
        *,
        language: str,
        output_dir: Path,
        pages: Iterable[int] | None = None,
        progress: ProviderProgressCallback | None = None,
    ) -> str:
        available, reason = self.available()
        if not available:
            raise ProviderUnavailable(reason)
        foundation = self._foundation()
        output_dir.mkdir(parents=True, exist_ok=True)
        languages = self._lang(language)
        missing = set(languages.split('+')) - self.installed_languages()
        if missing:
            raise ProviderUnavailable(f'Tesseract language packs missing: {sorted(missing)}')
        pages_to_run = list(pages or [])
        if not pages_to_run:
            raise ProviderUnavailable('Tesseract page-level execution requires an explicit page list.')
        out: list[str] = []
        total = len(pages_to_run)
        for offset, page in enumerate(pages_to_run, start=1):
            prefix = output_dir / f'page-{int(page):04d}'
            run_hidden_cli(
                [str(foundation.pdftoppm), '-f', str(page), '-l', str(page), '-singlefile', '-png', '-r', '250', str(source), str(prefix)],
                check=True,
                capture_output=True,
                env=foundation.tesseract_env(self.profile),
            )
            _emit(progress, provider_id=self.spec.provider_id, state='ocr-page-rendered', page=int(page), page_offset=offset, total_pages=total)
            result = run_hidden_cli(
                [str(foundation.tesseract), '--tessdata-dir', str(foundation.tessdata(self.profile)), str(prefix.with_suffix('.png')), 'stdout', '-l', languages],
                capture_output=True,
                check=False,
                env=foundation.tesseract_env(self.profile),
            )
            if result.returncode != 0:
                raise RuntimeError((result.stderr or b'').decode('utf-8', 'replace') if isinstance(result.stderr, (bytes, bytearray)) else str(result.stderr or 'Tesseract failed.'))
            text = result.stdout.decode('utf-8', 'replace') if isinstance(result.stdout, (bytes, bytearray)) else str(result.stdout or '')
            out.append(text)
            _emit(progress, provider_id=self.spec.provider_id, state='ocr-page-recognized', page=int(page), page_offset=offset, total_pages=total, text_chars=len(text))
        return '\f'.join(out)


class OCRmyPDFProvider(OCRProvider):
    page_checkpoint_capable = False
    spec = ProviderSpec('ocrmypdf-tesseract', 'ocr', 'OCRmyPDF · Tesseract searchable PDF', 'local-process', 'optional-adapter', False, notes='Optional searchable-PDF adapter. Not installed by the v2.5.0 OCR foundation.')

    def available(self) -> tuple[bool, str]:
        return False, 'OCRmyPDF remains an optional adapter and is not installed by the v2.5.0 local OCR foundation.'

    def recognize_pdf_to_text(self, source: Path, *, language: str, output_dir: Path, pages: Iterable[int] | None = None, progress: ProviderProgressCallback | None = None) -> str:
        raise ProviderUnavailable('OCRmyPDF is an optional searchable-PDF adapter, not an operational v2.5.0 core OCR Provider.')


class ReservedOCRAPIProvider(ExternalAPIContract, OCRProvider):
    def __init__(self, spec: ProviderSpec):
        self.spec = spec

    def available(self) -> tuple[bool, str]:
        return False, f'{self.spec.label} is reserved but disabled.'

    def recognize_pdf_to_text(self, source: Path, *, language: str, output_dir: Path, pages: Iterable[int] | None = None, progress: ProviderProgressCallback | None = None) -> str:
        self.assert_configured()
        raise ProviderUnavailable(f'{self.spec.label} adapter is reserved but not implemented.')


OCR_PROVIDER_SPECS: dict[str, ProviderSpec] = {
    'native-text': ProviderSpec('native-text', 'ocr', 'Native text layer', 'native', 'enabled', True, notes='No OCR needed.'),
    'paddleocr-ppocrv5': PaddleOCRProvider('server').spec,
    'paddleocr-ppocrv5-mobile': PaddleOCRProvider('mobile').spec,
    'tesseract-local': TesseractOCRProvider('fast').spec,
    'tesseract-local-best': TesseractOCRProvider('best').spec,
    'ocrmypdf-tesseract': OCRmyPDFProvider.spec,
    'openai-vision-api': ProviderSpec('openai-vision-api', 'ocr', 'OpenAI Vision API', 'external-api', 'reserved', False, 'OPENAI_API_KEY', None, 'Reserved cloud OCR fallback slot. Disabled by default.'),
    'claude-vision-api': ProviderSpec('claude-vision-api', 'ocr', 'Claude Vision API', 'external-api', 'reserved', False, 'ANTHROPIC_API_KEY', None, 'Reserved cloud OCR fallback slot. Disabled by default.'),
    'custom-http-ocr-api': ProviderSpec('custom-http-ocr-api', 'ocr', 'Custom HTTP OCR API', 'external-api', 'reserved', False, 'KR_B2A_OCR_API_KEY', 'KR_B2A_OCR_API_ENDPOINT', 'Reserved generic API adapter slot.'),
    'paddleocr-vl': ProviderSpec('paddleocr-vl', 'ocr', 'PaddleOCR-VL', 'local-python', 'reserved', False, notes='Reserved complex-layout adapter slot.'),
}


def get_ocr_provider(provider_id: str) -> OCRProvider:
    if provider_id == 'paddleocr-ppocrv5':
        return PaddleOCRProvider('server')
    if provider_id == 'paddleocr-ppocrv5-mobile':
        return PaddleOCRProvider('mobile')
    if provider_id == 'tesseract-local':
        return TesseractOCRProvider('fast')
    if provider_id == 'tesseract-local-best':
        return TesseractOCRProvider('best')
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
