import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Iterable

FILE_HEADER_TMPL = "\n\n===== FILE: {path} =====\n"


def load_config(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sha256_short(path: Path, n: int = 12) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:n]


def is_under(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def collect_files(root: Path, cfg: Dict) -> List[Path]:
    include_dirs = [root / d for d in cfg["include"]["dirs"]]
    ex_dirs = set(cfg["exclude"].get("dirs", []))
    ex_files = set(cfg["exclude"].get("files", []))
    exts = set(cfg["include"]["extensions"])

    result: List[Path] = []

    for inc in include_dirs:
        if not inc.exists():
            continue

        for p in inc.rglob("*"):
            if not p.is_file():
                continue

            if p.name in ex_files:
                continue

            if p.suffix not in exts:
                continue

            if any(part in ex_dirs for part in p.parts):
                continue

            result.append(p)

    return sorted(result)


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def write_manifest(out_dir: Path, cfg: Dict, files: List[Path]):
    manifest = {
        "root": str(Path(cfg["root"]).resolve()),
        "file_count": len(files),
        "config": cfg,
    }
    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def export_bundles(
    root: Path,
    out_dir: Path,
    files: List[Path],
    max_bytes: int,
    encoding: str,
):
    index_lines = []
    bundle_id = 1
    cur_bytes = 0
    bundle_path = out_dir / f"bundle_{bundle_id:04d}.txt"
    bundle_fp = open(bundle_path, "w", encoding=encoding)

    def new_bundle():
        nonlocal bundle_id, cur_bytes, bundle_fp, bundle_path
        bundle_fp.close()
        bundle_id += 1
        cur_bytes = 0
        bundle_path = out_dir / f"bundle_{bundle_id:04d}.txt"
        bundle_fp = open(bundle_path, "w", encoding=encoding)

    for p in files:
        rel = p.relative_to(root)
        header = FILE_HEADER_TMPL.format(path=str(rel))
        try:
            content = p.read_text(encoding=encoding)
        except Exception as e:
            content = f"<<FAILED TO READ FILE: {e}>>"

        block = header + content
        size = len(block.encode(encoding))

        if cur_bytes + size > max_bytes:
            new_bundle()

        bundle_fp.write(block)
        cur_bytes += size

        index_lines.append(
            f"{rel}\t{p.stat().st_size}\t{sha256_short(p)}\tbundle_{bundle_id:04d}.txt"
        )

    bundle_fp.close()

    with open(out_dir / "index.txt", "w", encoding=encoding) as f:
        f.write("\n".join(index_lines))


def main():
    import argparse

    ap = argparse.ArgumentParser("export_sandbox")
    ap.add_argument("--config", required=True, help="export_config.json")
    args = ap.parse_args()

    cfg = load_config(args.config)
    root = Path(cfg["root"]).resolve()
    out_dir = Path(cfg["output_dir"]).resolve()
    ensure_dir(out_dir)

    files = collect_files(root, cfg)

    write_manifest(out_dir, cfg, files)

    export_bundles(
        root=root,
        out_dir=out_dir,
        files=files,
        max_bytes=cfg["bundle"]["max_bytes"],
        encoding=cfg["bundle"].get("encoding", "utf-8"),
    )

    print(f"[export_sandbox] done. files={len(files)} out={out_dir}")


if __name__ == "__main__":
    main()
