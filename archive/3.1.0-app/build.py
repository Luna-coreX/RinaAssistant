import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).parent

APP_NAME = "RinaAssistant"

PNG_ICON = PROJECT_ROOT / "assets" / "logo.png"
ICO_ICON = PROJECT_ROOT / "assets" / "icon.ico"


def png_to_ico():
    if ICO_ICON.exists():
        return

    print("Creating icon.ico...")

    img = Image.open(PNG_ICON)

    img.save(
        ICO_ICON,
        format="ICO",
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )


def remove_old():
    for folder in ["build", "dist"]:
        path = PROJECT_ROOT / folder
        if path.exists():
            shutil.rmtree(path)

    spec = PROJECT_ROOT / f"{APP_NAME}.spec"
    if spec.exists():
        spec.unlink()


def build():
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",
        "--name",
        APP_NAME,
        "--icon",
        str(ICO_ICON),

        "--add-data",
        f"assets;assets",

        "--add-data",
        f"plugins;plugins",

        "--add-data",
        f"animations;animations",

        "--add-data",
        f"components;components",

        "--add-data",
        f"dialogs;dialogs",

        "--add-data",
        f"pages;pages",



        "--add-data",
        f"voice;voice",
        "--version-file",
        "version_info.txt",

        "main.py",
    ]

    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    remove_old()
    png_to_ico()
    build()

    print()
    print("=" * 50)
    print("Build completed successfully!")
    print("Executable:")
    print(PROJECT_ROOT / "dist" / f"{APP_NAME}.exe")