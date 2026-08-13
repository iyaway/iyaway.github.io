# IYAWAY Repo

APT repository for iOS jailbreak packages, published at <https://iyaway.github.io/>.

## Publish packages

1. Copy one or more valid `.deb` files into `debs/`.
2. Commit and push to `main`.
3. GitHub Actions validates every package, builds the APT indexes, and deploys GitHub Pages.

Build locally with:

```bash
python3 scripts/build_repo.py --output public
```

The package control file must contain at least `Package`, `Version`, `Architecture`, and `Description`.

## Package descriptions

Create `package-info/<package-id>/info.json`. The build injects `Depiction`,
`SileoDepiction`, and `Icon` fields into the generated package index, then creates
both an HTML depiction and a native Sileo depiction. Optional assets use these
conventional paths:

```text
package-info/<package-id>/
├── info.json
├── icon.png
├── banner.png
└── screenshots/
    └── 01.png
```
