"""Fujifilm HDR RAF Extractor - desktop application."""

from __future__ import annotations

import io
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

from core.metadata import read_raf_metadata
from core.raf_hdr import RAFHDR


APP_NAME = "Fuji HDR Extractor"
APP_VERSION = "1.0.0"


class FujiHDRExtractorApp(ctk.CTk):
  def __init__(self) -> None:
    super().__init__()
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    self.title(f"{APP_NAME} v{APP_VERSION}")
    self.geometry("980x720")
    self.minsize(860, 640)

    self.current_path: Path | None = None
    self.current_data: bytes | None = None
    self.preview_image: ImageTk.PhotoImage | None = None

    self._build_layout()
    self._set_idle_state()

  def _build_layout(self) -> None:
    self.grid_columnconfigure(0, weight=1)
    self.grid_rowconfigure(1, weight=1)

    header = ctk.CTkFrame(self)
    header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
    header.grid_columnconfigure(0, weight=1)

    title_font = ctk.CTkFont(size=22, weight="bold")
    subtitle_font = ctk.CTkFont(size=13)

    ctk.CTkLabel(header, text=APP_NAME, font=title_font).grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(
      header,
      text="Unpack Fujifilm HDR RAF files into separate exposure steps",
      font=subtitle_font,
      text_color=("gray40", "gray70"),
    ).grid(row=1, column=0, sticky="w", pady=(2, 0))

    body = ctk.CTkFrame(self)
    body.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)
    body.grid_columnconfigure(1, weight=1)
    body.grid_rowconfigure(2, weight=1)

    controls = ctk.CTkFrame(body)
    controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
    controls.grid_columnconfigure(1, weight=1)

    self.open_button = ctk.CTkButton(controls, text="Open HDR RAF…", command=self.open_file, width=140)
    self.open_button.grid(row=0, column=0, padx=(12, 8), pady=12)

    self.file_label = ctk.CTkLabel(controls, text="No file selected", anchor="w")
    self.file_label.grid(row=0, column=1, sticky="ew", padx=8, pady=12)

    self.status_label = ctk.CTkLabel(
      body,
      text="Select a Fujifilm HDR RAF file to inspect metadata and extract exposures.",
      anchor="w",
      wraplength=900,
      justify="left",
    )
    self.status_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))

    preview_card = ctk.CTkFrame(body)
    preview_card.grid(row=2, column=0, sticky="nsw", padx=(0, 12))
    ctk.CTkLabel(preview_card, text="Embedded preview", font=ctk.CTkFont(weight="bold")).pack(
      anchor="w", padx=12, pady=(12, 8)
    )
    self.preview_label = ctk.CTkLabel(preview_card, text="No preview", width=280, height=210)
    self.preview_label.pack(padx=12, pady=(0, 12))

    meta_card = ctk.CTkFrame(body)
    meta_card.grid(row=2, column=1, sticky="nsew")
    meta_card.grid_rowconfigure(1, weight=1)
    meta_card.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(meta_card, text="Metadata", font=ctk.CTkFont(weight="bold")).grid(
      row=0, column=0, sticky="w", padx=12, pady=(12, 8)
    )

    mono = ctk.CTkFont(family="Consolas", size=11)
    self.metadata_box = ctk.CTkTextbox(meta_card, font=mono, wrap="none")
    self.metadata_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
    self.metadata_box.insert("1.0", "Metadata will appear here after you open a RAF file.")
    self.metadata_box.configure(state="disabled")

    footer = ctk.CTkFrame(self)
    footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 16))
    footer.grid_columnconfigure(1, weight=1)

    self.output_button = ctk.CTkButton(
      footer,
      text="Choose output folder…",
      command=self.choose_output_folder,
      width=170,
    )
    self.output_button.grid(row=0, column=0, padx=(12, 8), pady=12)

    self.output_label = ctk.CTkLabel(footer, text="Output: same folder as source file", anchor="w")
    self.output_label.grid(row=0, column=1, sticky="ew", padx=8, pady=12)

    self.extract_button = ctk.CTkButton(
      footer,
      text="Extract HDR steps",
      command=self.extract_frames,
      width=170,
      height=40,
      font=ctk.CTkFont(size=14, weight="bold"),
    )
    self.extract_button.grid(row=0, column=2, padx=(8, 12), pady=12)

    self.output_dir: Path | None = None

  def _set_idle_state(self) -> None:
    self.extract_button.configure(state="disabled")
    self.output_button.configure(state="disabled")

  def _set_loaded_state(self, can_extract: bool) -> None:
    self.output_button.configure(state="normal")
    self.extract_button.configure(state="normal" if can_extract else "disabled")

  def open_file(self) -> None:
    selected = filedialog.askopenfilename(
      title="Select Fujifilm HDR RAF file",
      filetypes=[("Fujifilm RAW", "*.raf *.RAF"), ("All files", "*.*")],
    )
    if not selected:
      return
    self.load_file(Path(selected))

  def load_file(self, path: Path) -> None:
    try:
      data = path.read_bytes()
    except OSError as exc:
      messagebox.showerror(APP_NAME, f"Could not read file:\n{exc}")
      return

    try:
      self.current_path = path
      self.current_data = data
      self.output_dir = None
      self.output_label.configure(text=f"Output: {path.parent}")

      self.file_label.configure(text=str(path))
      self._render_metadata(path, data)
      self._render_preview(data)

      info = RAFHDR(data).analyze(path)
      self.status_label.configure(text=info.message)
      self._set_loaded_state(can_extract=info.frame_count == 3)
    except Exception as exc:
      messagebox.showerror(APP_NAME, f"Could not read RAF metadata:\n{exc}")
      self.status_label.configure(text="Failed to read the selected RAF file.")
      self._set_idle_state()

  def _render_metadata(self, path: Path, data: bytes) -> None:
    metadata = read_raf_metadata(path, data)
    info = RAFHDR(data).analyze(path)

    text_lines = [metadata.to_display_text(), "", "Container analysis", f"  {info.message}"]
    if info.cfa_tags:
      text_lines.append("")
      text_lines.append("Raw segments")
      for index, cfa in enumerate(info.cfa_tags, start=1):
        segment_mb = cfa.segment_size / (1024 * 1024)
        text_lines.append(
          f"  Segment {index}: {cfa.cfa_raw_width}x{cfa.cfa_raw_height} "
          f"({segment_mb:.1f} MB raw data)"
        )

    self.metadata_box.configure(state="normal")
    self.metadata_box.delete("1.0", "end")
    self.metadata_box.insert("1.0", "\n".join(text_lines))
    self.metadata_box.configure(state="disabled")

  def _render_preview(self, data: bytes) -> None:
    preview_bytes = RAFHDR(data).get_preview_jpeg()
    if not preview_bytes:
      self.preview_label.configure(image=None, text="No embedded preview")
      self.preview_image = None
      return

    image = Image.open(io.BytesIO(preview_bytes))
    image.thumbnail((280, 210), Image.Resampling.LANCZOS)
    self.preview_image = ImageTk.PhotoImage(image)
    self.preview_label.configure(image=self.preview_image, text="")

  def choose_output_folder(self) -> None:
    if not self.current_path:
      return
    selected = filedialog.askdirectory(
      title="Choose output folder",
      initialdir=str(self.current_path.parent),
    )
    if not selected:
      return
    self.output_dir = Path(selected)
    self.output_label.configure(text=f"Output: {self.output_dir}")

  def extract_frames(self) -> None:
    if not self.current_path or not self.current_data:
      return

    output_dir = self.output_dir or self.current_path.parent
    metadata = read_raf_metadata(self.current_path, self.current_data)

    try:
      result = RAFHDR(self.current_data).extract_to_directory(
        output_dir=output_dir,
        source_path=self.current_path,
        metadata=metadata,
      )
    except ValueError as exc:
      messagebox.showerror(APP_NAME, str(exc))
      return
    except OSError as exc:
      messagebox.showerror(APP_NAME, f"Could not write output files:\n{exc}")
      return

    files_text = "\n".join(f"• {path.name}" for path in result.files)
    messagebox.showinfo(
      APP_NAME,
      f"Extracted {len(result.files)} RAF files to:\n{output_dir}\n\n{files_text}",
    )
    self.status_label.configure(text=f"Extracted {len(result.files)} files to {output_dir}")


def main() -> None:
  try:
    app = FujiHDRExtractorApp()
    app.mainloop()
  except Exception:
    import traceback

    traceback.print_exc()
    from tkinter import messagebox

    messagebox.showerror(APP_NAME, traceback.format_exc())


if __name__ == "__main__":
  main()
