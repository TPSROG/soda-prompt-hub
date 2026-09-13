"""Convert approved artwork to desktop icon containers without changing its design."""

from pathlib import Path

from PIL import Image


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "deploy" / "desktop-ui"
    with Image.open(root / "app-icon-source.png") as source:
        icon = source.convert("RGBA").resize((1024, 1024), Image.Resampling.LANCZOS)
        icon.save(root / "app-icon.png")
        icon.save(root / "app-icon.icns", format="ICNS")
        icon.save(
            root / "app-icon.ico",
            format="ICO",
            sizes=[(s, s) for s in (16, 20, 24, 32, 48, 64, 128, 256)],
        )


if __name__ == "__main__":
    main()
