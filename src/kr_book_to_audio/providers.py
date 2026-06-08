from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable
import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile


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


class TTSProvider:
    spec: ProviderSpec

    def list_voices(self) -> list[dict[str, str]]:
        raise NotImplementedError

    def synthesize(self, text: str, out_path: Path, *, voice: str, rate: str, pitch: str, volume: str) -> None:
        raise NotImplementedError


class EdgeTTSProvider(TTSProvider):
    spec = ProviderSpec(
        provider_id='edge-tts',
        kind='tts',
        label='Microsoft Edge Online TTS · edge-tts',
        transport='online-no-api-key',
        status='enabled',
        enabled=True,
        notes='Current default provider. Uses the edge-tts Python adapter.',
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

    def synthesize(self, text: str, out_path: Path, *, voice: str, rate: str, pitch: str, volume: str) -> None:
        try:
            import edge_tts
        except ImportError as exc:
            raise ProviderUnavailable('edge-tts is not installed. Run: pip install -U edge-tts') from exc
        asyncio.run(edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume).save(str(out_path)))


class ReservedTTSAPIProvider(ExternalAPIContract, TTSProvider):
    def __init__(self, spec: ProviderSpec):
        self.spec = spec

    def list_voices(self) -> list[dict[str, str]]:
        self.assert_configured()
        raise ProviderUnavailable(f'{self.spec.label} adapter is reserved but not implemented.')

    def synthesize(self, text: str, out_path: Path, *, voice: str, rate: str, pitch: str, volume: str) -> None:
        self.assert_configured()
        raise ProviderUnavailable(f'{self.spec.label} adapter is reserved but not implemented.')


TTS_PROVIDER_SPECS: dict[str, ProviderSpec] = {
    'edge-tts': EdgeTTSProvider.spec,
    'azure-speech-api': ProviderSpec('azure-speech-api', 'tts', 'Azure Speech API', 'external-api', 'reserved', False, 'AZURE_SPEECH_KEY', 'AZURE_SPEECH_ENDPOINT', 'Reserved API adapter slot.'),
    'openai-tts-api': ProviderSpec('openai-tts-api', 'tts', 'OpenAI TTS API', 'external-api', 'reserved', False, 'OPENAI_API_KEY', None, 'Reserved API adapter slot.'),
    'custom-http-tts-api': ProviderSpec('custom-http-tts-api', 'tts', 'Custom HTTP TTS API', 'external-api', 'reserved', False, 'KR_B2A_TTS_API_KEY', 'KR_B2A_TTS_API_ENDPOINT', 'Reserved generic API adapter slot.'),
    'piper-local': ProviderSpec('piper-local', 'tts', 'Piper local TTS', 'local-process', 'reserved', False, None, None, 'Reserved offline adapter slot.'),
}


def get_tts_provider(provider_id: str = 'edge-tts') -> TTSProvider:
    if provider_id == 'edge-tts':
        return EdgeTTSProvider()
    spec = TTS_PROVIDER_SPECS.get(provider_id)
    if not spec:
        raise ProviderUnavailable(f'Unknown TTS provider: {provider_id}')
    return ReservedTTSAPIProvider(spec)


def enabled_tts_specs() -> list[ProviderSpec]:
    return [spec for spec in TTS_PROVIDER_SPECS.values() if spec.enabled]


class OCRProvider:
    spec: ProviderSpec

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def recognize_pdf_to_text(self, source: Path, *, language: str, output_dir: Path, pages: Iterable[int] | None = None) -> str:
        raise NotImplementedError


class PaddleOCRProvider(OCRProvider):
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
                subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-singlefile', '-png', '-r', '250', str(source), str(prefix)], check=True, capture_output=True)
                images.append(prefix.with_suffix('.png'))
        else:
            prefix = output_dir / 'page'
            subprocess.run(['pdftoppm', '-png', '-r', '250', str(source), str(prefix)], check=True, capture_output=True)
            images = sorted(output_dir.glob('page-*.png'))
        return '\f'.join(self._recognize_image(image, language) for image in images)


class TesseractOCRProvider(OCRProvider):
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
        result = subprocess.run(['tesseract', '--list-langs'], capture_output=True, text=True, check=False)
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
                subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-singlefile', '-png', '-r', '250', str(source), str(prefix)], check=True, capture_output=True)
                images.append(prefix.with_suffix('.png'))
        else:
            prefix = output_dir / 'page'
            subprocess.run(['pdftoppm', '-png', '-r', '250', str(source), str(prefix)], check=True, capture_output=True)
            images = sorted(output_dir.glob('page-*.png'))
        out = []
        for image in images:
            result = subprocess.run(['tesseract', str(image), 'stdout', '-l', languages], capture_output=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode('utf-8', 'replace'))
            out.append(result.stdout.decode('utf-8', 'replace'))
        return '\f'.join(out)


class OCRmyPDFProvider(OCRProvider):
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
        subprocess.run(['ocrmypdf', '--skip-text', '--deskew', '-l', langs, str(source), str(output_pdf)], check=True)
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
    return {
        'tts': [spec.to_dict() for spec in TTS_PROVIDER_SPECS.values()],
        'ocr': [spec.to_dict() for spec in OCR_PROVIDER_SPECS.values()],
    }
