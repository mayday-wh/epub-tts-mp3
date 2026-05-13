from __future__ import annotations

import asyncio
import ctypes
import queue
import re
import sys
import threading
from pathlib import Path
from tkinter import BooleanVar, StringVar, filedialog, messagebox
import tkinter.font as tkfont
import tkinter as tk
from tkinter import ttk

from epub_tts import (
    Chapter,
    DEFAULT_PITCH,
    DEFAULT_RATE,
    DEFAULT_VOLUME,
    MAX_TTS_CHARS,
    concat_mp3_with_ffmpeg,
    parse_epub,
    safe_filename,
    split_text,
    stream_tts_chunk,
    write_text_preview,
)


APP_VERSION = "1.1"

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # Drag-and-drop is optional; file picker still works.
    DND_FILES = None
    TkinterDnD = None


VOICE_OPTIONS = [
    ("云扬 男声 - 稳重", "zh-CN-YunyangNeural"),
    ("云希 男声 - 轻快", "zh-CN-YunxiNeural"),
    ("云健 男声 - 清晰", "zh-CN-YunjianNeural"),
    ("云夏 男声 - 年轻", "zh-CN-YunxiaNeural"),
    ("晓晓 女声 - 自然", "zh-CN-XiaoxiaoNeural"),
    ("晓伊 女声 - 温和", "zh-CN-XiaoyiNeural"),
]


def draw_rounded_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs) -> int:
    points = [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command,
        width: int,
        height: int,
        radius: int,
        bg: str,
        fill: str,
        active_fill: str,
        disabled_fill: str,
        fg: str,
        disabled_fg: str = "#f8fafc",
    ) -> None:
        super().__init__(master, width=width, height=height, bg=bg, highlightthickness=0, bd=0)
        self.command = command
        self.width_px = width
        self.height_px = height
        self.radius = radius
        self.fill = fill
        self.active_fill = active_fill
        self.disabled_fill = disabled_fill
        self.fg = fg
        self.disabled_fg = disabled_fg
        self.state = "normal"
        self.text = text
        self.bg_color = bg
        self.configure(cursor="hand2")
        self._draw(self.fill, self.fg)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_click)

    def configure(self, cnf=None, **kwargs):  # type: ignore[override]
        if cnf:
            kwargs.update(cnf)
        if "state" in kwargs:
            self.state = kwargs.pop("state")
            if self.state == "disabled":
                self.configure(cursor="arrow")
                self._draw(self.disabled_fill, self.disabled_fg)
            else:
                self.configure(cursor="hand2")
                self._draw(self.fill, self.fg)
        if "text" in kwargs:
            self.text = kwargs.pop("text")
            self._draw(self.fill if self.state != "disabled" else self.disabled_fill, self.fg if self.state != "disabled" else self.disabled_fg)
        if kwargs:
            return super().configure(**kwargs)
        return None

    config = configure

    def _draw(self, fill: str, fg: str) -> None:
        self.delete("all")
        draw_rounded_rect(self, 1, 1, self.width_px - 1, self.height_px - 1, self.radius, fill=fill, outline="")
        self.create_text(self.width_px // 2, self.height_px // 2, text=self.text, fill=fg, font=("Microsoft YaHei UI", 10, "bold"))

    def _on_enter(self, event: tk.Event) -> None:
        if self.state != "disabled":
            self._draw(self.active_fill, self.fg)

    def _on_leave(self, event: tk.Event) -> None:
        if self.state != "disabled":
            self._draw(self.fill, self.fg)

    def _on_click(self, event: tk.Event) -> None:
        if self.state != "disabled" and self.command:
            self.command()


class TinyStepper(tk.Canvas):
    def __init__(
        self,
        master: tk.Misc,
        up_command,
        down_command,
        width: int,
        height: int,
        bg: str,
        border: str,
        fg: str,
    ) -> None:
        super().__init__(master, width=width, height=height, bg=bg, highlightthickness=0, bd=0)
        self.up_command = up_command
        self.down_command = down_command
        self.width_px = width
        self.height_px = height
        self.bg_color = bg
        self.border = border
        self.fg = fg
        self.configure(cursor="hand2")
        self.bind("<Configure>", self._draw)
        self.bind("<ButtonRelease-1>", self._click)

    def _draw(self, event: tk.Event | None = None) -> None:
        width = max(self.winfo_width(), self.width_px)
        height = max(self.winfo_height(), self.height_px)
        mid = height // 2
        self.delete("all")
        self.create_rectangle(0, 0, width - 1, height - 1, fill="#ffffff", outline=self.border)
        self.create_line(0, mid, width, mid, fill=self.border)
        self.create_text(width // 2, mid // 2, text="▲", fill=self.fg, font=("Microsoft YaHei UI", 7, "bold"))
        self.create_text(width // 2, mid + (height - mid) // 2, text="▼", fill=self.fg, font=("Microsoft YaHei UI", 7, "bold"))

    def _click(self, event: tk.Event) -> None:
        if event.y < self.winfo_height() // 2:
            self.up_command()
        else:
            self.down_command()


def enable_high_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def configure_tk_scaling(root: tk.Tk) -> float:
    try:
        dpi = float(root.winfo_fpixels("1i"))
    except tk.TclError:
        dpi = 96.0
    if dpi <= 0:
        dpi = 96.0
    scale = max(1.0, dpi / 96.0)
    root.tk.call("tk", "scaling", dpi / 72.0)
    setattr(root, "_epub_tts_ui_scale", scale)
    return scale


class EpubTtsApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.ui_scale = float(getattr(root, "_epub_tts_ui_scale", 1.0))
        self.root.title(f"EPUB 转 MP3 v{APP_VERSION}")
        self.root.geometry(f"{self._px(840)}x{self._px(600)}")
        self.root.minsize(self._px(780), self._px(520))

        self.message_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.epub_path: Path | None = None
        self.book_title = ""
        self.chapters: list[Chapter] = []
        self.checked: set[int] = set()
        self.is_working = False
        self.worker_failed = False

        self.voice_var = StringVar(value=VOICE_OPTIONS[0][1])
        self.rate_var = StringVar(value=DEFAULT_RATE)
        self.pitch_var = StringVar(value=DEFAULT_PITCH)
        self.volume_var = StringVar(value=DEFAULT_VOLUME)
        self.output_var = StringVar()
        self.merge_var = BooleanVar(value=True)
        self.overwrite_var = BooleanVar(value=False)
        self.status_var = StringVar(value="拖入 EPUB 文件，或点击“选择 EPUB”。")
        self.progress_var = tk.DoubleVar(value=0)

        self._configure_style()
        self._build_ui()
        self._bind_drop()
        self.root.after(100, self._poll_messages)

    def _px(self, value: int | float) -> int:
        return max(1, int(round(value * self.ui_scale)))

    def _pad(self, *values: int) -> tuple[int, ...]:
        return tuple(self._px(value) for value in values)

    def _configure_style(self) -> None:
        self.colors = {
            "bg": "#f4f6fb",
            "panel": "#ffffff",
            "panel_soft": "#eef3fb",
            "text_section": "#eef6ff",
            "voice_section": "#eefaf2",
            "list_section": "#fbf8ff",
            "drop": "#dbeafe",
            "drop_border": "#93c5fd",
            "border": "#d8e0ec",
            "text": "#182230",
            "muted": "#64748b",
            "accent": "#2563eb",
            "accent_dark": "#1d4ed8",
            "success": "#16825d",
            "row_alt": "#f8fafc",
            "row_selected": "#e8f1ff",
        }
        self.root.configure(bg=self.colors["bg"])
        self.default_font = tkfont.nametofont("TkDefaultFont")
        self.default_font.configure(family="Microsoft YaHei UI", size=10)
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=self.default_font, background=self.colors["bg"], foreground=self.colors["text"])
        style.configure("App.TFrame", background=self.colors["bg"])
        style.configure("Panel.TFrame", background=self.colors["panel"], relief="flat")
        style.configure("List.TFrame", background=self.colors["list_section"], relief="flat")
        style.configure("Soft.TFrame", background=self.colors["panel_soft"])
        style.configure("Muted.TLabel", background=self.colors["panel"], foreground=self.colors["muted"])
        style.configure("Section.TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("ListSection.TLabel", background=self.colors["list_section"], foreground=self.colors["text"], font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("ListMuted.TLabel", background=self.colors["list_section"], foreground=self.colors["muted"])
        style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["text"])
        style.configure("TCheckbutton", background=self.colors["panel"], foreground=self.colors["text"])
        style.configure("TEntry", padding=self._pad(7, 5), fieldbackground="#ffffff", bordercolor=self.colors["border"], lightcolor=self.colors["border"], darkcolor=self.colors["border"])
        style.configure("TCombobox", padding=self._pad(7, 5), fieldbackground="#ffffff", bordercolor=self.colors["border"], arrowcolor=self.colors["muted"])
        style.configure("TButton", padding=self._pad(10, 8), background="#ffffff", foreground=self.colors["text"], bordercolor=self.colors["border"])
        style.map("TButton", background=[("active", "#eef3fb")])
        style.configure("Accent.TButton", padding=self._pad(10, 8), background=self.colors["accent"], foreground="#ffffff", bordercolor=self.colors["accent"])
        style.map("Accent.TButton", background=[("active", self.colors["accent_dark"]), ("disabled", "#9bb7ef")], foreground=[("disabled", "#edf2ff")])
        style.configure("Ghost.TButton", padding=self._pad(10, 8), background=self.colors["panel"], foreground=self.colors["text"], bordercolor=self.colors["border"])
        style.configure("File.TButton", padding=self._pad(10, 8), background="#dbeafe", foreground="#1e3a8a", bordercolor="#93c5fd")
        style.map("File.TButton", background=[("active", "#bfdbfe"), ("disabled", "#dbeafe")])
        style.configure("Select.TButton", padding=self._pad(10, 8), background="#dcfce7", foreground="#14532d", bordercolor="#86efac")
        style.map("Select.TButton", background=[("active", "#bbf7d0"), ("disabled", "#dcfce7")])
        style.configure("Export.TButton", padding=self._pad(10, 8), background="#2563eb", foreground="#ffffff", bordercolor="#1d4ed8")
        style.map("Export.TButton", background=[("active", "#1d4ed8"), ("disabled", "#9bb7ef")], foreground=[("disabled", "#edf2ff")])
        style.configure("Step.TButton", padding=self._pad(1, 0), background="#ffffff", foreground=self.colors["text"], bordercolor=self.colors["border"])
        style.map("Step.TButton", background=[("active", "#eef3fb")])
        style.configure("Horizontal.TProgressbar", background=self.colors["accent"], troughcolor="#e3e9f3", bordercolor="#e3e9f3", lightcolor=self.colors["accent"], darkcolor=self.colors["accent"])
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground=self.colors["text"], rowheight=self._px(28), bordercolor=self.colors["border"])
        style.configure("Treeview.Heading", background="#eef3fb", foreground="#334155", padding=self._pad(7, 6), font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", self.colors["text"])])

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self.root, style="Panel.TFrame", padding=(12, 8, 12, 8))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(8, weight=1)
        button_w = self._px(116)
        button_h = self._px(38)
        radius = self._px(10)
        RoundedButton(toolbar, "选择 EPUB", self.choose_epub, button_w, button_h, radius, self.colors["panel"], "#dbeafe", "#bfdbfe", "#dbeafe", "#1e3a8a").grid(row=0, column=0, sticky="w")
        RoundedButton(toolbar, "选择输出目录", self.choose_output, button_w, button_h, radius, self.colors["panel"], "#dbeafe", "#bfdbfe", "#dbeafe", "#1e3a8a").grid(row=0, column=1, sticky="w", padx=(8, 0))
        RoundedButton(toolbar, "全选", self.select_all, button_w, button_h, radius, self.colors["panel"], "#dcfce7", "#bbf7d0", "#dcfce7", "#14532d").grid(row=0, column=2, sticky="w", padx=(18, 0))
        RoundedButton(toolbar, "全不选", self.select_none, button_w, button_h, radius, self.colors["panel"], "#dcfce7", "#bbf7d0", "#dcfce7", "#14532d").grid(row=0, column=3, sticky="w", padx=(8, 0))
        RoundedButton(toolbar, "正文推荐", self.select_body_guess, button_w, button_h, radius, self.colors["panel"], "#dcfce7", "#bbf7d0", "#dcfce7", "#14532d").grid(row=0, column=4, sticky="w", padx=(8, 0))
        self.export_button = RoundedButton(toolbar, "导出 MP3", self.export_mp3, button_w, button_h, radius, self.colors["panel"], "#2563eb", "#1d4ed8", "#9bb7ef", "#ffffff")
        self.export_button.grid(row=0, column=5, sticky="w", padx=(18, 0))

        content = ttk.Frame(self.root, style="App.TFrame", padding=(8, 8, 8, 8))
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=0, minsize=self._px(280))
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        left = ttk.Frame(content, style="App.TFrame")
        left.configure(width=self._px(280))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.grid_propagate(False)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1, uniform="left_sections")
        left.rowconfigure(1, weight=1, uniform="left_sections")

        text_section = tk.Frame(left, bg=self.colors["text_section"], highlightbackground=self.colors["border"], highlightthickness=1)
        text_section.grid(row=0, column=0, sticky="nsew")
        text_section.columnconfigure(0, weight=1)
        tk.Label(text_section, text="文本选择", bg=self.colors["text_section"], fg=self.colors["text"], font=("Microsoft YaHei UI", 11, "bold"), anchor="w").grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        drop_panel = tk.Canvas(text_section, bg=self.colors["text_section"], highlightthickness=0, height=self._px(136))
        drop_panel.grid(row=1, column=0, sticky="ew", padx=10, pady=(8, 0))
        drop_panel.columnconfigure(0, weight=1)
        self.drop_label = drop_panel
        self.drop_label.bind("<Configure>", self._draw_drop_area)

        file_row = tk.Frame(text_section, bg=self.colors["text_section"])
        file_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(8, 0))
        file_row.columnconfigure(0, weight=1)
        self.file_label = tk.Label(file_row, text="未选择文件", bg=self.colors["text_section"], fg=self.colors["muted"], anchor="w")
        self.file_label.grid(row=0, column=0, sticky="ew")

        output_row = tk.Frame(text_section, bg=self.colors["text_section"])
        output_row.grid(row=3, column=0, sticky="ew", padx=10, pady=(10, 10))
        output_row.columnconfigure(0, weight=1)
        tk.Label(output_row, text="输出目录", bg=self.colors["text_section"], fg=self.colors["text"], anchor="w").grid(row=0, column=0, sticky="w")
        ttk.Entry(output_row, textvariable=self.output_var).grid(row=1, column=0, sticky="ew", pady=(4, 0))

        voice_section = tk.Frame(left, bg=self.colors["voice_section"], highlightbackground=self.colors["border"], highlightthickness=1)
        voice_section.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        voice_section.columnconfigure(0, weight=1)
        tk.Label(voice_section, text="音色选择", bg=self.colors["voice_section"], fg=self.colors["text"], font=("Microsoft YaHei UI", 11, "bold"), anchor="w").grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        tk.Label(voice_section, text="音色", bg=self.colors["voice_section"], fg=self.colors["text"], anchor="w").grid(row=1, column=0, sticky="w", padx=10, pady=(8, 0))
        voice_box = ttk.Combobox(voice_section, textvariable=self.voice_var, values=[f"{name} | {value}" for name, value in VOICE_OPTIONS], state="readonly", width=1)
        voice_box.grid(row=2, column=0, sticky="ew", padx=10, pady=(4, 0))
        voice_box.current(0)
        voice_box.bind("<<ComboboxSelected>>", self._voice_selected)

        params = tk.Frame(voice_section, bg=self.colors["voice_section"])
        params.grid(row=3, column=0, sticky="ew", padx=10, pady=(10, 0))
        for col in (0, 1, 2):
            params.columnconfigure(col, weight=1)
        tk.Label(params, text="语速", bg=self.colors["voice_section"], fg=self.colors["text"], anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(params, text="音调", bg=self.colors["voice_section"], fg=self.colors["text"], anchor="w").grid(row=0, column=1, sticky="w", padx=(10, 0))
        tk.Label(params, text="音量", bg=self.colors["voice_section"], fg=self.colors["text"], anchor="w").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self._build_stepper(params, self.rate_var, "%", 5).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._build_stepper(params, self.pitch_var, "Hz", 5).grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(4, 0))
        self._build_stepper(params, self.volume_var, "%", 5).grid(row=1, column=2, sticky="ew", padx=(10, 0), pady=(4, 0))

        options = tk.Frame(voice_section, bg=self.colors["voice_section"])
        options.grid(row=4, column=0, sticky="ew", padx=10, pady=(12, 10))
        tk.Checkbutton(options, text="合并整本 MP3", variable=self.merge_var, bg=self.colors["voice_section"], fg=self.colors["text"], activebackground=self.colors["voice_section"], selectcolor="#ffffff", anchor="w").pack(anchor="w")
        tk.Checkbutton(options, text="覆盖已有章节 MP3", variable=self.overwrite_var, bg=self.colors["voice_section"], fg=self.colors["text"], activebackground=self.colors["voice_section"], selectcolor="#ffffff", anchor="w").pack(anchor="w", pady=(6, 0))

        table_frame = ttk.Frame(content, style="List.TFrame", padding=(14, 12, 14, 12))
        table_frame.grid(row=0, column=1, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(1, weight=1)

        table_header = ttk.Frame(table_frame, style="List.TFrame")
        table_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        table_header.columnconfigure(0, weight=1)
        ttk.Label(table_header, text="章节选择", style="ListSection.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(table_header, text="点击章节行即可勾选或取消", style="ListMuted.TLabel").grid(row=0, column=1, sticky="e")

        columns = ("use", "index", "title")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("use", text="选")
        self.tree.heading("index", text="#")
        self.tree.heading("title", text="章节")
        self.tree.column("use", width=self._px(64), minwidth=self._px(64), anchor="center", stretch=False)
        self.tree.column("index", width=self._px(72), minwidth=self._px(72), anchor="center", stretch=False)
        self.tree.column("title", width=760, minwidth=360, anchor="w", stretch=True)
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<ButtonRelease-1>", self._tree_clicked)
        self.tree.bind("<space>", self._toggle_selected_event)
        self.tree.bind("<MouseWheel>", self._on_tree_mousewheel)
        self.tree.bind("<Button-4>", self._on_tree_mousewheel)
        self.tree.bind("<Button-5>", self._on_tree_mousewheel)
        self.tree.tag_configure("checked", background=self.colors["row_selected"])
        self.tree.tag_configure("odd", background=self.colors["row_alt"])
        self.tree.tag_configure("even", background="#ffffff")

        self.progress_canvas = tk.Canvas(table_frame, height=self._px(34), bg=self.colors["list_section"], highlightthickness=0, bd=0)
        self.progress_canvas.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.progress_canvas.bind("<Configure>", self._draw_progress_bar)
        self._draw_progress_bar()

    def _bind_drop(self) -> None:
        if TkinterDnD is None or DND_FILES is None:
            return
        for widget in (self.root, self.drop_label):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._drop_file)

    def _draw_drop_area(self, event: tk.Event | None = None) -> None:
        canvas = self.drop_label
        if not isinstance(canvas, tk.Canvas):
            return
        width = max(canvas.winfo_width(), self._px(240))
        height = max(canvas.winfo_height(), self._px(120))
        canvas.delete("all")
        draw_rounded_rect(
            canvas,
            self._px(1),
            self._px(1),
            width - self._px(1),
            height - self._px(1),
            self._px(14),
            fill=self.colors["drop"],
            outline=self.colors["drop_border"],
        )
        canvas.create_text(
            width // 2,
            height // 2,
            text=".epub 拖到这里",
            fill=self.colors["accent_dark"],
            font=("Microsoft YaHei UI", 10, "bold"),
        )

    def _draw_progress_bar(self, event: tk.Event | None = None) -> None:
        canvas = getattr(self, "progress_canvas", None)
        if not isinstance(canvas, tk.Canvas):
            return
        width = max(canvas.winfo_width(), self._px(240))
        height = max(canvas.winfo_height(), self._px(34))
        value = max(0.0, min(100.0, float(self.progress_var.get())))
        left = self._px(12)
        right = width - self._px(12)
        center_y = height // 2
        track_h = self._px(8)
        radius = self._px(4)
        fill_x = left + int((right - left) * value / 100.0)

        canvas.delete("all")
        draw_rounded_rect(
            canvas,
            left,
            center_y - track_h // 2,
            right,
            center_y + track_h // 2,
            radius,
            fill="#e2e8f0",
            outline="",
        )
        if value > 0:
            draw_rounded_rect(
                canvas,
                left,
                center_y - track_h // 2,
                max(fill_x, left + self._px(2)),
                center_y + track_h // 2,
                radius,
                fill=self.colors["accent"],
                outline="",
            )
        canvas.create_text(
            fill_x,
            center_y,
            text="🎧",
            fill=self.colors["accent_dark"],
            font=("Segoe UI Emoji", max(12, self._px(11))),
        )

    def _build_stepper(self, parent: tk.Misc, variable: StringVar, unit: str, step: int) -> ttk.Frame:
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        ttk.Entry(frame, textvariable=variable, width=6).grid(row=0, column=0, sticky="nsew")
        TinyStepper(
            frame,
            up_command=lambda: self._adjust_value(variable, unit, step),
            down_command=lambda: self._adjust_value(variable, unit, -step),
            width=self._px(16),
            height=self._px(34),
            bg=self.colors["voice_section"],
            border=self.colors["border"],
            fg=self.colors["text"],
        ).grid(row=0, column=1, sticky="ns")
        return frame

    def _adjust_value(self, variable: StringVar, unit: str, delta: int) -> None:
        current = variable.get().strip()
        match = re.match(r"^([+-]?\d+)\s*(%|Hz)?$", current)
        if match:
            value = int(match.group(1))
        else:
            value = 0
        value += delta
        if unit == "%":
            value = max(-100, min(100, value))
            variable.set(f"{value:+d}%")
        else:
            value = max(-100, min(100, value))
            variable.set(f"{value:+d}Hz")

    def _voice_selected(self, event: object | None = None) -> None:
        return

    def _current_voice(self) -> str:
        value = self.voice_var.get()
        if "|" in value:
            return value.split("|", 1)[1].strip()
        return value.strip()

    def _drop_file(self, event: object) -> None:
        raw = getattr(event, "data", "")
        files = self.root.tk.splitlist(raw)
        if files:
            self.load_epub(Path(files[0]))

    def choose_epub(self) -> None:
        file_name = filedialog.askopenfilename(
            title="选择 EPUB",
            filetypes=[("EPUB 文件", "*.epub"), ("所有文件", "*.*")],
        )
        if file_name:
            self.load_epub(Path(file_name))

    def choose_output(self) -> None:
        if self.is_working:
            messagebox.showinfo("正在处理", "当前任务还没结束。")
            return
        folder = filedialog.askdirectory(title="选择输出目录")
        if folder:
            self.output_var.set(folder)

    def load_epub(self, path: Path) -> None:
        if self.is_working:
            messagebox.showinfo("正在处理", "当前任务还没结束。")
            return
        if path.suffix.lower() != ".epub":
            messagebox.showerror("文件格式不支持", "请选择 .epub 文件。")
            return
        self._start_worker(self._load_epub_worker, path)

    def _load_epub_worker(self, path: Path) -> None:
        self.message_queue.put(("status", "正在读取 EPUB..."))
        book = parse_epub(path, min_chars=30)
        output_dir = path.with_suffix("")
        output_dir.mkdir(parents=True, exist_ok=True)
        write_text_preview(book, output_dir)
        self.message_queue.put(("loaded", (path, book.title, book.chapters, output_dir)))

    def _render_chapters(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, chapter in enumerate(self.chapters, start=1):
            item_index = index - 1
            mark = "✓" if item_index in self.checked else ""
            tags = ("checked",) if item_index in self.checked else ("odd" if index % 2 else "even",)
            self.tree.insert(
                "",
                "end",
                iid=str(item_index),
                values=(mark, f"{index:03d}", chapter.title),
                tags=tags,
            )

    def _tree_clicked(self, event: tk.Event) -> None:
        row_id = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if row_id and col in ("#1", "#2", "#3"):
            self._toggle_index(int(row_id))

    def _toggle_selected_event(self, event: object | None = None) -> str:
        selected = self.tree.selection()
        if selected:
            self._toggle_index(int(selected[0]))
        return "break"

    def _on_tree_mousewheel(self, event: tk.Event) -> str:
        if getattr(event, "num", None) == 4:
            self.tree.yview_scroll(-3, "units")
        elif getattr(event, "num", None) == 5:
            self.tree.yview_scroll(3, "units")
        else:
            delta = int(-1 * (event.delta / 120))
            self.tree.yview_scroll(delta * 3, "units")
        return "break"

    def _toggle_index(self, index: int) -> None:
        if self.is_working:
            return
        if index in self.checked:
            self.checked.remove(index)
        else:
            self.checked.add(index)
        self._render_chapters()
        self.tree.selection_set(str(index))
        self._update_selected_status()

    def select_all(self) -> None:
        if self.is_working:
            return
        self.checked = set(range(len(self.chapters)))
        self._render_chapters()
        self._update_selected_status()

    def select_none(self) -> None:
        if self.is_working:
            return
        self.checked.clear()
        self._render_chapters()
        self._update_selected_status()

    def select_body_guess(self) -> None:
        if self.is_working:
            return
        self.checked = self._body_guess_indices()
        self._render_chapters()
        self._update_selected_status()

    def _body_guess_indices(self) -> set[int]:
        skip_words = ("版权", "目录", "制作声明", "附录")
        selected = set()
        for index, chapter in enumerate(self.chapters):
            if len(chapter.text) < 500:
                continue
            if any(word in chapter.title for word in skip_words):
                continue
            selected.add(index)
        return selected or set(range(len(self.chapters)))

    def selected_chapters(self) -> list[tuple[int, Chapter]]:
        return [(index, self.chapters[index]) for index in sorted(self.checked)]

    def export_mp3(self) -> None:
        if self.is_working:
            return
        selected = self.selected_chapters()
        if not selected:
            messagebox.showinfo("没有选择章节", "请至少勾选一个章节。")
            return
        if self.epub_path is None:
            return
        output_dir = Path(self.output_var.get() or self.epub_path.with_suffix(""))
        self._start_worker(self._export_worker, selected, output_dir, self.merge_var.get(), None, self._settings())

    def _settings(self) -> dict[str, object]:
        return {
            "voice": self._current_voice(),
            "rate": self.rate_var.get(),
            "pitch": self.pitch_var.get(),
            "volume": self.volume_var.get(),
            "overwrite": self.overwrite_var.get(),
        }

    def _start_worker(self, func, *args) -> None:
        self.is_working = True
        self.worker_failed = False
        self.export_button.configure(state="disabled")
        self.progress_var.set(0)
        self._draw_progress_bar()
        thread = threading.Thread(target=self._worker_wrapper, args=(func, args), daemon=True)
        thread.start()

    def _worker_wrapper(self, func, args: tuple[object, ...]) -> None:
        try:
            func(*args)
        except Exception as exc:
            self.worker_failed = True
            self.message_queue.put(("error", exc))
        finally:
            self.message_queue.put(("done", None))

    def _export_worker(
        self,
        selected: list[tuple[int, Chapter]],
        output_dir: Path,
        merge: bool,
        single_filename: str | None,
        settings: dict[str, object],
    ) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        chapters_dir = output_dir / "chapters"
        chapters_dir.mkdir(parents=True, exist_ok=True)
        selected_chapters = [chapter for _, chapter in selected]
        write_text_preview_from_selection(self.book_title, selected_chapters, output_dir)

        chapter_files: list[Path] = []
        total_units = sum(max(1, len(split_text(chapter.text, MAX_TTS_CHARS))) for _, chapter in selected)
        finished_units = 0

        async def run() -> None:
            nonlocal finished_units
            for visible_index, (original_index, chapter) in enumerate(selected, start=1):
                if single_filename:
                    mp3_path = output_dir / single_filename
                else:
                    file_name = safe_filename(f"{visible_index:03d} {chapter.title}", fallback=f"{visible_index:03d}") + ".mp3"
                    mp3_path = chapters_dir / file_name
                chapter_files.append(mp3_path)

                if mp3_path.exists() and not settings["overwrite"] and not single_filename:
                    chunks = split_text(chapter.text, MAX_TTS_CHARS)
                    finished_units += max(1, len(chunks))
                    self.message_queue.put(("progress", (finished_units, total_units, f"跳过：{mp3_path.name}")))
                    continue

                self.message_queue.put(("status", f"正在生成 {visible_index}/{len(selected)}：{chapter.title}"))
                chunks = split_text(chapter.text, MAX_TTS_CHARS)
                temp_path = mp3_path.with_name(mp3_path.name + ".part")
                try:
                    with temp_path.open("wb") as out:
                        for chunk_index, chunk in enumerate(chunks, start=1):
                            await stream_tts_chunk(
                                chunk,
                                out,
                                str(settings["voice"]),
                                str(settings["rate"]),
                                str(settings["pitch"]),
                                str(settings["volume"]),
                            )
                            finished_units += 1
                            label = f"{chapter.title} ({chunk_index}/{len(chunks)})"
                            self.message_queue.put(("progress", (finished_units, total_units, label)))
                    temp_path.replace(mp3_path)
                except Exception:
                    temp_path.unlink(missing_ok=True)
                    raise

        asyncio.run(run())

        playlist = output_dir / "chapters.m3u"
        with playlist.open("w", encoding="utf-8") as f:
            for file in chapter_files:
                f.write(file.resolve().as_posix() + "\n")

        if merge and not single_filename and self.book_title:
            merged = output_dir / (safe_filename(self.book_title, "book") + ".mp3")
            concat_mp3_with_ffmpeg(chapter_files, merged)
            self.message_queue.put(("status", f"完成：{merged}"))
        else:
            self.message_queue.put(("status", f"完成：{output_dir}"))

    def _poll_messages(self) -> None:
        while True:
            try:
                kind, payload = self.message_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                self.status_var.set(str(payload))
            elif kind == "progress":
                done, total, label = payload  # type: ignore[misc]
                percent = (done / total * 100) if total else 0
                self.progress_var.set(percent)
                self._draw_progress_bar()
                self.status_var.set(str(label))
            elif kind == "loaded":
                path, title, chapters, output_dir = payload  # type: ignore[misc]
                self.epub_path = path
                self.book_title = title
                self.chapters = chapters
                self.output_var.set(str(output_dir))
                self.file_label.configure(text=str(path))
                self.checked = self._body_guess_indices()
                self._render_chapters()
                self.status_var.set(f"已读取：{title}，共 {len(chapters)} 个章节。")
            elif kind == "error":
                self.worker_failed = True
                self.status_var.set("发生错误。")
                messagebox.showerror("错误", str(payload))
            elif kind == "done":
                self.is_working = False
                self.export_button.configure(state="normal")
                if self.progress_var.get() > 0 and not self.worker_failed:
                    self.progress_var.set(100)
                    self._draw_progress_bar()
        self.root.after(100, self._poll_messages)

    def _update_selected_status(self) -> None:
        self.status_var.set(f"已选择 {len(self.checked)} / {len(self.chapters)} 个章节。")


def write_text_preview_from_selection(title: str, chapters: list[Chapter], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_path = output_dir / "book_text_preview.txt"
    with preview_path.open("w", encoding="utf-8") as f:
        f.write(title + "\n\n")
        for i, chapter in enumerate(chapters, start=1):
            f.write(f"## {i:03d} {chapter.title}\n")
            f.write(f"Source: {chapter.source}\n\n")
            f.write(chapter.text[:2000])
            f.write("\n\n")
    return preview_path


def main() -> None:
    enable_high_dpi_awareness()
    root_class = TkinterDnD.Tk if TkinterDnD is not None else tk.Tk
    root = root_class()
    configure_tk_scaling(root)
    EpubTtsApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
