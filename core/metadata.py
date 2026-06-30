"""Read useful metadata from Fujifilm RAF / HDR RAF files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import struct


@dataclass
class ExposureFrame:
  index: int
  label: str
  shutter: str | None = None
  aperture: str | None = None
  iso: int | None = None
  ev_offset: str | None = None
  ev_stops: int | None = None


@dataclass
class RAFMetadata:
  filename: str
  file_size_mb: float
  make: str | None = None
  model: str | None = None
  lens: str | None = None
  timestamp: str | None = None
  picture_mode: str | None = None
  is_hdr: bool = False
  image_width: int | None = None
  image_height: int | None = None
  shutter: str | None = None
  aperture: str | None = None
  iso: int | None = None
  focal_length: str | None = None
  exposure_compensation: str | None = None
  hdr_bracket_stops: int | None = None
  hdr_frames: list[ExposureFrame] = field(default_factory=list)
  extra: dict[str, str] = field(default_factory=dict)

  def to_display_text(self) -> str:
    lines = [
      f"File: {self.filename}",
      f"Size: {self.file_size_mb:.1f} MB",
      "",
      "Camera",
      f"  Make: {self.make or '—'}",
      f"  Model: {self.model or '—'}",
      f"  Lens: {self.lens or '—'}",
      f"  Date/Time: {self.timestamp or '—'}",
      "",
      "Capture",
      f"  Picture mode: {self.picture_mode or '—'}",
      f"  HDR container: {'Yes' if self.is_hdr else 'No'}",
      f"  Resolution: {self._resolution()}",
      f"  Shutter: {self.shutter or '—'}",
      f"  Aperture: {self.aperture or '—'}",
      f"  ISO: {self.iso or '—'}",
      f"  Focal length: {self.focal_length or '—'}",
      f"  Exposure comp.: {self.exposure_compensation or '—'}",
    ]

    if self.hdr_frames:
      lines.extend(["", "HDR exposure steps"])
      for frame in self.hdr_frames:
        lines.append(f"  Frame {frame.index} ({frame.label})")
        if frame.ev_stops is not None:
          ev_text = f"+{frame.ev_stops}" if frame.ev_stops > 0 else str(frame.ev_stops)
          lines.append(f"    EV stops: {ev_text}")
        elif frame.ev_offset:
          lines.append(f"    EV offset: {frame.ev_offset}")
        if frame.shutter:
          lines.append(f"    Shutter: {frame.shutter}")
        if frame.aperture:
          lines.append(f"    Aperture: {frame.aperture}")
        if frame.iso is not None:
          lines.append(f"    ISO: {frame.iso}")

    if self.extra:
      lines.extend(["", "Additional tags"])
      for key, value in sorted(self.extra.items()):
        lines.append(f"  {key}: {value}")

    return "\n".join(lines)

  def _resolution(self) -> str:
    if self.image_width and self.image_height:
      return f"{self.image_width} x {self.image_height}"
    return "—"


class _TiffReader:
  def __init__(self, data: bytes, tiff_start: int, little_endian: bool):
    self.data = data
    self.tiff_start = tiff_start
    self.little_endian = little_endian
    self.endian = "<" if little_endian else ">"

  def u16(self, offset: int) -> int:
    return struct.unpack_from(f"{self.endian}H", self.data, offset)[0]

  def u32(self, offset: int) -> int:
    return struct.unpack_from(f"{self.endian}I", self.data, offset)[0]

  def i32(self, offset: int) -> int:
    return struct.unpack_from(f"{self.endian}i", self.data, offset)[0]

  def rational(self, offset: int) -> float:
    numerator = self.u32(offset)
    denominator = self.u32(offset + 4)
    if denominator == 0:
      return 0.0
    return numerator / denominator

  def ascii(self, offset: int, count: int) -> str:
    raw = self.data[offset : offset + max(count - 1, 0)]
    return raw.decode("ascii", errors="ignore").strip("\x00")

  def read_directory(self, dir_start: int) -> dict[int, object]:
    tags: dict[int, object] = {}
    if dir_start + 2 > len(self.data):
      return tags

    entries = self.u16(dir_start)
    for index in range(entries):
      entry_offset = dir_start + 2 + index * 12
      if entry_offset + 12 > len(self.data):
        break
      tag_id = self.u16(entry_offset)
      type_id = self.u16(entry_offset + 2)
      count = self.u32(entry_offset + 4)
      value_offset = self.u32(entry_offset + 8) + self.tiff_start
      inline_offset = entry_offset + 8

      if type_id == 2:
        if count <= 4:
          tags[tag_id] = self.ascii(inline_offset, count)
        else:
          tags[tag_id] = self.ascii(value_offset, count)
      elif type_id == 3:
        if count == 1:
          tags[tag_id] = self.u16(inline_offset)
        else:
          tags[tag_id] = [self.u16(value_offset + 2 * n) for n in range(count)]
      elif type_id == 4:
        if count == 1:
          tags[tag_id] = self.u32(inline_offset)
        else:
          tags[tag_id] = [self.u32(value_offset + 4 * n) for n in range(count)]
      elif type_id == 5 and count == 1:
        tags[tag_id] = self.rational(value_offset)
      elif type_id == 7:
        if tag_id == 0x927C:
          tags[tag_id] = self.u32(inline_offset)
        elif count <= 4:
          tags[tag_id] = self.data[inline_offset : inline_offset + count].hex()
        else:
          tags[tag_id] = self.data[value_offset : value_offset + count].hex()
      elif type_id == 9 and count == 1:
        tags[tag_id] = self.i32(inline_offset)
      elif type_id == 10 and count == 1:
        tags[tag_id] = self.i32(value_offset) / self.i32(value_offset + 4)
    return tags


PICTURE_MODES = {
  0: "Full Auto",
  6: "Program AE",
  48: "HDR",
  256: "Aperture-priority AE",
  512: "Shutter speed priority AE",
  768: "Manual",
}


def _format_shutter(seconds: float) -> str:
  if seconds <= 0:
    return "—"
  if seconds >= 1:
    return f"{seconds:.1f}s"
  return f"1/{round(1 / seconds)}s"


def _format_aperture(value: float) -> str:
  if value <= 0:
    return "—"
  return f"f/{value:.1f}"


def _format_rational_tag(value: object, suffix: str = "") -> str | None:
  if isinstance(value, float):
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}" if suffix else text
  return None


def read_raf_metadata(path: str | Path, data: bytes | None = None) -> RAFMetadata:
  path = Path(path)
  blob = data if data is not None else path.read_bytes()
  file_size_mb = len(blob) / (1024 * 1024)

  metadata = RAFMetadata(filename=path.name, file_size_mb=file_size_mb)
  if len(blob) < 120 or blob[0:4] != b"FUJI":
    metadata.extra["Error"] = "Not a Fujifilm RAF file"
    return metadata

  if len(blob) < 108:
    metadata.extra["Error"] = "RAF file is too small"
    return metadata

  jpg_offset = struct.unpack_from(">I", blob, 84)[0]
  if jpg_offset + 20 >= len(blob):
    metadata.extra["Error"] = "Invalid RAF JPEG/TIFF offsets"
    return metadata

  offset = jpg_offset + 2
  if offset + 12 >= len(blob):
    metadata.extra["Error"] = "Invalid TIFF header location"
    return metadata

  endian_mark = struct.unpack_from(">H", blob, offset + 10)[0]
  if endian_mark not in (0x4949, 0x4D4D):
    metadata.extra["Error"] = "Missing TIFF header"
    return metadata

  tiff_little_endian = endian_mark == 0x4949
  tiff_start = offset + 10
  reader = _TiffReader(blob, tiff_start, little_endian=tiff_little_endian)
  ifd0 = reader.read_directory(offset + 18)

  metadata.make = ifd0.get(0x010F)  # type: ignore[assignment]
  metadata.model = ifd0.get(0x0110)  # type: ignore[assignment]
  metadata.timestamp = ifd0.get(0x0132)  # type: ignore[assignment]

  exif_offset = ifd0.get(0x8769)
  exif: dict[int, object] = {}
  if isinstance(exif_offset, int):
    exif = reader.read_directory(tiff_start + exif_offset)
    metadata.shutter = _format_shutter(exif[0x829A]) if 0x829A in exif else None
    metadata.aperture = _format_aperture(exif[0x829D]) if 0x829D in exif else None
    metadata.iso = exif.get(0x8827)  # type: ignore[assignment]
    metadata.focal_length = _format_aperture(exif[0x920A]) if 0x920A in exif else None
    if 0x9204 in exif:
      metadata.exposure_compensation = _format_rational_tag(exif[0x9204], " EV")
    if 0x9003 in exif and not metadata.timestamp:
      metadata.timestamp = str(exif[0x9003])

  fuji_offset = ifd0.get(0x927C)
  if not isinstance(fuji_offset, int):
    fuji_offset = exif.get(0x927C)
  if isinstance(fuji_offset, int):
    fuji_dir_start = fuji_offset + offset + 22
    fuji = reader.read_directory(fuji_dir_start)
    metadata.image_width = fuji.get(0xA002)  # type: ignore[assignment]
    metadata.image_height = fuji.get(0xA003)  # type: ignore[assignment]
    if 0xA434 in fuji:
      metadata.lens = str(fuji[0xA434])

    picture_mode = fuji.get(0x1031)
    if isinstance(picture_mode, int):
      metadata.picture_mode = PICTURE_MODES.get(picture_mode, f"Mode {picture_mode}")
      metadata.is_hdr = picture_mode == 48

    metadata.hdr_frames = _parse_hdr_frames(fuji, metadata)
    if metadata.hdr_bracket_stops is None and metadata.hdr_frames:
      for frame in metadata.hdr_frames:
        if frame.ev_stops is not None and frame.ev_stops != 0:
          metadata.hdr_bracket_stops = abs(frame.ev_stops)
          break

  return metadata


def _parse_hdr_frames(fuji: dict[int, object], metadata: RAFMetadata) -> list[ExposureFrame]:
  labels = ["Base (0 EV)", "Underexposed", "Overexposed"]
  frames: list[ExposureFrame] = []

  stops_under = fuji.get(0x1151)
  stops_over = fuji.get(0x1152)
  if isinstance(stops_under, int) and stops_under > 0:
    metadata.hdr_bracket_stops = stops_under
  elif isinstance(stops_over, int) and stops_over > 0:
    metadata.hdr_bracket_stops = stops_over

  for index, label in enumerate(labels, start=1):
    frame = ExposureFrame(index=index, label=label)
    if index == 1:
      frame.ev_stops = 0
      frame.label = "Base (0 EV)"
    elif index == 2 and isinstance(stops_under, int) and stops_under > 0:
      frame.ev_stops = -stops_under
      frame.label = f"Under ({-stops_under} EV)"
    elif index == 3 and isinstance(stops_over, int) and stops_over > 0:
      frame.ev_stops = stops_over
      frame.label = f"Over (+{stops_over} EV)"

    tag_id = 0x114F + index
    raw = fuji.get(tag_id)
    if isinstance(raw, str) and len(raw) >= 16:
      frame.ev_offset = _decode_ev_offset(raw)
      if frame.ev_stops is None:
        parsed = _decode_ev_stops(raw)
        if parsed is not None:
          frame.ev_stops = parsed
      frame.shutter = _decode_shutter(raw)
      frame.aperture = _decode_aperture(raw)
      frame.iso = _decode_iso(raw)
    frames.append(frame)

  if all(frame.shutter is None for frame in frames) and metadata.shutter:
    frames[0].shutter = metadata.shutter
    frames[0].aperture = metadata.aperture
    frames[0].iso = metadata.iso

  return frames


def _decode_ev_stops(raw_hex: str) -> int | None:
  try:
    stops_under = int(raw_hex[6:8], 16)
    stops_over = int(raw_hex[8:10], 16)
    if stops_under == stops_over and stops_under > 0:
      if raw_hex.startswith("01"):
        return -stops_under
      if raw_hex.startswith("03"):
        return stops_over
  except ValueError:
    return None
  return None


def _decode_ev_offset(raw_hex: str) -> str | None:
  try:
    stops_under = int(raw_hex[6:8], 16)
    stops_over = int(raw_hex[8:10], 16)
    if stops_under == stops_over and stops_under > 0:
      if raw_hex.startswith("01"):
        return f"-{stops_under} EV"
      if raw_hex.startswith("03"):
        return f"+{stops_over} EV"
      return f"±{stops_under} EV bracket"
  except ValueError:
    return None
  return None


def _decode_shutter(raw_hex: str) -> str | None:
  try:
    value = int(raw_hex[10:18], 16)
    if value <= 0:
      return None
    seconds = value / 10_000_000
    return _format_shutter(seconds)
  except ValueError:
    return None


def _decode_aperture(raw_hex: str) -> str | None:
  try:
    value = int(raw_hex[18:26], 16)
    if value <= 0:
      return None
    return _format_aperture(value / 100)
  except ValueError:
    return None


def _decode_iso(raw_hex: str) -> int | None:
  try:
    value = int(raw_hex[26:34], 16)
    return value if value > 0 else None
  except ValueError:
    return None
