#!/usr/bin/env python3
"""Build a flat APT repository from debs/*.deb using the Python standard library."""

from __future__ import annotations

import argparse
import bz2
import gzip
import hashlib
import io
import lzma
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path


GENERATED_FIELDS = {
    "filename",
    "size",
    "md5sum",
    "sha1",
    "sha256",
    "sha512",
}
REQUIRED_FIELDS = {"package", "version", "architecture", "description"}


def read_ar_members(path: Path) -> dict[str, bytes]:
    data = path.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise ValueError("not a Debian ar archive")

    members: dict[str, bytes] = {}
    offset = 8
    while offset < len(data):
        header = data[offset : offset + 60]
        if len(header) != 60 or header[58:60] != b"`\n":
            raise ValueError("invalid ar member header")
        name = header[:16].decode("utf-8", "replace").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        start = offset + 60
        end = start + size
        members[name] = data[start:end]
        offset = end + (size % 2)
    return members


def decompress_control_archive(name: str, data: bytes) -> bytes:
    if name.endswith(".gz"):
        return gzip.decompress(data)
    if name.endswith(".xz"):
        return lzma.decompress(data)
    if name.endswith(".bz2"):
        return bz2.decompress(data)
    if name.endswith(".zst"):
        if not shutil.which("zstd"):
            raise RuntimeError("zstd is required to read control.tar.zst")
        return subprocess.run(
            ["zstd", "--decompress", "--quiet", "--stdout"],
            input=data,
            check=True,
            capture_output=True,
        ).stdout
    if name == "control.tar":
        return data
    raise ValueError(f"unsupported control archive: {name}")


def parse_control(text: str) -> list[tuple[str, list[str]]]:
    fields: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if not line:
            continue
        if line[0].isspace():
            if not fields:
                raise ValueError("orphaned continuation line in control file")
            fields[-1][1].append(line)
            continue
        if ":" not in line:
            raise ValueError(f"invalid control line: {line!r}")
        key, value = line.split(":", 1)
        fields.append((key, [value.lstrip()]))
    return fields


def control_value(fields: list[tuple[str, list[str]]], key: str) -> str | None:
    wanted = key.casefold()
    for field, values in fields:
        if field.casefold() == wanted:
            return values[0]
    return None


def extract_control(path: Path) -> list[tuple[str, list[str]]]:
    members = read_ar_members(path)
    candidates = [name for name in members if name.startswith("control.tar")]
    if len(candidates) != 1:
        raise ValueError("expected exactly one control.tar archive")

    archive = decompress_control_archive(candidates[0], members[candidates[0]])
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as control_tar:
        member = next(
            (item for item in control_tar.getmembers() if item.name.lstrip("./") == "control"),
            None,
        )
        if member is None:
            raise ValueError("control file is missing")
        extracted = control_tar.extractfile(member)
        if extracted is None:
            raise ValueError("control file cannot be read")
        fields = parse_control(extracted.read().decode("utf-8", "replace"))

    present = {key.casefold() for key, _ in fields}
    missing = sorted(REQUIRED_FIELDS - present)
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    return fields


def digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def package_paragraph(deb: Path, relative_name: str) -> tuple[str, str]:
    fields = extract_control(deb)
    lines: list[str] = []
    for key, values in fields:
        if key.casefold() in GENERATED_FIELDS:
            continue
        lines.append(f"{key}: {values[0]}")
        lines.extend(values[1:])

    lines.extend(
        [
            f"Filename: {relative_name}",
            f"Size: {deb.stat().st_size}",
            f"MD5sum: {digest(deb, 'md5')}",
            f"SHA1: {digest(deb, 'sha1')}",
            f"SHA256: {digest(deb, 'sha256')}",
            f"SHA512: {digest(deb, 'sha512')}",
        ]
    )
    architecture = control_value(fields, "Architecture") or "all"
    return "\n".join(lines), architecture


def write_release(output: Path, index_names: list[str], architectures: set[str]) -> None:
    visible_architectures = sorted(architectures - {"all"}) or ["iphoneos-arm", "iphoneos-arm64"]
    lines = [
        "Origin: IYAWAY",
        "Label: IYAWAY",
        "Suite: stable",
        "Version: 1.0",
        "Codename: ios",
        f"Architectures: {' '.join(visible_architectures)}",
        "Components: main",
        "Description: IYAWAY jailbreak repository",
        f"Date: {format_datetime(datetime.now(UTC), usegmt=True)}",
    ]
    for label, algorithm in (
        ("MD5Sum", "md5"),
        ("SHA1", "sha1"),
        ("SHA256", "sha256"),
        ("SHA512", "sha512"),
    ):
        lines.append(f"{label}:")
        for name in index_names:
            path = output / name
            lines.append(f" {digest(path, algorithm)} {path.stat().st_size:16d} {name}")
    (output / "Release").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build(root: Path, output: Path) -> int:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    site = root / "site"
    if site.exists():
        shutil.copytree(site, output, dirs_exist_ok=True)

    source_debs = root / "debs"
    published_debs = output / "debs"
    published_debs.mkdir()

    paragraphs: list[str] = []
    architectures: set[str] = set()
    for deb in sorted(source_debs.glob("*.deb"), key=lambda item: item.name.casefold()):
        target = published_debs / deb.name
        shutil.copy2(deb, target)
        try:
            paragraph, architecture = package_paragraph(deb, f"debs/{deb.name}")
        except Exception as error:
            raise RuntimeError(f"{deb.name}: {error}") from error
        paragraphs.append(paragraph)
        architectures.add(architecture)

    packages = ("\n\n".join(paragraphs) + ("\n" if paragraphs else "")).encode()
    (output / "Packages").write_bytes(packages)
    with (output / "Packages.gz").open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as compressed:
            compressed.write(packages)
    (output / "Packages.bz2").write_bytes(bz2.compress(packages, compresslevel=9))
    (output / "Packages.xz").write_bytes(lzma.compress(packages, preset=9))

    index_names = ["Packages", "Packages.gz", "Packages.bz2", "Packages.xz"]
    if shutil.which("zstd"):
        with (output / "Packages.zst").open("wb") as compressed:
            subprocess.run(
                ["zstd", "--compress", "--quiet", "-19", "--stdout"],
                input=packages,
                check=True,
                stdout=compressed,
            )
        index_names.append("Packages.zst")

    write_release(output, index_names, architectures)
    print(f"Built {len(paragraphs)} package(s) in {output}")
    return len(paragraphs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="public", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    output = args.output if args.output.is_absolute() else root / args.output
    build(root, output)


if __name__ == "__main__":
    main()
