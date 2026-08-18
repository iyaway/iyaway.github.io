#!/usr/bin/env python3
"""Build a flat APT repository from debs/*.deb using the Python standard library."""

from __future__ import annotations

import argparse
import bz2
import gzip
import hashlib
import html
import io
import json
import lzma
import re
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
REPO_URL = "https://iyaway.github.io"
PACKAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+.-]+$")
METADATA_CONTROL_FIELDS = {
    "name",
    "description",
    "author",
    "depiction",
    "sileodepiction",
    "icon",
}


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


def metadata_control_lines(info: dict, has_icon: bool) -> list[str]:
    package = info["package"]
    depiction_url = f"{REPO_URL}/depictions/{package}"
    lines = [
        f"Name: {info['name']}",
        f"Description: {info['tagline']}",
        f"Author: {info['developer']}",
        f"Depiction: {depiction_url}/",
        f"SileoDepiction: {depiction_url}/sileo.json",
    ]
    if has_icon:
        lines.append(f"Icon: {depiction_url}/icon.png")
    return lines


def package_paragraph(
    deb: Path,
    relative_name: str,
    package_infos: dict[str, tuple[dict, Path]],
) -> tuple[str, str]:
    fields = extract_control(deb)
    package = control_value(fields, "Package") or ""
    info_entry = package_infos.get(package)
    lines: list[str] = []
    for key, values in fields:
        if key.casefold() in GENERATED_FIELDS:
            continue
        if info_entry and key.casefold() in METADATA_CONTROL_FIELDS:
            continue
        lines.append(f"{key}: {values[0]}")
        lines.extend(values[1:])

    if info_entry:
        info, info_dir = info_entry
        lines.extend(metadata_control_lines(info, (info_dir / "icon.png").is_file()))

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


def require_string(info: dict, key: str, source: Path) -> str:
    value = info.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: {key} must be a non-empty string")
    return value.strip()


def load_package_infos(root: Path) -> dict[str, tuple[dict, Path]]:
    package_infos: dict[str, tuple[dict, Path]] = {}
    info_root = root / "package-info"
    if not info_root.exists():
        return package_infos

    for source in sorted(info_root.glob("*/info.json")):
        with source.open(encoding="utf-8") as stream:
            info = json.load(stream)
        if not isinstance(info, dict):
            raise ValueError(f"{source}: root value must be an object")

        for key in ("package", "name", "tagline", "developer"):
            info[key] = require_string(info, key, source)
        web_name = info.get("web_name")
        if web_name is not None:
            if not isinstance(web_name, str) or not web_name.strip():
                raise ValueError(f"{source}: web_name must be a non-empty string")
            info["web_name"] = web_name.strip()
        package = info["package"]
        if not PACKAGE_ID_PATTERN.fullmatch(package):
            raise ValueError(f"{source}: invalid package identifier")
        if source.parent.name != package:
            raise ValueError(f"{source}: directory name must match package identifier")
        if package in package_infos:
            raise ValueError(f"{source}: duplicate package metadata")

        for key in ("description", "features", "compatibility", "usage", "screenshots"):
            value = info.get(key, [])
            if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                raise ValueError(f"{source}: {key} must be an array of non-empty strings")
            info[key] = value

        notice = info.get("notice")
        if notice is not None:
            if not isinstance(notice, str) or not notice.strip():
                raise ValueError(f"{source}: notice must be a non-empty string")
            info["notice"] = notice.strip()

        changelog = info.get("changelog", [])
        if not isinstance(changelog, list):
            raise ValueError(f"{source}: changelog must be an array")
        for release in changelog:
            if not isinstance(release, dict):
                raise ValueError(f"{source}: changelog entries must be objects")
            require_string(release, "version", source)
            changes = release.get("changes")
            if not isinstance(changes, list) or not all(isinstance(item, str) and item for item in changes):
                raise ValueError(f"{source}: changelog changes must be non-empty strings")
        info["changelog"] = changelog

        locales = info.get("locales", {})
        if not isinstance(locales, dict):
            raise ValueError(f"{source}: locales must be an object")
        for locale, localized in locales.items():
            if locale != "en":
                raise ValueError(f"{source}: unsupported locale {locale!r}")
            if not isinstance(localized, dict):
                raise ValueError(f"{source}: locale {locale!r} must be an object")
            localized["name"] = require_string(localized, "name", source)
            localized["tagline"] = require_string(localized, "tagline", source)
            localized_notice = localized.get("notice")
            if localized_notice is not None:
                if not isinstance(localized_notice, str) or not localized_notice.strip():
                    raise ValueError(
                        f"{source}: locales.{locale}.notice must be a non-empty string"
                    )
                localized["notice"] = localized_notice.strip()
            for key in ("description", "features", "compatibility", "usage"):
                value = localized.get(key, [])
                if not isinstance(value, list) or not all(
                    isinstance(item, str) and item for item in value
                ):
                    raise ValueError(
                        f"{source}: locales.{locale}.{key} must be an array of non-empty strings"
                    )
                localized[key] = value
            localized_changelog = localized.get("changelog", [])
            if not isinstance(localized_changelog, list):
                raise ValueError(f"{source}: locales.{locale}.changelog must be an array")
            for release in localized_changelog:
                if not isinstance(release, dict):
                    raise ValueError(
                        f"{source}: locales.{locale}.changelog entries must be objects"
                    )
                require_string(release, "version", source)
                changes = release.get("changes")
                if not isinstance(changes, list) or not all(
                    isinstance(item, str) and item for item in changes
                ):
                    raise ValueError(
                        f"{source}: locales.{locale}.changelog changes must be non-empty strings"
                    )
            localized["changelog"] = localized_changelog
        info["locales"] = locales

        tint = info.get("tint", "#725AFF")
        if not isinstance(tint, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", tint):
            raise ValueError(f"{source}: tint must be a six-digit hex color")
        info["tint"] = tint

        for screenshot in info["screenshots"]:
            screenshot_path = source.parent / "screenshots" / screenshot
            if Path(screenshot).name != screenshot or not screenshot_path.is_file():
                raise ValueError(f"{source}: missing or unsafe screenshot {screenshot!r}")
        package_infos[package] = (info, source.parent)
    return package_infos


def web_locale(info: dict, locale: str) -> dict:
    if locale == "zh-Hans":
        localized = dict(info)
        localized["name"] = info.get("web_name", info["name"])
        return localized
    return info.get("locales", {}).get(locale, info)


def write_web_metadata(output: Path, package_infos: dict[str, tuple[dict, Path]]) -> None:
    metadata = {}
    for package, (info, _) in package_infos.items():
        metadata[package] = {
            locale: {
                "name": web_locale(info, locale)["name"],
                "tagline": web_locale(info, locale)["tagline"],
            }
            for locale in ("zh-Hans", "en")
        }
    (output / "package-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def markdown_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def make_sileo_language_views(info: dict, info_dir: Path, locale: str) -> list[dict]:
    localized = web_locale(info, locale)
    is_english = locale == "en"
    labels = {
        "features": "Features" if is_english else "功能",
        "usage": "Usage" if is_english else "使用方法",
        "compatibility": "Compatibility" if is_english else "兼容性",
        "developer": "Developer" if is_english else "开发者",
        "source": "View Source" if is_english else "查看源代码",
        "changelog": "Changelog" if is_english else "更新日志",
        "version": "Version" if is_english else "版本",
        "screenshot": "screenshot" if is_english else "截图",
    }
    asset_url = f"{REPO_URL}/depictions/{info['package']}"
    views: list[dict] = [
        {
            "class": "DepictionSubheaderView",
            "title": localized["name"],
            "useBoldText": True,
            "useBottomMargin": False,
        },
        {
            "class": "DepictionMarkdownView",
            "markdown": localized["tagline"],
            "useSpacing": True,
        },
    ]
    if localized.get("notice"):
        views.append(
            {
                "class": "DepictionMarkdownView",
                "markdown": f"> **{localized['notice']}**",
                "useSpacing": True,
            }
        )
    if info["screenshots"]:
        views.append(
            {
                "class": "DepictionScreenshotsView",
                "itemSize": "{160, 346}",
                "itemCornerRadius": 12,
                "screenshots": [
                    {
                        "url": f"{asset_url}/screenshots/{filename}",
                        "accessibilityText": f"{localized['name']} {labels['screenshot']} {index}",
                    }
                    for index, filename in enumerate(info["screenshots"], start=1)
                ],
            }
        )

    markdown_sections: list[str] = []
    if localized["description"]:
        markdown_sections.append("\n\n".join(localized["description"]))
    if localized["features"]:
        markdown_sections.append(
            f"## {labels['features']}\n{markdown_list(localized['features'])}"
        )
    if localized["usage"]:
        markdown_sections.append(
            f"## {labels['usage']}\n{markdown_list(localized['usage'])}"
        )
    if markdown_sections:
        views.append(
            {
                "class": "DepictionMarkdownView",
                "markdown": "\n\n".join(markdown_sections),
                "useSpacing": True,
            }
        )
    if localized["compatibility"]:
        views.append(
            {
                "class": "DepictionTableTextView",
                "title": labels["compatibility"],
                "text": " · ".join(localized["compatibility"]),
            }
        )
    views.append(
        {
            "class": "DepictionTableTextView",
            "title": labels["developer"],
            "text": info["developer"],
        }
    )
    source_url = info.get("source")
    if source_url:
        views.append(
            {
                "class": "DepictionTableButtonView",
                "title": labels["source"],
                "action": source_url,
                "openExternal": True,
            }
        )

    if localized["changelog"]:
        views.append(
            {
                "class": "DepictionSubheaderView",
                "title": labels["changelog"],
                "useBoldText": True,
            }
        )
        for release in localized["changelog"]:
            title = f"{labels['version']} {release['version']}"
            if release.get("date"):
                title += f" · {release['date']}"
            views.extend(
                [
                    {
                        "class": "DepictionSubheaderView",
                        "title": title,
                        "useBoldText": True,
                    },
                    {
                        "class": "DepictionMarkdownView",
                        "markdown": markdown_list(release["changes"]),
                        "useSpacing": True,
                    },
                ]
            )
    return views


def make_sileo_depiction(info: dict, info_dir: Path) -> dict:
    asset_url = f"{REPO_URL}/depictions/{info['package']}"
    tabs = [
        {
            "class": "DepictionStackView",
            "tabname": label,
            "views": make_sileo_language_views(info, info_dir, locale),
        }
        for locale, label in (("zh-Hans", "中文"), ("en", "English"))
    ]

    depiction = {
        "minVersion": "0.1",
        "class": "DepictionTabView",
        "tintColor": info["tint"],
        "tabs": tabs,
    }
    if (info_dir / "banner.png").is_file():
        depiction["headerImage"] = f"{asset_url}/banner.png"
    return depiction


def html_list(items: list[str]) -> str:
    return "".join(f"<li>{html.escape(item)}</li>" for item in items)


def make_html_locale(info: dict, info_dir: Path, locale: str) -> str:
    localized = web_locale(info, locale)
    is_english = locale == "en"
    labels = {
        "back": "← Banana Repo",
        "screenshots": "Screenshots" if is_english else "截图",
        "features": "Features" if is_english else "功能",
        "usage": "Usage" if is_english else "使用方法",
        "changelog": "Changelog" if is_english else "更新日志",
        "version": "Version" if is_english else "版本",
        "developer": "Developer" if is_english else "开发者",
        "source": "View Source" if is_english else "查看源代码",
    }
    package = html.escape(info["package"])
    icon = (
        '<img class="package-icon" src="icon.png" alt="">'
        if (info_dir / "icon.png").is_file()
        else ""
    )
    screenshots = "".join(
        f'<img src="screenshots/{html.escape(filename)}" '
        f'alt="{html.escape(localized["name"])} {labels["screenshots"]} {index}">'
        for index, filename in enumerate(info["screenshots"], start=1)
    )
    screenshot_section = (
        f'<section><h2>{labels["screenshots"]}</h2><div class="screenshots">{screenshots}</div></section>'
        if screenshots
        else ""
    )
    description = "".join(
        f"<p>{html.escape(paragraph)}</p>" for paragraph in localized["description"]
    )
    description_section = (
        f'<section class="description">{description}</section>' if description else ""
    )
    notice = (
        f'<aside class="notice" role="note"><strong>{html.escape(localized["notice"])}</strong></aside>'
        if localized.get("notice")
        else ""
    )
    features = (
        f'<section><h2>{labels["features"]}</h2><ul>{html_list(localized["features"])}</ul></section>'
        if localized["features"]
        else ""
    )
    usage = (
        f'<section><h2>{labels["usage"]}</h2><ol>{html_list(localized["usage"])}</ol></section>'
        if localized["usage"]
        else ""
    )
    compatibility = "".join(
        f"<span>{html.escape(item)}</span>" for item in localized["compatibility"]
    )
    change_parts: list[str] = []
    for release in localized["changelog"]:
        date_suffix = f" · {html.escape(release['date'])}" if release.get("date") else ""
        change_parts.append(
            '<article class="release">'
            f'<h3>{labels["version"]} {html.escape(release["version"])}{date_suffix}</h3>'
            f'<ul>{html_list(release["changes"])}</ul></article>'
        )
    changes = "".join(change_parts)
    changelog = (
        f'<section><h2>{labels["changelog"]}</h2>{changes}</section>' if changes else ""
    )
    source_url = info.get("source")
    source_link = (
        f'<a class="source-link" href="{html.escape(source_url, quote=True)}">{labels["source"]}</a>'
        if source_url
        else ""
    )
    developer_separator = ": " if is_english else "："
    hidden = " hidden" if is_english else ""
    return f"""<div data-language="{locale}" lang="{'en' if is_english else 'zh-CN'}"{hidden}>
      <a class="back" href="/">{labels["back"]}</a>
      <header>{icon}<div><p class="package-id">{package}</p><h1>{html.escape(localized["name"])}</h1><p class="tagline">{html.escape(localized["tagline"])}</p></div></header>
      <div class="compatibility">{compatibility}</div>
      {notice}
      {description_section}
      {screenshot_section}
      {features}
      {usage}
      {changelog}
      <footer><span>{labels["developer"]}{developer_separator}{html.escape(info["developer"])}</span>{source_link}</footer>
    </div>"""


def make_html_depiction(info: dict, info_dir: Path) -> str:
    zh = web_locale(info, "zh-Hans")
    en = web_locale(info, "en")
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="{html.escape(info['tint'])}">
    <title>{html.escape(zh['name'])} / {html.escape(en['name'])} · Banana Repo</title>
    <meta name="description" content="{html.escape(zh['tagline'] + ' / ' + en['tagline'], quote=True)}">
    <link rel="icon" href="/icon.png">
    <link rel="stylesheet" href="/depiction.css">
  </head>
  <body style="--accent: {html.escape(info['tint'])}">
    <main>
      <nav class="language-switcher" aria-label="Language">
        <button type="button" data-language-button="zh-Hans" aria-pressed="true">中文</button>
        <button type="button" data-language-button="en" aria-pressed="false">English</button>
      </nav>
      {make_html_locale(info, info_dir, "zh-Hans")}
      {make_html_locale(info, info_dir, "en")}
    </main>
    <script src="/depiction.js"></script>
  </body>
</html>
"""


def build_depictions(output: Path, package_infos: dict[str, tuple[dict, Path]]) -> None:
    for package, (info, info_dir) in package_infos.items():
        target = output / "depictions" / package
        target.mkdir(parents=True)
        for item in info_dir.iterdir():
            if item.name == "info.json":
                continue
            destination = target / item.name
            if item.is_dir():
                shutil.copytree(item, destination)
            elif item.is_file():
                shutil.copy2(item, destination)
        (target / "index.html").write_text(make_html_depiction(info, info_dir), encoding="utf-8")
        (target / "sileo.json").write_text(
            json.dumps(make_sileo_depiction(info, info_dir), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def write_release(output: Path, index_names: list[str], architectures: set[str]) -> None:
    visible_architectures = sorted(architectures - {"all"}) or ["iphoneos-arm", "iphoneos-arm64"]
    lines = [
        "Origin: Banana",
        "Label: Banana",
        "Suite: stable",
        "Version: 1.0",
        "Codename: ios",
        f"Architectures: {' '.join(visible_architectures)}",
        "Components: main",
        "Description: Banana jailbreak repository",
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

    package_infos = load_package_infos(root)
    build_depictions(output, package_infos)
    write_web_metadata(output, package_infos)

    source_debs = root / "debs"
    published_debs = output / "debs"
    published_debs.mkdir()

    paragraphs: list[str] = []
    architectures: set[str] = set()
    for deb in sorted(source_debs.glob("*.deb"), key=lambda item: item.name.casefold()):
        target = published_debs / deb.name
        shutil.copy2(deb, target)
        try:
            paragraph, architecture = package_paragraph(
                deb,
                f"debs/{deb.name}",
                package_infos,
            )
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
