"""Validate tags, assemble portable assets and write release checksums."""

import argparse
import hashlib
from pathlib import Path
import tomllib
from zipfile import ZipFile, ZIP_DEFLATED


ROOT = Path(__file__).resolve().parents[1]


def version():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "portable", "checksums"))
    parser.add_argument("--tag")
    args = parser.parse_args()
    current = version()
    dist = ROOT / "dist"
    if args.action == "check":
        if args.tag != f"v{current}":
            parser.error(f"tag must match pyproject.toml version: v{current}")
        print(current)
    elif args.action == "portable":
        target = dist / f"PixelToolkit-{current}-windows-x64.zip"
        with ZipFile(target, "w", ZIP_DEFLATED) as archive:
            for path in (dist / "PixelToolkit.exe", ROOT / "README.md", ROOT / "LICENSE", ROOT / "算法说明.md"):
                archive.write(path, path.name)
            for path in sorted((ROOT / "presets").glob("*.json")):
                archive.write(path, "presets/" + path.name)
            archive.writestr("使用说明.txt",
                            "双击 PixelToolkit.exe 打开本地工作台。\n"
                            "在命令行运行 PixelToolkit.exe --help 查看工具组命令。\n"
                            "无需另装 Python 或 uv。关闭控制台窗口即可停止工作台。\n".encode("utf-8"))
        print(target)
    else:
        assets = sorted(p for p in dist.iterdir() if p.is_file() and p.suffix in (".zip", ".whl", ".gz"))
        if not assets:
            parser.error("no release assets found")
        lines = []
        for path in assets:
            with path.open("rb") as source:
                checksum = hashlib.file_digest(source, "sha256").hexdigest()
            lines.append(f"{checksum}  {path.name}\n")
        (dist / "SHA256SUMS.txt").write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
