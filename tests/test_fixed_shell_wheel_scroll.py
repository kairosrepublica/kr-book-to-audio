import inspect
import unittest
from unittest.mock import Mock, patch
from kr_book_to_audio import gui
from kr_book_to_audio.gui import outer_scroll_enabled, preserves_native_wheel, visible_window_height_px, wheel_scroll_units

class FixedShellWheelScrollTests(unittest.TestCase):
    def test_footer_is_fixed_outside_scroll_viewport(self):
        source = inspect.getsource(gui.App._build)
        self.assertIn("self.shell = ttk.Frame(self.root)", source)
        self.assertIn("self.viewport = ttk.Frame(self.shell)", source)
        self.assertIn("footer = ttk.Frame(self.shell, padding=(12, 2))", source)
        self.assertIn("footer.pack(side='bottom', fill='x')", source)
        self.assertNotIn("footer = ttk.Frame(frame)", source)
        self.assertNotIn("footer.grid(", source)

    def test_minimum_width_is_enforced_by_root(self):
        source = inspect.getsource(gui.App.__init__)
        self.assertIn("self.root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)", source)

    def test_windows_wheel_and_touchpad_delta_scroll_outer_viewport(self):
        self.assertEqual(wheel_scroll_units(120), -1)
        self.assertEqual(wheel_scroll_units(-120), 1)
        self.assertEqual(wheel_scroll_units(1), -1)
        self.assertEqual(wheel_scroll_units(-1), 1)
        self.assertEqual(wheel_scroll_units(240), -2)

    def test_inner_widgets_preserve_native_wheel(self):
        for widget_class in ('Text', 'Treeview', 'Listbox', 'TCombobox'):
            self.assertTrue(preserves_native_wheel(widget_class))
        self.assertFalse(preserves_native_wheel('TFrame'))
        self.assertFalse(preserves_native_wheel('TLabel'))

    def test_mousewheel_bindings_cover_windows_and_linux(self):
        source = inspect.getsource(gui.App._bind_mousewheel)
        self.assertIn("'<MouseWheel>'", source)
        self.assertIn("'<Button-4>'", source)
        self.assertIn("'<Button-5>'", source)

    def test_combobox_wheel_is_not_hijacked(self):
        source = inspect.getsource(gui.App._on_mousewheel)
        self.assertIn('preserves_native_wheel', source)
        self.assertIn('return None', source)

    def test_outer_scroll_boundary_is_exact(self):
        self.assertTrue(outer_scroll_enabled(1869))
        self.assertFalse(outer_scroll_enabled(1870))
        self.assertFalse(outer_scroll_enabled(1871))

    def test_outer_wheel_routing_is_disabled_at_or_above_1870(self):
        app = object.__new__(gui.App)
        app.canvas = Mock()
        app._outer_scroll_enabled = Mock(return_value=False)
        self.assertEqual(app._scroll_outer_viewport(1), 'break')
        app.canvas.yview_scroll.assert_not_called()

    def test_outer_wheel_routing_is_enabled_below_1870(self):
        app = object.__new__(gui.App)
        app.canvas = Mock()
        app._outer_scroll_enabled = Mock(return_value=True)
        self.assertEqual(app._scroll_outer_viewport(1), 'break')
        app.canvas.yview_scroll.assert_called_once_with(1, 'units')

    def test_scrollbar_policy_hides_and_resets_outer_canvas_at_or_above_1870(self):
        app = object.__new__(gui.App)
        app.canvas = Mock()
        app.scrollbar = Mock()
        app.scrollbar.winfo_manager.return_value = 'pack'
        app._outer_scroll_enabled = Mock(return_value=False)
        app._sync_outer_scroll_policy()
        app.canvas.yview_moveto.assert_called_once_with(0.0)
        app.scrollbar.pack_forget.assert_called_once_with()

    def test_scrollbar_policy_restores_outer_scrollbar_below_1870(self):
        app = object.__new__(gui.App)
        app.canvas = Mock()
        app.scrollbar = Mock()
        app.scrollbar.winfo_manager.return_value = ''
        app._outer_scroll_enabled = Mock(return_value=True)
        app._sync_outer_scroll_policy()
        app.scrollbar.pack.assert_called_once_with(side='right', fill='y')
        app.canvas.yview_moveto.assert_not_called()

    def test_non_windows_visible_height_falls_back_to_tk_height(self):
        root = Mock()
        root.winfo_height.return_value = 1440
        with patch.object(gui.os, 'name', 'posix'):
            self.assertEqual(visible_window_height_px(root), 1440)

    def test_app_outer_scroll_mode_uses_visible_physical_window_height_adapter(self):
        app = object.__new__(gui.App)
        app.root = Mock()
        with patch.object(gui, 'visible_window_height_px', return_value=1869):
            self.assertTrue(app._outer_scroll_enabled())
        with patch.object(gui, 'visible_window_height_px', return_value=1870):
            self.assertFalse(app._outer_scroll_enabled())

    def test_windows_runtime_probe_is_shipped(self):
        probe = inspect.getsource(gui.visible_window_height_px)
        self.assertIn('DwmGetWindowAttribute', probe)
        self.assertIn('DWMWA_EXTENDED_FRAME_BOUNDS', probe)

if __name__ == '__main__':
    unittest.main()
