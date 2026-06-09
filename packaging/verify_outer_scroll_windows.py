#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if os.name != "nt":
    raise SystemExit("Windows target runtime required.")

import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from kr_book_to_audio.gui import App, visible_window_height_px


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def refresh(root: tk.Tk) -> None:
    root.update_idletasks()
    root.update()


def build_probe(root: tk.Tk):
    viewport = ttk.Frame(root)
    viewport.pack(fill="both", expand=True)
    canvas = tk.Canvas(viewport, highlightthickness=0)
    scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    frame = ttk.Frame(canvas)
    canvas_window = canvas.create_window((0, 0), window=frame, anchor="nw")
    for index in range(240):
        ttk.Label(frame, text=f"Outer workflow probe row {index:03d}").pack(anchor="w")
    frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(canvas_window, width=event.width))
    refresh(root)
    app = object.__new__(App)
    app.root = root
    app.canvas = canvas
    app.scrollbar = scrollbar
    return app, canvas, scrollbar


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    evidence_path = Path(args.evidence)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)

    root = tk.Tk()
    root.title("KR Book To Audio outer-scroll runtime probe")
    root.geometry("900x1200+20+20")
    try:
        app, canvas, scrollbar = build_probe(root)

        root.state("zoomed")
        refresh(root)
        high_height = visible_window_height_px(root)
        require(high_height >= 1870, f"High-window probe could not reach 1870 physical px: {high_height}")
        app._sync_outer_scroll_policy()
        refresh(root)
        high_before = canvas.yview()
        high_result = app._scroll_outer_viewport(8)
        refresh(root)
        high_after = canvas.yview()
        high_scrollbar_manager = scrollbar.winfo_manager()
        require(high_scrollbar_manager == "", f"High-window outer scrollbar remained visible: {high_scrollbar_manager!r}")
        require(high_result == "break", f"High-window wheel routing was not suppressed: {high_result!r}")
        require(high_before == high_after, f"High-window outer viewport moved: before={high_before}; after={high_after}")

        root.state("normal")
        root.geometry("900x1200+20+20")
        refresh(root)
        low_height = visible_window_height_px(root)
        require(low_height < 1870, f"Low-window probe did not fall below 1870 physical px: {low_height}")
        app._sync_outer_scroll_policy()
        canvas.yview_moveto(0.0)
        refresh(root)
        low_before = canvas.yview()
        low_result = app._scroll_outer_viewport(8)
        refresh(root)
        low_after = canvas.yview()
        low_scrollbar_manager = scrollbar.winfo_manager()
        require(low_scrollbar_manager == "pack", f"Low-window outer scrollbar was not restored: {low_scrollbar_manager!r}")
        require(low_result == "break", f"Low-window wheel routing was not enabled: {low_result!r}")
        require(low_before != low_after, f"Low-window outer viewport did not move: before={low_before}; after={low_after}")

        evidence = {
            "ok": True,
            "high_window": {
                "physical_visible_height_px": high_height,
                "scrollbar_manager": high_scrollbar_manager,
                "wheel_result": high_result,
                "yview_before": high_before,
                "yview_after": high_after,
            },
            "low_window": {
                "physical_visible_height_px": low_height,
                "scrollbar_manager": low_scrollbar_manager,
                "wheel_result": low_result,
                "yview_before": low_before,
                "yview_after": low_after,
            },
        }
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(evidence, indent=2, sort_keys=True))
        print("TARGET_RUNTIME_FIXTURE PASS: real Windows outer-scroll interaction probe")
        return 0
    finally:
        root.destroy()


if __name__ == "__main__":
    raise SystemExit(main())
