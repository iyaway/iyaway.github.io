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
