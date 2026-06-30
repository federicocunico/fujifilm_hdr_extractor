# Fuji HDR Extractor

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Release](https://github.com/federicocunico/fujifilm_hdr_extractor/actions/workflows/release.yml/badge.svg)](https://github.com/federicocunico/fujifilm_hdr_extractor/actions/workflows/release.yml)

Open-source desktop app for Windows that unpacks **Fujifilm HDR RAF** files into separate exposure steps.

Fujifilm HDR mode stores three raw exposures inside one `.RAF` container. Most editors only read the first exposure. This tool splits the file back into individual RAFs you can merge in HDR software of your choice.

**Repository:** [github.com/federicocunico/fujifilm_hdr_extractor](https://github.com/federicocunico/fujifilm_hdr_extractor)

## Download

Pre-built Windows builds are published on [GitHub Releases](https://github.com/federicocunico/fujifilm_hdr_extractor/releases).

Download the latest:

`Fuji-HDR-Extractor-vX.Y.Z-Windows-x64.zip`

Unzip anywhere and run `Fuji HDR Extractor.exe`. No installer required.

## Output naming

Extracted files keep the original base name and add the exposure step:

| Frame | Example |
|-------|---------|
| Underexposed (−3 EV) | `DSCF5422_-3.RAF` |
| Base (0 EV) | `DSCF5422_0.RAF` |
| Overexposed (+3 EV) | `DSCF5422_+3.RAF` |

For wider brackets the suffixes scale automatically (`-2`, `-1`, `0`, `+1`, `+2`, etc.).

## Use

1. **Open HDR RAF…** — select your Fujifilm HDR `.RAF` file
2. Review metadata and preview
3. Optionally choose an output folder (defaults to the source folder)
4. Click **Extract HDR steps**

## Build from source

Requires [uv](https://docs.astral.sh/uv/).

```powershell
git clone https://github.com/federicocunico/fujifilm_hdr_extractor.git
cd fujifilm_hdr_extractor
uv sync --group dev
uv run python app.py
```

Build the portable Windows app:

```powershell
.\build.bat
```

Output: `dist\Fuji HDR Extractor\Fuji HDR Extractor.exe`

## Publish a release

Maintainers can cut a release by pushing a version tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions builds the Windows zip and attaches it to the release automatically.

## Contributing

Contributions are welcome. This project is fully open source — feel free to open issues, suggest improvements, or submit pull requests.

## License

This project is licensed under the [MIT License](LICENSE). You are free to use, modify, and distribute it, including for commercial purposes, as long as the license notice is preserved.

## Credits

Extraction logic is based on the approach used by Greybeard's [FUJIFILM HDR Extract](https://www.solentsystems.com/hdrextract/) tool.
