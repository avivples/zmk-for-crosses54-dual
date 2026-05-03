from __future__ import annotations

import configparser
import binascii
import io
import os
import re
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DRAWER_CONFIG = ROOT / "keymap_drawer.config.yaml"
KEYMAP_YAML = ROOT / "keymap-drawer" / "crosses.yaml"
OUT_DIR = ROOT / "keyboard-companion"
ASSETS_DIR = OUT_DIR / "assets"
CONFIG_INI = OUT_DIR / "config.ini"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BLE_VENDOR_ID = "0xA241"
BLE_PRODUCT_ID = "0xC054"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def draw_layer_svg(layer_name: str, layer_data: list, layout: dict, svg_path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_yaml = Path(tmp) / f"{slugify(layer_name)}.yaml"
        tmp_yaml.write_text(
            yaml.safe_dump(
                {
                    "layout": layout,
                    "layers": {layer_name: layer_data},
                },
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "keymap_drawer",
                "-c",
                str(DRAWER_CONFIG),
                "draw",
                str(tmp_yaml),
                "-o",
                str(svg_path),
            ],
            check=True,
            cwd=ROOT,
        )
        svg_path.write_text(
            "\n".join(line.rstrip() for line in svg_path.read_text(encoding="utf-8").splitlines())
            + "\n",
            encoding="utf-8",
        )


def svg_size(svg_path: Path) -> tuple[int, int]:
    match = re.search(
        r'<svg[^>]*\swidth="([0-9.]+)"[^>]*\sheight="([0-9.]+)"',
        svg_path.read_text(encoding="utf-8", errors="ignore")[:512],
    )
    if match is None:
        return 1600, 1200

    width = int(float(match.group(1))) + 16
    height = int(float(match.group(2)) * 1.25) + 16
    return width, height


def svg_to_png(svg_path: Path, png_path: Path) -> None:
    try:
        import cairosvg
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_width=1600)
        return
    except (ImportError, OSError):
        pass

    browser_paths = [
        Path(os.environ.get("ProgramFiles", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    browser = next((path for path in browser_paths if path.exists()), None)
    if browser is None:
        raise SystemExit(
            "No SVG->PNG converter found. Install Cairo DLLs for cairosvg, or install Edge/Chrome."
        )

    width, height = svg_size(svg_path)
    with tempfile.TemporaryDirectory() as browser_profile:
        subprocess.run(
            [
                str(browser),
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                "--disable-crash-reporter",
                "--disable-features=Crashpad",
                "--force-device-scale-factor=1",
                f"--user-data-dir={browser_profile}",
                f"--window-size={width},{height}",
                f"--screenshot={png_path.resolve().as_posix()}",
                svg_path.resolve().as_uri(),
            ],
            check=True,
        )

    if not png_path.exists():
        raise SystemExit(f"Browser finished but did not write {png_path}")


def paeth(left: int, up: int, up_left: int) -> int:
    predictor = left + up - up_left
    left_dist = abs(predictor - left)
    up_dist = abs(predictor - up)
    up_left_dist = abs(predictor - up_left)
    if left_dist <= up_dist and left_dist <= up_left_dist:
        return left
    if up_dist <= up_left_dist:
        return up
    return up_left


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def read_png_rows(png_path: Path) -> tuple[int, int, int, list[bytes]]:
    data = png_path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise SystemExit(f"{png_path} is not a PNG")

    pos = len(PNG_SIGNATURE)
    width = height = color_type = None
    idat_chunks: list[bytes] = []
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if bit_depth != 8 or compression != 0 or filter_method != 0 or interlace != 0:
                raise SystemExit(f"Unsupported PNG format for cropping: {png_path}")
        elif kind == b"IDAT":
            idat_chunks.append(payload)
        elif kind == b"IEND":
            break

    if width is None or height is None or color_type is None:
        raise SystemExit(f"Missing PNG header in {png_path}")
    if color_type not in (2, 6):
        raise SystemExit(f"Unsupported PNG color type {color_type} in {png_path}")

    channels = 4 if color_type == 6 else 3
    stride = width * channels
    raw = zlib.decompress(b"".join(idat_chunks))
    rows: list[bytes] = []
    prev = bytearray(stride)
    raw_pos = 0
    for _ in range(height):
        filter_type = raw[raw_pos]
        raw_pos += 1
        row = bytearray(raw[raw_pos : raw_pos + stride])
        raw_pos += stride

        for index, value in enumerate(row):
            left = row[index - channels] if index >= channels else 0
            up = prev[index]
            up_left = prev[index - channels] if index >= channels else 0
            if filter_type == 1:
                row[index] = (value + left) & 0xFF
            elif filter_type == 2:
                row[index] = (value + up) & 0xFF
            elif filter_type == 3:
                row[index] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[index] = (value + paeth(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                raise SystemExit(f"Unsupported PNG filter {filter_type} in {png_path}")

        rows.append(bytes(row))
        prev = row

    return width, height, color_type, rows


def write_png_rows(png_path: Path, width: int, height: int, color_type: int, rows: list[bytes]) -> None:
    raw = b"".join(b"\x00" + row for row in rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    png_path.write_bytes(
        PNG_SIGNATURE
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + png_chunk(b"IEND", b"")
    )


def crop_png_whitespace(png_path: Path, padding: int = 8, threshold: int = 248) -> None:
    width, height, color_type, rows = read_png_rows(png_path)
    channels = 4 if color_type == 6 else 3
    min_x, min_y = width, height
    max_x = max_y = -1

    for y, row in enumerate(rows):
        for x in range(width):
            index = x * channels
            red, green, blue = row[index], row[index + 1], row[index + 2]
            alpha = row[index + 3] if channels == 4 else 255
            is_blank = alpha == 0 or (red >= threshold and green >= threshold and blue >= threshold)
            if not is_blank:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if max_x < 0:
        return

    min_x = max(min_x - padding, 0)
    min_y = max(min_y - padding, 0)
    max_x = min(max_x + padding, width - 1)
    max_y = min(max_y + padding, height - 1)
    cropped_width = max_x - min_x + 1
    cropped_height = max_y - min_y + 1
    cropped_rows = [
        row[min_x * channels : (max_x + 1) * channels] for row in rows[min_y : max_y + 1]
    ]
    write_png_rows(png_path, cropped_width, cropped_height, color_type, cropped_rows)


def write_companion_config(layer_pngs: list[str]) -> None:
    config = configparser.ConfigParser()
    config["KEYBOARD_USB_HID"] = {
        "usage_page": "0xFF60",
        "usage": "0x61",
    }
    config["KEYBOARD_BLE_HID"] = {
        "vendor_id": BLE_VENDOR_ID,
        "product_id": BLE_PRODUCT_ID,
    }
    config["LAYER_IMAGES"] = {
        f"layer_{index}": file_name for index, file_name in enumerate(layer_pngs)
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    handle = io.StringIO()
    config.write(handle)
    CONFIG_INI.write_text(handle.getvalue().rstrip() + "\n", encoding="utf-8")


def main() -> None:
    data = yaml.safe_load(KEYMAP_YAML.read_text(encoding="utf-8"))
    layout = {"ortho_layout": {"split": True, "rows": 4, "columns": 6, "thumbs": 3}}
    layers = data["layers"]

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    png_files: list[str] = []
    for layer_name, layer_data in layers.items():
        stem = slugify(layer_name)
        svg_path = ASSETS_DIR / f"{stem}.svg"
        png_path = ASSETS_DIR / f"{stem}.png"
        draw_layer_svg(layer_name, layer_data, layout, svg_path)
        svg_to_png(svg_path, png_path)
        crop_png_whitespace(png_path)
        png_files.append(png_path.name)
        print(f"wrote {png_path.relative_to(ROOT)}")

    write_companion_config(png_files)
    print(f"wrote {CONFIG_INI.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
