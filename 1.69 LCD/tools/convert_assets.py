"""Helpers to prepare images and fonts for MicroPython LCD demos.

These scripts run on a desktop Python environment (CPython + Pillow).
"""

from __future__ import annotations

import argparse
import pathlib
from typing import Tuple

from PIL import Image

LCD_WIDTH = 240
LCD_HEIGHT = 280


def image_to_rgb565(source: pathlib.Path, dest: pathlib.Path) -> None:
    """Convert an image file to raw RGB565 data sized for the 1.69" LCD."""
    image = Image.open(source).convert("RGB").resize((LCD_WIDTH, LCD_HEIGHT))
    pixels = bytearray()
    for r, g, b in image.getdata():
        value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        pixels.append((value >> 8) & 0xFF)
        pixels.append(value & 0xFF)
    dest.write_bytes(pixels)
    print(f"[ok] saved rgb565: {dest}")


def parse_size(text: str) -> Tuple[int, int]:
    parts = text.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("size must look like WIDTHxHEIGHT")
    return int(parts[0]), int(parts[1])


def image_to_py(source: pathlib.Path, dest: pathlib.Path, size: Tuple[int, int]) -> None:
    """Convert an image into a Python module with a bytes literal."""
    width, height = size
    image = Image.open(source).convert("RGB").resize((width, height))
    rgb = bytearray()
    for r, g, b in image.getdata():
        value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        rgb.append((value >> 8) & 0xFF)
        rgb.append(value & 0xFF)
    module = [
        "# Auto-generated RGB565 sprite",
        f"WIDTH = {width}",
        f"HEIGHT = {height}",
        "DATA = bytes.fromhex(\"" + rgb.hex() + "\")",
    ]
    dest.write_text("\n".join(module))
    print(f"[ok] saved python sprite: {dest}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    to_bin = sub.add_parser("image", help="convert image to raw .bin")
    to_bin.add_argument("source", type=pathlib.Path)
    to_bin.add_argument("dest", type=pathlib.Path)

    to_py = sub.add_parser("sprite", help="convert image to python module")
    to_py.add_argument("source", type=pathlib.Path)
    to_py.add_argument("dest", type=pathlib.Path)
    to_py.add_argument(
        "--size",
        type=parse_size,
        default=parse_size("64x64"),
        help="output size WIDTHxHEIGHT",
    )

    args = parser.parse_args(argv)

    if args.command == "image":
        image_to_rgb565(args.source, args.dest)
    elif args.command == "sprite":
        image_to_py(args.source, args.dest, args.size)
    else:
        parser.error("unknown command")


if __name__ == "__main__":
    main()
