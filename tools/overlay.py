"""
Floating JARVIS status overlay for macOS.

Always visible in the top-right corner. Changes appearance to reflect state:
  STANDBY   → dim border, quiet dot
  LISTENING → bright cyan, pulsing ring
  THINKING  → amber, spinning dots
  SPEAKING  → cyan-green, animated bars

Runs on the main thread via tkinter mainloop().
All state changes from other threads go through a thread-safe queue.
"""

from __future__ import annotations

import math
import queue
import threading
import tkinter as tk
from enum import Enum


class State(Enum):
    STANDBY   = "standby"
    LISTENING = "listening"
    THINKING  = "thinking"
    SPEAKING  = "speaking"


# Palette
_COLORS = {
    State.STANDBY:   {"border": "#0f3460", "accent": "#1e3a5f", "text": "#2a5080", "label": "STANDBY"},
    State.LISTENING: {"border": "#00d4ff", "accent": "#00d4ff", "text": "#00d4ff", "label": "LISTENING"},
    State.THINKING:  {"border": "#ffaa00", "accent": "#ffaa00", "text": "#ffaa00", "label": "PROCESSING"},
    State.SPEAKING:  {"border": "#64ffda", "accent": "#64ffda", "text": "#64ffda", "label": "SPEAKING"},
}

W, H = 240, 64


class JarvisOverlay:
    def __init__(self) -> None:
        self._state   = State.STANDBY
        self._queue:  queue.Queue[State] = queue.Queue()
        self._tick    = 0
        self._root:   tk.Tk | None = None
        self._canvas: tk.Canvas | None = None

    # ── Public API (thread-safe) ──────────────────────────────────────────

    def set_state(self, state: State) -> None:
        self._queue.put(state)

    def stop(self) -> None:
        if self._root:
            self._root.after(0, self._root.destroy)

    # ── Setup ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the tkinter mainloop — MUST be called from the main thread."""
        self._root = root = tk.Tk()

        root.overrideredirect(True)           # no title bar / chrome
        root.attributes("-topmost", True)     # float above all windows
        root.attributes("-alpha", 0.93)
        root.configure(bg="#020c1b")

        # Position: top-right, 20 px from screen edge
        sw = root.winfo_screenwidth()
        root.geometry(f"{W}x{H}+{sw - W - 20}+20")

        self._canvas = tk.Canvas(
            root, width=W, height=H,
            bg="#020c1b", highlightthickness=0,
        )
        self._canvas.pack()

        # Allow dragging with left-click
        self._canvas.bind("<ButtonPress-1>",   self._drag_start)
        self._canvas.bind("<B1-Motion>",        self._drag_move)

        self._loop()
        root.mainloop()

    # ── Drag support ──────────────────────────────────────────────────────

    def _drag_start(self, event) -> None:
        self._dx, self._dy = event.x, event.y

    def _drag_move(self, event) -> None:
        if self._root:
            x = self._root.winfo_x() + event.x - self._dx
            y = self._root.winfo_y() + event.y - self._dy
            self._root.geometry(f"+{x}+{y}")

    # ── Animation loop ────────────────────────────────────────────────────

    def _loop(self) -> None:
        # Drain state updates
        try:
            while True:
                self._state = self._queue.get_nowait()
        except queue.Empty:
            pass

        self._tick += 1
        self._draw()
        if self._root:
            self._root.after(60, self._loop)   # ~16 fps

    # ── Drawing ───────────────────────────────────────────────────────────

    def _draw(self) -> None:
        c = self._canvas
        if c is None:
            return
        c.delete("all")

        col = _COLORS[self._state]
        t   = self._tick
        bg  = "#020c1b"

        # ── Background ────────────────────────────────────────────────
        c.create_rectangle(0, 0, W, H, fill=bg, outline="")

        # ── Glow fill when active ──────────────────────────────────────
        if self._state != State.STANDBY:
            pulse = 0.04 + 0.02 * math.sin(t * 0.15)
            glow_hex = self._alpha_fill(col["border"], pulse)
            c.create_rectangle(2, 2, W - 2, H - 2, fill=glow_hex, outline="")

        # ── Outer border ───────────────────────────────────────────────
        c.create_rectangle(1, 1, W - 1, H - 1, outline=col["border"], width=1)

        # ── Corner brackets ────────────────────────────────────────────
        sz = 10
        for (x1, y1), (x2, y2), (x3, y3) in [
            ((1,1+sz),(1,1),(1+sz,1)),
            ((W-1-sz,1),(W-1,1),(W-1,1+sz)),
            ((1,H-1-sz),(1,H-1),(1+sz,H-1)),
            ((W-1-sz,H-1),(W-1,H-1),(W-1,H-1-sz)),
        ]:
            c.create_line(x1,y1,x2,y2,x3,y3, fill=col["accent"], width=1.5)

        # ── Logo ───────────────────────────────────────────────────────
        c.create_text(
            14, H // 2 - 6,
            text="J.A.R.V.I.S.",
            anchor="w",
            font=("Courier New", 11, "bold"),
            fill=col["text"],
        )

        # ── State indicator (right side) ───────────────────────────────
        self._draw_indicator(c, col, t)

        # ── State label ────────────────────────────────────────────────
        c.create_text(
            14, H // 2 + 8,
            text=col["label"],
            anchor="w",
            font=("Courier New", 7),
            fill=col["text"],
        )

    def _draw_indicator(self, c, col, t) -> None:
        cx, cy = W - 26, H // 2

        if self._state == State.STANDBY:
            # Dim small circle
            c.create_oval(cx - 4, cy - 4, cx + 4, cy + 4,
                          fill="#0f3460", outline="#1e3a5f")

        elif self._state == State.LISTENING:
            # Pulsing concentric rings
            r_outer = 14 + 4 * math.sin(t * 0.2)
            r_inner = 8  + 2 * math.sin(t * 0.2 + 1)
            alpha_o = 0.25 + 0.15 * math.sin(t * 0.2)
            c.create_oval(cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer,
                          outline=self._alpha_fill(col["accent"], alpha_o), width=1)
            c.create_oval(cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner,
                          outline=col["accent"], width=1)
            c.create_oval(cx - 4, cy - 4, cx + 4, cy + 4,
                          fill=col["accent"], outline="")

        elif self._state == State.THINKING:
            # Three spinning dots
            for i in range(3):
                angle = math.radians(t * 6 + i * 120)
                dx = 9 * math.cos(angle)
                dy = 9 * math.sin(angle)
                bright = 0.5 + 0.5 * math.sin(t * 0.2 + i * 2)
                r = 3 + bright
                c.create_oval(
                    cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r,
                    fill=col["accent"], outline="",
                )

        elif self._state == State.SPEAKING:
            # Animated equaliser bars
            for i, base_h in enumerate([5, 9, 12, 9, 5]):
                bx = cx - 10 + i * 5
                bh = base_h + 4 * math.sin(t * 0.25 + i * 0.8)
                c.create_rectangle(
                    bx, cy - bh, bx + 3, cy + bh,
                    fill=col["accent"], outline="",
                )

    @staticmethod
    def _alpha_fill(hex_color: str, alpha: float) -> str:
        """Blend hex_color toward #020c1b background by alpha."""
        fg = tuple(int(hex_color[i:i+2], 16) for i in (1, 3, 5))
        bg = (2, 12, 27)
        blended = tuple(int(bg[j] + (fg[j] - bg[j]) * alpha) for j in range(3))
        return "#{:02x}{:02x}{:02x}".format(*blended)
