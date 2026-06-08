import inspect
import json
import tempfile
import unittest
import runpy
import sys
import types
from pathlib import Path
from kr_book_to_audio import portable
from kr_book_to_audio import gui

ROOT=Path(__file__).resolve().parents[1]

class PortableContractTests(unittest.TestCase):
    def test_spec_uses_onedir_windowed_icon_and_collects_package_data(self):
        spec=(ROOT/'packaging/KRBookToAudio.spec').read_text(encoding='utf-8')
        self.assertIn("console=False", spec)
        self.assertIn("name='KRBookToAudio'", spec)
        self.assertIn("COLLECT(", spec)
        self.assertIn("collect_data_files('kr_book_to_audio')", spec)
        self.assertIn("kr_book_to_audio.ico", spec)

    def test_spec_resolves_real_pyinstaller_spec_directory_and_preloads_src_for_hooks(self):
        """SPECPATH is a directory in real PyInstaller spec execution."""
        spec_path = ROOT / 'packaging' / 'KRBookToAudio.spec'
        hook_calls = []
        analysis_calls = []

        hooks = types.ModuleType('PyInstaller.utils.hooks')
        def collect_data_files(name):
            hook_calls.append(('data', name, str(ROOT / 'src') in sys.path))
            return [('branding', 'branding')]
        def collect_submodules(name):
            hook_calls.append(('submodules', name, str(ROOT / 'src') in sys.path))
            return ['edge_tts']
        hooks.collect_data_files = collect_data_files
        hooks.collect_submodules = collect_submodules

        pyinstaller = types.ModuleType('PyInstaller')
        utils = types.ModuleType('PyInstaller.utils')
        original = {name: sys.modules.get(name) for name in (
            'PyInstaller', 'PyInstaller.utils', 'PyInstaller.utils.hooks'
        )}
        sys.modules['PyInstaller'] = pyinstaller
        sys.modules['PyInstaller.utils'] = utils
        sys.modules['PyInstaller.utils.hooks'] = hooks

        class AnalysisStub:
            def __init__(self, scripts, **kwargs):
                analysis_calls.append((scripts, kwargs))
                self.pure = []
                self.scripts = []
                self.binaries = []
                self.datas = kwargs['datas']
        try:
            runpy.run_path(str(spec_path), init_globals={
                'SPECPATH': str(ROOT / 'packaging'),
                'Analysis': AnalysisStub,
                'PYZ': lambda pure: ('PYZ', pure),
                'EXE': lambda *args, **kwargs: ('EXE', args, kwargs),
                'COLLECT': lambda *args, **kwargs: ('COLLECT', args, kwargs),
            })
        finally:
            for name, module in original.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

        self.assertEqual(len(analysis_calls), 1)
        scripts, kwargs = analysis_calls[0]
        self.assertEqual(Path(scripts[0]).resolve(), (ROOT / 'src' / 'kr_book_to_audio_gui.py').resolve())
        self.assertEqual([Path(p).resolve() for p in kwargs['pathex']], [(ROOT / 'src').resolve()])
        self.assertEqual(kwargs['datas'], [('branding', 'branding')])
        self.assertEqual(hook_calls, [
            ('data', 'kr_book_to_audio', True),
            ('submodules', 'edge_tts', True),
        ])

    def test_spec_does_not_walk_two_parents_above_spec_directory(self):
        spec=(ROOT/'packaging/KRBookToAudio.spec').read_text(encoding='utf-8')
        self.assertIn("SPEC_DIR = Path(SPECPATH).resolve()", spec)
        self.assertIn("ROOT = SPEC_DIR.parent", spec)
        self.assertNotIn("parent.parent", spec)
        self.assertIn("sys.path.insert(0, str(SRC))", spec)

    def test_portable_smoke_report_is_json_safe_in_source_mode(self):
        report=portable.portable_smoke_report()
        json.dumps(report)
        self.assertTrue(report['ok'])
        self.assertIn('provider_registry', report)
        self.assertTrue(report['branding_ico'])

    def test_entrypoint_supports_hidden_smoke_mode(self):
        entry=(ROOT/'src/kr_book_to_audio_gui.py').read_text(encoding='utf-8')
        self.assertIn('portable_main', entry)
        self.assertIn('--portable-smoke-test', inspect.getsource(portable))

    def test_public_screenshot_and_readme_branding_exist(self):
        readme=(ROOT/'README.md').read_text(encoding='utf-8')
        self.assertIn("Possibly the world's best book-to-audio conversion software.", readme)
        self.assertIn('可能是全世界最好用的 Book-to-Audio 轉換軟體。', readme)
        self.assertIn('Built by Kent Reis from Constantinople with love. AD May 20, 2026', readme)
        self.assertIn('Copyright © Kent Reis & Kairos República', readme)
        self.assertTrue((ROOT/'docs/images/kr_book_to_audio_gui_istanbul_release_2_0.png').exists())
        self.assertTrue((ROOT/'docs/images/kr_book_to_audio_gui_istanbul_release_v2_0_1.png').exists())

if __name__=='__main__': unittest.main()
