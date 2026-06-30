"""Fujifilm HDR RAF parsing and frame extraction.

Based on the public-domain approach used by Greybeard's HDR Extract tool
(https://www.solentsystems.com/hdrextract/). HDR RAF files store three full
raw exposures concatenated in one container file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

from .metadata import RAFMetadata
from .naming import build_raf_filenames, default_ev_stops, ev_stops_from_metadata, format_ev_stops


@dataclass
class CFATags:
    jpg_offset: int
    jpg_length: int
    cfa_header_offset: int
    cfa_header_size: int
    cfa_offset: int
    cfa_size: int
    cfa_raw_height: int
    cfa_raw_width: int

    @property
    def segment_size(self) -> int:
        return self.cfa_offset + self.cfa_size


@dataclass
class RAFHDRInfo:
    path: Path
    file_size: int
    is_fuji_raf: bool
    is_hdr: bool
    frame_count: int
    preview_jpeg: bytes | None
    cfa_tags: list[CFATags]
    message: str


@dataclass
class ExtractionResult:
    source: Path
    output_dir: Path
    files: list[Path]
    labels: list[str]
    ev_stops: list[int]


class RAFHDR:
  PICTURE_MODE_HDR = 48

  def __init__(self, data: bytes):
    self.data = data

  @classmethod
  def from_path(cls, path: str | Path) -> "RAFHDR":
    path = Path(path)
    return cls(path.read_bytes())

  def _u8(self, offset: int) -> int:
    return self.data[offset]

  def _u16(self, offset: int, little_endian: bool = True) -> int:
    endian = "<" if little_endian else ">"
    return struct.unpack_from(f"{endian}H", self.data, offset)[0]

  def _u32(self, offset: int, little_endian: bool = True) -> int:
    endian = "<" if little_endian else ">"
    return struct.unpack_from(f"{endian}I", self.data, offset)[0]

  def _raf_u32(self, offset: int) -> int:
    """RAF container header integers are big-endian (JavaScript DataView default)."""
    return struct.unpack_from(">I", self.data, offset)[0]

  def is_fuji_raf(self) -> bool:
    return len(self.data) >= 4 and self.data[0:4] == b"FUJI"

  def read_cfa_tags(self, base_offset: int = 0) -> CFATags:
    cfa_header_offset = self._raf_u32(base_offset + 92)
    cfa_header_abs = base_offset + cfa_header_offset
    return CFATags(
      jpg_offset=self._raf_u32(base_offset + 84),
      jpg_length=self._raf_u32(base_offset + 88),
      cfa_header_offset=cfa_header_offset,
      cfa_header_size=self._raf_u32(base_offset + 96),
      cfa_offset=self._raf_u32(base_offset + 100),
      cfa_size=self._raf_u32(base_offset + 104),
      cfa_raw_height=self._u16(cfa_header_abs + 8, little_endian=False),
      cfa_raw_width=self._u16(cfa_header_abs + 10, little_endian=False),
    )

  def get_preview_jpeg(self) -> bytes | None:
    if not self.is_fuji_raf() or len(self.data) < 92:
      return None
    offset = self._raf_u32(84)
    length = self._raf_u32(88)
    if offset <= 0 or length <= 0 or offset + length > len(self.data):
      return None
    return bytes(self.data[offset : offset + length])

  def is_hdr_mode(self) -> bool:
    """Detect Fujifilm HDR picture mode (tag 0x1031 == 48)."""
    if not self.is_fuji_raf():
      return False

    try:
      jpg_offset = self._raf_u32(84)
      offset = jpg_offset + 2
      if offset + 14 >= len(self.data):
        return False

      endian_mark = self._u16(offset + 10, little_endian=False)
      if endian_mark not in (0x4949, 0x4D4D):
        return False

      tiff_le = endian_mark == 0x4949
      if self._u16(offset + 12, little_endian=tiff_le) != 0x002A:
        return False

      tiff_start = offset + 10
      dir_start = offset + 18
      entries = self._u16(dir_start, little_endian=tiff_le)
      fuji_ifd_offset = None

      for index in range(entries):
        entry_offset = dir_start + 2 + index * 12
        tag_id = self._u16(entry_offset, little_endian=tiff_le)
        if tag_id == 0x927C:
          fuji_ifd_offset = self._u32(entry_offset + 8, little_endian=tiff_le)
        if tag_id == 0x8769 and fuji_ifd_offset is None:
          exif_offset = self._u32(entry_offset + 8, little_endian=tiff_le)
          exif_dir = tiff_start + exif_offset
          exif_entries = self._u16(exif_dir, little_endian=tiff_le)
          for exif_index in range(exif_entries):
            exif_entry = exif_dir + 2 + exif_index * 12
            if self._u16(exif_entry, little_endian=tiff_le) == 0x927C:
              fuji_ifd_offset = self._u32(exif_entry + 8, little_endian=tiff_le)
              break

      if fuji_ifd_offset is None:
        return False

      fuji_dir_start = fuji_ifd_offset + offset + 22
      picture_mode = self._read_tag_u16(tiff_start, fuji_dir_start, 0x1031, tiff_le)
      return picture_mode == self.PICTURE_MODE_HDR
    except (IndexError, struct.error):
      return False

  def _read_tag_u16(
    self,
    tiff_start: int,
    dir_start: int,
    tag_id: int,
    little_endian: bool,
  ) -> int | None:
    entries = self._u16(dir_start, little_endian=little_endian)
    for index in range(entries):
      entry_offset = dir_start + 2 + index * 12
      current_tag = self._u16(entry_offset, little_endian=little_endian)
      if current_tag != tag_id:
        continue
      return self._u16(entry_offset + 8, little_endian=little_endian)
    return None

  def _read_ascii(self, entry_offset: int, inline_count: int, little_endian: bool) -> str:
    type_id = self._u16(entry_offset + 2, little_endian=little_endian)
    count = self._u32(entry_offset + 4, little_endian=little_endian)
    if type_id != 2:
      return ""
    if count <= inline_count:
      raw = self.data[entry_offset + 8 : entry_offset + 8 + count - 1]
    else:
      value_offset = self._u32(entry_offset + 8, little_endian=little_endian)
      raw = self.data[value_offset : value_offset + count - 1]
    return raw.decode("ascii", errors="ignore")

  def analyze(self, path: Path | None = None) -> RAFHDRInfo:
    path = path or Path("unknown.raf")
    file_size = len(self.data)
    is_fuji = self.is_fuji_raf()
    preview = self.get_preview_jpeg() if is_fuji else None

    if not is_fuji:
      return RAFHDRInfo(
        path=path,
        file_size=file_size,
        is_fuji_raf=False,
        is_hdr=False,
        frame_count=0,
        preview_jpeg=None,
        cfa_tags=[],
        message="This file is not a Fujifilm RAF file.",
      )

    cfa1 = self.read_cfa_tags(0)
    if cfa1.segment_size >= file_size:
      return RAFHDRInfo(
        path=path,
        file_size=file_size,
        is_fuji_raf=True,
        is_hdr=False,
        frame_count=0,
        preview_jpeg=preview,
        cfa_tags=[cfa1],
        message="This RAF file does not appear to contain multiple HDR exposures.",
      )

    cfa2 = self.read_cfa_tags(cfa1.segment_size)
    size2 = cfa2.segment_size
    cfa3 = self.read_cfa_tags(cfa1.segment_size + size2)
    cfa_tags = [cfa1, cfa2, cfa3]
    is_hdr = self.is_hdr_mode() or file_size > cfa1.segment_size * 2

    if cfa3.segment_size + cfa1.segment_size + size2 > file_size:
      return RAFHDRInfo(
        path=path,
        file_size=file_size,
        is_fuji_raf=True,
        is_hdr=is_hdr,
        frame_count=0,
        preview_jpeg=preview,
        cfa_tags=cfa_tags,
        message="HDR segments were found but the file appears truncated or corrupt.",
      )

    message = (
      "Valid Fujifilm HDR RAF with 3 embedded exposures."
      if is_hdr
      else "This RAF contains 3 raw segments but picture mode is not HDR."
    )
    return RAFHDRInfo(
      path=path,
      file_size=file_size,
      is_fuji_raf=True,
      is_hdr=is_hdr,
      frame_count=3,
      preview_jpeg=preview,
      cfa_tags=cfa_tags,
      message=message,
    )

  def extract_frames(self) -> list[bytes]:
    info = self.analyze()
    if info.frame_count != 3:
      raise ValueError(info.message)

    cfa1, cfa2, cfa3 = info.cfa_tags
    raf_size1 = cfa1.segment_size
    cfa_header_offset = cfa1.cfa_header_offset

    frame1 = bytes(self.data[0:raf_size1])

    raf_part_os2 = raf_size1 + cfa2.cfa_header_offset
    raf_part_sz2 = cfa2.cfa_header_size + cfa2.cfa_size
    frame2 = (
      bytes(self.data[0:104])
      + bytes(self.data[raf_size1 + 104 : raf_size1 + 108])
      + bytes(self.data[108:cfa_header_offset])
      + bytes(self.data[raf_part_os2 : raf_part_os2 + raf_part_sz2])
    )

    raf_size2 = cfa2.segment_size
    raf_part_os3 = raf_size1 + raf_size2 + cfa3.cfa_header_offset
    raf_part_sz3 = cfa3.cfa_header_size + cfa3.cfa_size
    frame3 = (
      bytes(self.data[0:104])
      + bytes(self.data[raf_size1 + raf_size2 + 104 : raf_size1 + raf_size2 + 108])
      + bytes(self.data[108:cfa_header_offset])
      + bytes(self.data[raf_part_os3 : raf_part_os3 + raf_part_sz3])
    )

    return [frame1, frame2, frame3]

  def extract_to_directory(
    self,
    output_dir: str | Path,
    source_path: str | Path,
    ev_stops: list[int] | None = None,
    metadata: RAFMetadata | None = None,
  ) -> ExtractionResult:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = Path(source_path)
    stem = source_path.stem

    frames = self.extract_frames()
    if ev_stops is None:
      if metadata is not None:
        ev_stops = ev_stops_from_metadata(metadata, len(frames))
      else:
        ev_stops = default_ev_stops(len(frames))

    if len(ev_stops) != len(frames):
      raise ValueError(
        f"Expected {len(frames)} EV labels, got {len(ev_stops)}: {ev_stops}"
      )

    output_names = build_raf_filenames(stem, ev_stops)

    written: list[Path] = []
    for frame, out_name in zip(frames, output_names):
      out_path = output_dir / out_name
      out_path.write_bytes(frame)
      written.append(out_path)

    return ExtractionResult(
      source=source_path,
      output_dir=output_dir,
      files=written,
      labels=[format_ev_stops(ev) for ev in ev_stops],
      ev_stops=ev_stops,
    )
