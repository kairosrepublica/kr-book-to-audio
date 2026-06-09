import inspect
import unittest
from kr_book_to_audio import gui
from kr_book_to_audio.gui import preserves_native_wheel, wheel_scroll_units

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

if __name__ == '__main__':
    unittest.main()
