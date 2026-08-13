import gzip
import importlib.util
import io
import tarfile
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_repo.py"
SPEC = importlib.util.spec_from_file_location("build_repo", MODULE_PATH)
build_repo = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_repo)


def ar_member(name: str, payload: bytes) -> bytes:
    header = (
        f"{name + '/':<16}"
        f"{0:<12}"
        f"{0:<6}"
        f"{0:<6}"
        f"{0o100644:<8o}"
        f"{len(payload):<10}"
        "`\n"
    ).encode("ascii")
    return header + payload + (b"\n" if len(payload) % 2 else b"")


def make_deb(path: Path, control: str) -> None:
    control_buffer = io.BytesIO()
    with tarfile.open(fileobj=control_buffer, mode="w") as archive:
        payload = control.encode()
        info = tarfile.TarInfo("./control")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    empty_data_buffer = io.BytesIO()
    with tarfile.open(fileobj=empty_data_buffer, mode="w"):
        pass

    path.write_bytes(
        b"!<arch>\n"
        + ar_member("debian-binary", b"2.0\n")
        + ar_member("control.tar.gz", gzip.compress(control_buffer.getvalue()))
        + ar_member("data.tar.gz", gzip.compress(empty_data_buffer.getvalue()))
    )


class BuildRepoTests(unittest.TestCase):
    def test_builds_package_indexes_from_deb(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "debs").mkdir()
            (root / "site").mkdir()
            (root / "site" / "index.html").write_text("repo", encoding="utf-8")
            make_deb(
                root / "debs" / "demo.deb",
                "\n".join(
                    [
                        "Package: com.iyaway.demo",
                        "Name: Demo",
                        "Version: 1.0.0",
                        "Architecture: iphoneos-arm64",
                        "Description: Demo package",
                        " second line",
                        "Maintainer: IYAWAY",
                        "",
                    ]
                ),
            )

            count = build_repo.build(root, root / "public")
            packages = (root / "public" / "Packages").read_text()
            release = (root / "public" / "Release").read_text()

            self.assertEqual(count, 1)
            self.assertIn("Package: com.iyaway.demo", packages)
            self.assertIn("Filename: debs/demo.deb", packages)
            self.assertIn("SHA256:", packages)
            self.assertIn("Architectures: iphoneos-arm64", release)
            self.assertTrue((root / "public" / "debs" / "demo.deb").is_file())
            self.assertEqual((root / "public" / "index.html").read_text(), "repo")


if __name__ == "__main__":
    unittest.main()
