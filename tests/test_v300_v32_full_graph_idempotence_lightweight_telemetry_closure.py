from pathlib import Path
import ast
import unittest
ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / 'src' / 'kr_book_to_audio' / 'gui.py'

class V300V32FullGraphIdempotenceLightweightTelemetryClosureTests(unittest.TestCase):
    def gui(self) -> str:
        return GUI.read_text(encoding='utf-8')

    def method_source(self, name: str) -> str:
        source = self.gui()
        tree = ast.parse(source)
        lines = source.splitlines()
        nodes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name]
        self.assertEqual(len(nodes), 1, name)
        node = nodes[0]
        return '\n'.join(lines[node.lineno - 1:node.end_lineno])

    def test_provider_telemetry_fast_path_is_memory_only(self):
        method = self.method_source('_update_provider_telemetry')
        self.assertNotIn('job_status(', method)
        self.assertNotIn('self.job', method)
        self.assertIn('self._project_tts_overall_percent(index, self.current_estimate)', method)
        self.assertIn('self._render_audio_status_summary(index=index, percent=self.current_estimate)', method)

    def test_project_tts_overall_percent_uses_cache_not_manifest(self):
        method = self.method_source('_project_tts_overall_percent')
        self.assertNotIn('job_status(', method)
        self.assertNotIn('self.job', method)
        self.assertIn("getattr(self, '_audio_total_parts_cache'", method)
        self.assertIn("getattr(self, '_audio_completed_parts_cache'", method)

    def test_low_frequency_seed_is_the_only_manifest_hydration_path(self):
        method = self.method_source('_seed_audio_progress_cache')
        self.assertIn("job = getattr(self, 'job', None)", method)
        self.assertIn('status = job_status(job)', method)
        for name in ('preview', 'synthesize', 'retry_failed', '_resume_from_part'):
            self.assertIn('self._seed_audio_progress_cache(', self.method_source(name))

    def test_v32_runtime_marker_exists(self):
        self.assertIn('V32_FULL_GRAPH_IDEMPOTENCE_LIGHTWEIGHT_TELEMETRY_RUNTIME', self.gui())

if __name__ == '__main__': unittest.main()
