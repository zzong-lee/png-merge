"""PNG 파일을 카드로 정렬·회전한 뒤 PDF 또는 세로 PNG로 저장한다."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

APP_NAME = "PNG 병합"
FONT = "Malgun Gothic"

BG = "#eef1f4"
WHITE = "#ffffff"
TEXT = "#1c2430"
MUTED = "#667085"
LINE = "#e2e6ec"
ACCENT = "#1f6feb"
ACCENT_HOVER = "#1a62d0"
THUMB_BG = "#eef1f5"
SOFT = "#f3f4f6"
SOFT_HOVER = "#e5e7eb"
DANGER = "#b42318"

THUMB_W = 156
THUMB_H = 120
CARD_W = 196
GAP = 14
LARGE_PIXELS = 60_000_000
MAX_PIXELS = 150_000_000


@dataclass
class Page:
    path: str
    rotation: int = 0

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


def short_name(name: str, limit: int = 20) -> str:
    if len(name) <= limit:
        return name
    stem, ext = os.path.splitext(name)
    tail = ext if len(ext) <= 6 else ext[:6]
    head = limit - len(tail) - 1
    if head < 4:
        return name[: limit - 1] + "…"
    return stem[:head] + "…" + tail


def font(size: int, bold: bool = False) -> tuple:
    if bold:
        return (FONT, size, "bold")
    return (FONT, size)


def rotated_size(size: tuple[int, int], degrees: int) -> tuple[int, int]:
    width, height = size
    if degrees % 180 == 90:
        return height, width
    return width, height


def apply_rotation(image: Image.Image, degrees: int) -> Image.Image:
    turns = {
        90: Image.Transpose.ROTATE_270,
        180: Image.Transpose.ROTATE_180,
        270: Image.Transpose.ROTATE_90,
    }
    operation = turns.get(degrees % 360)
    if operation is None:
        return image
    return image.transpose(operation)


def to_rgb_white(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image.copy()
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, "white")
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def load_rgb(page: Page) -> Image.Image:
    with Image.open(page.path) as image:
        return to_rgb_white(apply_rotation(image, page.rotation))


def page_pixel_size(page: Page) -> tuple[int, int]:
    with Image.open(page.path) as image:
        return rotated_size(image.size, page.rotation)


def merged_png_size(pages: list[Page]) -> tuple[int, int]:
    width = 0
    height = 0
    for page in pages:
        page_width, page_height = page_pixel_size(page)
        width = max(width, page_width)
        height += page_height
    return width, height


def move_item(items: list, src: int, target: int) -> None:
    """src 항목을 빼서, 결과 리스트 기준 target 위치에 넣는다."""
    item = items.pop(src)
    items.insert(target, item)


def atomic_write(path: str, write) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    descriptor, temporary = tempfile.mkstemp(prefix="pngmerge-", suffix=".tmp", dir=directory)
    os.close(descriptor)
    try:
        write(temporary)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass


def save_pdf(pages: list[Page], path: str) -> None:
    if not pages:
        raise ValueError("저장할 이미지가 없습니다.")
    images = [load_rgb(page) for page in pages]
    try:
        def write(temporary: str) -> None:
            images[0].save(
                temporary,
                format="PDF",
                save_all=True,
                append_images=images[1:],
                resolution=96,
            )

        atomic_write(path, write)
    finally:
        for image in images:
            image.close()


def save_png(pages: list[Page], path: str) -> None:
    if not pages:
        raise ValueError("저장할 이미지가 없습니다.")
    width, height = merged_png_size(pages)
    canvas = Image.new("RGB", (width, height), "white")
    top = 0
    for page in pages:
        image = load_rgb(page)
        try:
            left = (width - image.width) // 2
            canvas.paste(image, (left, top))
            top += image.height
        finally:
            image.close()

    def write(temporary: str) -> None:
        canvas.save(temporary, format="PNG")

    try:
        atomic_write(path, write)
    finally:
        canvas.close()


def make_thumbnail(page: Page, master: tk.Misc) -> ImageTk.PhotoImage:
    with Image.open(page.path) as image:
        rgb = to_rgb_white(apply_rotation(image, page.rotation))
    rgb.thumbnail((THUMB_W, THUMB_H), Image.Resampling.LANCZOS)
    plate = Image.new("RGB", (THUMB_W, THUMB_H), THUMB_BG)
    plate.paste(rgb, ((THUMB_W - rgb.width) // 2, (THUMB_H - rgb.height) // 2))
    rgb.close()
    return ImageTk.PhotoImage(image=plate, master=master)


def place_center(window: tk.Toplevel, parent: tk.Misc) -> None:
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    if parent.winfo_viewable():
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
    else:
        x = max(0, (window.winfo_screenwidth() - width) // 2)
        y = max(0, (window.winfo_screenheight() - height) // 2)
    window.geometry(f"+{x}+{y}")


class FormatDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.result: str | None = None
        self.title("저장 형식")
        self.resizable(False, False)
        self.configure(bg=WHITE)
        self.transient(parent)

        tk.Label(
            self,
            text="어떤 형식으로 저장할까요?",
            bg=WHITE,
            fg=TEXT,
            font=font(12, True),
            anchor="w",
        ).pack(fill="x", padx=20, pady=(18, 10))

        self._option(
            "PDF",
            "이미지 한 장당 한 페이지로 저장합니다.",
            "pdf",
        )
        self._option(
            "PNG",
            "번호 순서대로 세로로 이어 붙인 이미지 한 장입니다.",
            "png",
        )

        cancel = tk.Button(
            self,
            text="취소",
            command=self._cancel,
            bg=SOFT,
            fg=TEXT,
            activebackground=SOFT_HOVER,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            font=font(9),
            cursor="hand2",
        )
        cancel.pack(pady=(8, 18))

        self.bind("<Escape>", lambda _event: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        place_center(self, parent)
        self.grab_set()
        self.wait_window()

    def _option(self, title: str, description: str, value: str) -> None:
        box = tk.Frame(
            self,
            bg=WHITE,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=LINE,
        )
        box.pack(fill="x", padx=20, pady=5)
        heading = tk.Label(box, text=title, bg=WHITE, fg=ACCENT, font=font(12, True), anchor="w")
        heading.pack(fill="x", padx=14, pady=(10, 0))
        detail = tk.Label(
            box,
            text=description,
            bg=WHITE,
            fg=MUTED,
            font=font(9),
            anchor="w",
            justify="left",
        )
        detail.pack(fill="x", padx=14, pady=(2, 12))

        def choose(_event=None, selected=value) -> None:
            self.result = selected
            self.destroy()

        def enter(_event=None) -> None:
            box.configure(highlightbackground=ACCENT, bg="#f5f9ff")
            heading.configure(bg="#f5f9ff")
            detail.configure(bg="#f5f9ff")

        def leave(_event=None) -> None:
            box.configure(highlightbackground=LINE, bg=WHITE)
            heading.configure(bg=WHITE)
            detail.configure(bg=WHITE)

        for widget in (box, heading, detail):
            widget.bind("<Button-1>", choose)
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


def action_button(parent: tk.Misc, text: str, command, role: str = "primary") -> tk.Button:
    styles = {
        "primary": (ACCENT, WHITE, ACCENT_HOVER, ACCENT),
        "ghost": (WHITE, TEXT, SOFT, LINE),
        "dark": ("#1c2430", WHITE, "#111827", "#1c2430"),
    }
    background, foreground, hover, border = styles[role]
    button = tk.Button(
        parent,
        text=text,
        command=command,
        bg=background,
        fg=foreground,
        activebackground=hover,
        activeforeground=foreground,
        disabledforeground="#9ca3af",
        relief="flat",
        bd=0,
        padx=14,
        pady=7,
        font=font(10, True),
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=border,
        highlightcolor=border,
    )
    button._palette = (background, foreground, hover, border)

    def on_enter(_event) -> None:
        if str(button.cget("state")) == "normal":
            button.configure(bg=hover)

    def on_leave(_event) -> None:
        if str(button.cget("state")) == "normal":
            button.configure(bg=background)

    button.bind("<Enter>", on_enter)
    button.bind("<Leave>", on_leave)
    return button


def set_button_enabled(button: tk.Button, enabled: bool) -> None:
    background, foreground, _hover, border = button._palette
    if enabled:
        button.configure(
            state="normal",
            bg=background,
            fg=foreground,
            highlightbackground=border,
        )
    else:
        button.configure(
            state="disabled",
            bg="#e5e7eb",
            fg="#9ca3af",
            highlightbackground="#e5e7eb",
        )


class Card(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        app: App,
        page: Page,
        index: int,
        thumb: ImageTk.PhotoImage | None,
    ) -> None:
        super().__init__(
            master,
            bg=WHITE,
            width=CARD_W,
            highlightthickness=2,
            highlightbackground=LINE,
            bd=0,
        )
        self.app = app
        self.index = index
        self.card_index = index

        top = tk.Frame(self, bg=WHITE)
        top.pack(fill="x", padx=10, pady=(8, 0))
        self.badge = tk.Label(
            top,
            text=str(index + 1),
            bg=ACCENT,
            fg=WHITE,
            font=font(8, True),
            padx=6,
            pady=1,
        )
        self.badge.pack(side="left")
        self.degree = tk.Label(top, text=self._degree_text(page.rotation), bg=WHITE, fg=ACCENT, font=font(9, True))
        self.degree.pack(side="right")

        self.plate = tk.Frame(self, width=THUMB_W, height=THUMB_H, bg=THUMB_BG)
        self.plate.pack(padx=10, pady=8)
        self.plate.pack_propagate(False)
        self.thumb_label = tk.Label(self.plate, bg=THUMB_BG, fg=MUTED, font=font(8))
        self.thumb_label.pack(expand=True)
        self.update_preview(thumb, page.rotation)

        self.name_label = tk.Label(
            self,
            text=short_name(page.name),
            bg=WHITE,
            fg=TEXT,
            font=font(9),
        )
        self.name_label.pack(padx=8)
        self.name_label.bind("<Enter>", lambda _event, path=page.path: app.set_status(path), add="+")
        self.name_label.bind("<Leave>", lambda _event: app.show_summary_if_idle(), add="+")

        self._tool_row(
            ("좌회전", self._rotate_left),
            ("우회전", self._rotate_right),
            top=8,
            bottom=0,
        )
        self._tool_row(
            ("앞으로", self._shift_back),
            ("뒤로", self._shift_forward),
            ("빼기", self._remove_self, DANGER),
            top=4,
            bottom=10,
        )
        self._bind_drag_tree(self)

    def _rotate_left(self) -> None:
        self.app.rotate(self.index, -90)

    def _rotate_right(self) -> None:
        self.app.rotate(self.index, 90)

    def _shift_back(self) -> None:
        self.app.shift(self.index, -1)

    def _shift_forward(self) -> None:
        self.app.shift(self.index, 1)

    def _remove_self(self) -> None:
        self.app.remove(self.index)

    def set_index(self, index: int) -> None:
        self.index = index
        self.badge.configure(text=str(index + 1))
        self._tag_index(self)

    def _tag_index(self, widget: tk.Misc) -> None:
        widget.card_index = self.index
        for child in widget.winfo_children():
            self._tag_index(child)

    def _tool_row(self, *specs, top: int = 4, bottom: int = 0) -> None:
        row = tk.Frame(self, bg=WHITE)
        row.pack(pady=(top, bottom))
        for spec in specs:
            text, command = spec[0], spec[1]
            color = spec[2] if len(spec) > 2 else TEXT
            button = tk.Button(
                row,
                text=text,
                command=command,
                bg=SOFT,
                fg=color,
                activebackground=SOFT_HOVER,
                activeforeground=color,
                relief="flat",
                bd=0,
                padx=6,
                pady=3,
                font=font(8),
                cursor="hand2",
                highlightthickness=0,
            )
            button.pack(side="left", padx=2)
            button.card_index = self.index

    def _degree_text(self, rotation: int) -> str:
        if rotation % 360 == 0:
            return ""
        return f"{rotation % 360}°"

    def update_preview(self, thumb: ImageTk.PhotoImage | None, rotation: int) -> None:
        self.degree.configure(text=self._degree_text(rotation))
        if thumb is None:
            self.thumb_label.configure(image="", text="미리보기 실패")
            self.thumb_label.image = None
            return
        self.thumb_label.configure(image=thumb, text="")
        self.thumb_label.image = thumb

    def set_role(self, role: str) -> None:
        colors = {"normal": LINE, "source": "#94a3b8", "target": ACCENT}
        self.configure(highlightbackground=colors.get(role, LINE))

    def _bind_drag_tree(self, widget: tk.Misc) -> None:
        if isinstance(widget, tk.Button):
            widget.card_index = self.index
            return
        widget.card_index = self.index
        widget.bind("<ButtonPress-1>", self._press, add="+")
        try:
            widget.configure(cursor="hand2")
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._bind_drag_tree(child)

    def _press(self, event) -> None:
        self.app.begin_drag(event, self.index)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.configure(bg=BG)
        self.minsize(760, 560)
        self.pages: list[Page] = []
        self.cards: list[Card] = []
        self.drag: dict | None = None
        self.busy = False
        self.open_dir = os.path.expanduser("~")
        self.save_dir: str | None = None
        self._canvas_width = -1
        self.card_width = CARD_W

        self._build()
        self._place_window()
        self.bind("<Control-o>", lambda _event: self.open_files())
        self.bind("<Control-O>", lambda _event: self.open_files())
        self.bind("<Control-s>", lambda _event: self.save())
        self.bind("<Control-S>", lambda _event: self.save())
        self.refresh()

    def _place_window(self) -> None:
        self.update_idletasks()
        width, height = 980, 700
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build(self) -> None:
        header = tk.Frame(self, bg=WHITE)
        header.pack(fill="x")
        titles = tk.Frame(header, bg=WHITE)
        titles.pack(side="left", padx=18, pady=14)
        tk.Label(titles, text=APP_NAME, bg=WHITE, fg=TEXT, font=font(16, True)).pack(anchor="w")
        tk.Label(
            titles,
            text="여러 PNG를 카드로 맞춘 뒤 하나로 저장합니다.",
            bg=WHITE,
            fg=MUTED,
            font=font(9),
        ).pack(anchor="w", pady=(2, 0))

        actions = tk.Frame(header, bg=WHITE)
        actions.pack(side="right", padx=18)
        self.open_button = action_button(actions, "열기", self.open_files, "primary")
        self.open_button.pack(side="left", padx=(0, 8))
        self.clear_button = action_button(actions, "모두 지우기", self.clear_all, "ghost")
        self.clear_button.pack(side="left", padx=(0, 8))
        self.save_button = action_button(actions, "저장", self.save, "dark")
        self.save_button.pack(side="left")

        tk.Frame(self, bg=LINE, height=1).pack(fill="x")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text="번호 순서대로 위에서 아래로 저장됩니다. 카드를 클릭한 채로 끌면 자리가 바뀝니다.",
            bg=BG,
            fg=MUTED,
            font=font(9),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(12, 8))

        list_row = tk.Frame(body, bg=BG)
        list_row.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.canvas = tk.Canvas(list_row, bg=BG, highlightthickness=0, bd=0, yscrollincrement=24)
        self.scroll = ttk.Scrollbar(list_row, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_wheel)

        footer = tk.Frame(self, bg=WHITE)
        footer.pack(fill="x")
        tk.Frame(footer, bg=LINE, height=1).pack(fill="x")
        self.status = tk.Label(footer, text="", bg=WHITE, fg=MUTED, font=font(9), anchor="w")
        self.status.pack(fill="x", padx=18, pady=8)

    def summary(self) -> str:
        count = len(self.pages)
        if count == 0:
            return "열기로 PNG를 선택하세요.  Ctrl+O"
        return f"{count}장  ·  번호 순서대로 위에서 아래로 저장됩니다.  카드를 클릭한 채로 끌어 순서를 바꾸세요."

    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def show_summary_if_idle(self) -> None:
        if self.drag and self.drag.get("active"):
            return
        self.set_status(self.summary())

    def _sync_buttons(self) -> None:
        has_pages = bool(self.pages) and not self.busy
        set_button_enabled(self.clear_button, has_pages)
        set_button_enabled(self.save_button, has_pages)
        set_button_enabled(self.open_button, not self.busy)

    def _on_canvas_configure(self, event) -> None:
        if event.width < 10 or event.width == self._canvas_width:
            return
        self._canvas_width = event.width
        self.relayout()

    def _on_wheel(self, event) -> str:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _bind_wheel(self, widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", self._on_wheel, add="+")
        for child in widget.winfo_children():
            self._bind_wheel(child)

    def _uniform_cards(self) -> None:
        if not self.cards:
            self.card_width = CARD_W
            return
        self.update_idletasks()
        width = max(CARD_W, max(card.winfo_reqwidth() for card in self.cards))
        height = max(card.winfo_reqheight() for card in self.cards)
        self.card_width = width
        for card in self.cards:
            card.configure(width=width, height=height)
            card.pack_propagate(False)

    def relayout(self) -> None:
        width = max(self.canvas.winfo_width(), 1)
        self.canvas.itemconfig(self.window_id, width=width)
        if self.cards:
            pitch = self.card_width + GAP
            columns = max(1, width // pitch)
            for index, card in enumerate(self.cards):
                card.grid(
                    row=index // columns,
                    column=index % columns,
                    padx=GAP // 2,
                    pady=GAP // 2,
                    sticky="n",
                )
        self.inner.update_idletasks()
        box = self.canvas.bbox("all")
        if box:
            self.canvas.configure(scrollregion=box)

    def refresh(self) -> None:
        try:
            scroll_y = self.canvas.yview()[0]
        except tk.TclError:
            scroll_y = 0.0
        for child in self.inner.winfo_children():
            child.destroy()
        self.cards = []
        if not self.pages:
            tk.Label(
                self.inner,
                text="아직 가져온 PNG가 없습니다.\n열기 버튼으로 파일을 선택하세요.",
                bg=BG,
                fg=MUTED,
                font=font(12),
                justify="center",
            ).grid(row=0, column=0, padx=24, pady=80)
        else:
            for index, page in enumerate(self.pages):
                try:
                    thumb = make_thumbnail(page, self)
                except Exception:
                    thumb = None
                self.cards.append(Card(self.inner, self, page, index, thumb))
        self._bind_wheel(self.inner)
        self._uniform_cards()
        self.relayout()
        self.canvas.yview_moveto(scroll_y)
        self._sync_buttons()
        self.set_status(self.summary())

    def open_files(self) -> None:
        if self.busy:
            return
        selected = filedialog.askopenfilenames(
            title="PNG 열기",
            initialdir=self.open_dir,
            filetypes=[("PNG 이미지", "*.png"), ("모든 파일", "*.*")],
        )
        if selected:
            self.add_files(list(selected))

    def add_files(self, paths: list[str]) -> None:
        added = 0
        failed: list[str] = []
        last_dir = None
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            for path in paths:
                name = os.path.basename(path)
                if os.path.splitext(path)[1].lower() != ".png":
                    failed.append(f"{name}  ·  PNG가 아닙니다")
                    continue
                try:
                    with Image.open(path) as image:
                        if image.size[0] < 1 or image.size[1] < 1:
                            raise ValueError("크기가 올바르지 않습니다.")
                except Exception as error:
                    failed.append(f"{name}  ·  {error}")
                    continue
                self.pages.append(Page(os.path.abspath(path)))
                last_dir = os.path.dirname(os.path.abspath(path))
                added += 1
        finally:
            self.configure(cursor="")
        if last_dir:
            self.open_dir = last_dir
        self.refresh()
        if failed and not added:
            messagebox.showerror("열기 실패", "\n".join(failed))
        elif failed:
            messagebox.showwarning("일부 파일을 열지 못했습니다", "\n".join(failed))
        if added:
            self.set_status(f"{added}장을 추가했습니다.  현재 {len(self.pages)}장")

    def clear_all(self) -> None:
        if not self.pages or self.busy:
            return
        agreed = messagebox.askyesno("모두 지우기", "목록을 비울까요?\n원본 파일은 삭제되지 않습니다.")
        if not agreed:
            return
        self.pages.clear()
        self.refresh()

    def rotate(self, index: int, delta: int) -> None:
        if self.busy or not 0 <= index < len(self.pages):
            return
        page = self.pages[index]
        previous = page.rotation
        page.rotation = (page.rotation + delta) % 360
        try:
            thumb = make_thumbnail(page, self)
        except Exception as error:
            page.rotation = previous
            messagebox.showerror("회전 실패", f"{page.name}\n{error}")
            return
        self.cards[index].update_preview(thumb, page.rotation)
        self.set_status(self.summary())

    def shift(self, index: int, delta: int) -> None:
        if self.busy:
            return
        target = index + delta
        if target < 0 or target >= len(self.pages):
            self.set_status("이 카드는 더 이동할 수 없습니다.")
            return
        move_item(self.pages, index, target)
        self.refresh()

    def remove(self, index: int) -> None:
        if self.busy or not 0 <= index < len(self.pages):
            return
        del self.pages[index]
        self.refresh()

    def begin_drag(self, event, index: int) -> None:
        if self.busy:
            return
        self.drag = {
            "index": index,
            "x": event.x_root,
            "y": event.y_root,
            "active": False,
            "target": None,
            "scrolled": 0.0,
        }
        self.bind_all("<B1-Motion>", self._drag_motion)
        self.bind_all("<ButtonRelease-1>", self._drag_release)

    def _drag_motion(self, event) -> None:
        info = self.drag
        if info is None:
            return
        started = False
        if not info["active"]:
            if abs(event.x_root - info["x"]) < 6 and abs(event.y_root - info["y"]) < 6:
                return
            info["active"] = True
            started = True
            self.configure(cursor="fleur")
        now = time.monotonic()
        if now - info["scrolled"] > 0.04:
            top = self.canvas.winfo_rooty()
            bottom = top + self.canvas.winfo_height()
            if event.y_root < top + 36:
                self.canvas.yview_scroll(-1, "units")
                info["scrolled"] = now
            elif event.y_root > bottom - 36:
                self.canvas.yview_scroll(1, "units")
                info["scrolled"] = now
        target = self.index_at(event.x_root, event.y_root)
        if target is not None and target != info["index"]:
            self._move_dragged_card(info["index"], target)
            info["index"] = target
            info["target"] = target
            self._paint_drag()
            self.set_status(f"{target + 1}번 위치로 옮겼습니다. 마우스를 놓으면 이 순서로 고정됩니다.")
        elif started:
            self._paint_drag()
            self.set_status("클릭한 채로 다른 카드 쪽으로 끌면 순서가 바뀝니다.")

    def _paint_drag(self) -> None:
        info = self.drag or {}
        for index, card in enumerate(self.cards):
            if index == info.get("index") and info.get("active"):
                card.set_role("source")
            elif index == info.get("target"):
                card.set_role("target")
            else:
                card.set_role("normal")

    def _move_dragged_card(self, src: int, target: int) -> None:
        move_item(self.pages, src, target)
        move_item(self.cards, src, target)
        for index, card in enumerate(self.cards):
            card.set_index(index)
        self.relayout()

    def _drag_release(self, _event) -> None:
        info = self.drag
        self.drag = None
        self.unbind_all("<B1-Motion>")
        self.unbind_all("<ButtonRelease-1>")
        self.configure(cursor="")
        for card in self.cards:
            card.set_role("normal")
        if info and info.get("active"):
            self.set_status(self.summary())

    def index_at(self, x: int, y: int) -> int | None:
        widget = self.winfo_containing(x, y)
        while widget is not None:
            index = getattr(widget, "card_index", None)
            if index is not None:
                return index
            widget = getattr(widget, "master", None)
        return None

    def save(self) -> None:
        if self.busy or not self.pages:
            if not self.pages:
                messagebox.showinfo(APP_NAME, "저장할 PNG가 없습니다.")
            return
        kind = FormatDialog(self).result
        if kind not in ("pdf", "png"):
            return
        extension = ".pdf" if kind == "pdf" else ".png"
        stem = os.path.splitext(os.path.basename(self.pages[0].path))[0]
        path = filedialog.asksaveasfilename(
            title="저장",
            defaultextension=extension,
            filetypes=[("PDF", "*.pdf")] if kind == "pdf" else [("PNG 이미지", "*.png")],
            initialdir=self.save_dir or self.open_dir,
            initialfile=f"{stem}_병합{extension}",
        )
        if not path:
            return
        if not path.lower().endswith(extension):
            path += extension
        if kind == "png":
            try:
                width, height = merged_png_size(self.pages)
            except Exception as error:
                messagebox.showerror("저장 실패", f"이미지 크기를 확인하지 못했습니다.\n{error}")
                return
            pixels = width * height
            if pixels > MAX_PIXELS or width > 30000 or height > 60000:
                messagebox.showerror(
                    "이미지가 너무 큽니다",
                    "이어 붙인 PNG가 너무 큽니다.\nPDF로 저장하면 페이지로 나뉘어 저장됩니다.\n"
                    f"예상 크기  {width} × {height}",
                )
                return
            if pixels > LARGE_PIXELS or width > 20000 or height > 30000:
                agreed = messagebox.askyesno(
                    "큰 이미지",
                    f"가로 {width} × 세로 {height} 입니다.\n메모리를 많이 사용합니다. 계속할까요?",
                    default=messagebox.NO,
                )
                if not agreed:
                    return
        self.busy = True
        self._sync_buttons()
        self.configure(cursor="watch")
        self.set_status("저장하는 중입니다.")
        self.update_idletasks()
        try:
            if kind == "pdf":
                save_pdf(self.pages, path)
            else:
                save_png(self.pages, path)
        except Image.DecompressionBombError:
            messagebox.showerror("저장 실패", "이미지가 너무 커서 열 수 없습니다. PDF로 다시 시도해 주세요.")
            self.set_status("저장하지 못했습니다.")
        except OSError as error:
            messagebox.showerror("저장 실패", f"파일을 저장하지 못했습니다.\n{error}")
            self.set_status("저장하지 못했습니다.")
        except Exception as error:
            messagebox.showerror("저장 실패", f"파일을 저장하지 못했습니다.\n{error}")
            self.set_status("저장하지 못했습니다.")
        else:
            self.save_dir = os.path.dirname(os.path.abspath(path))
            self.set_status(f"저장했습니다.  {path}")
            messagebox.showinfo("저장", f"저장했습니다.\n{path}")
        finally:
            self.busy = False
            self.configure(cursor="")
            self._sync_buttons()


def main() -> None:
    app = App()
    if len(sys.argv) > 1:
        paths = sys.argv[1:]
        app.after(50, lambda: app.add_files(paths))
    app.mainloop()


if __name__ == "__main__":
    main()
