"""Output filename helpers for extracted HDR RAF frames."""

from __future__ import annotations

from .metadata import ExposureFrame, RAFMetadata


def format_ev_stops(ev: int) -> str:
  """Format EV stops for filenames, e.g. -2, 0, +1."""
  if ev > 0:
    return f"+{ev}"
  return str(ev)


def build_raf_filenames(stem: str, ev_stops: list[int]) -> list[str]:
  return [f"{stem}_{format_ev_stops(ev)}.RAF" for ev in ev_stops]


def default_ev_stops(frame_count: int, bracket_stops: int = 1) -> list[int]:
  """Build a symmetric EV sequence when metadata does not provide per-frame values."""
  if frame_count <= 0:
    return []

  if frame_count == 1:
    return [0]

  if frame_count == 3:
    stops = max(bracket_stops, 1)
    return [-stops, 0, stops]

  if frame_count % 2 == 1:
    half = frame_count // 2
    return list(range(-half, half + 1))

  # Even frame counts: -N..-1, +1..+N (no exact 0 frame)
  half = frame_count // 2
  return list(range(-half, 0)) + list(range(1, half + 1))


def ev_stops_from_metadata(metadata: RAFMetadata, frame_count: int) -> list[int]:
  """Derive EV stop labels for extracted frames."""
  if metadata.hdr_frames and len(metadata.hdr_frames) == frame_count:
    explicit = [frame.ev_stops for frame in metadata.hdr_frames]
    if all(isinstance(ev, int) for ev in explicit):
      return explicit  # type: ignore[return-value]

  bracket = metadata.hdr_bracket_stops
  if bracket is None and metadata.hdr_frames:
    for frame in metadata.hdr_frames:
      if frame.ev_stops is not None and frame.ev_stops < 0:
        bracket = abs(frame.ev_stops)
        break
      if frame.ev_stops is not None and frame.ev_stops > 0:
        bracket = frame.ev_stops
        break

  return default_ev_stops(frame_count, bracket_stops=bracket or 1)
