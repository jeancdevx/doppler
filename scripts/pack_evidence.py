#!/usr/bin/env python3
"""Empaqueta una ejecución de evidencia en ZIP con manifiesto SHA-256 y auditoría antisecretos."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

FORBIDDEN_PATTERNS = [
    re.compile(r"R2_SECRET_ACCESS_KEY\s*=\s*(?!replace_with_)\S+"),
    re.compile(r"R2_ACCESS_KEY_ID\s*=\s*(?!replace_with_)\S+"),
    re.compile(r"ADMIN_API_TOKEN\s*=\s*(?!replace_with_)\S+"),
    re.compile(r"X-Admin-Token\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"X-Amz-Signature=[0-9a-f]{32,}"),
    re.compile(r"doppler_session=[0-9a-f]{16,}\.[0-9a-f]{64}"),
    re.compile(r"SESSION_HMAC_SECRET\s*=\s*(?!replace_with_)\S+"),
]

FORBIDDEN_EXTENSIONS = {
    ".pt",
    ".pth",
    ".wav",
    ".env",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".sqlite-wal",
    ".sqlite-shm",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_directory(run_dir: Path) -> None:
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in FORBIDDEN_EXTENSIONS or path.name == ".env":
            raise RuntimeError(f"Archivo prohibido dentro de evidencias: {path}")
        if path.suffix.lower() in {".json", ".csv", ".md", ".txt", ".svg", ".yaml", ".yml"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in FORBIDDEN_PATTERNS:
                if pat.search(text):
                    raise RuntimeError(f"Posible secreto o URL firmada detectado en {path}")


def pack_run(run_dir: Path) -> tuple[Path, Path]:
    if not run_dir.is_dir():
        raise FileNotFoundError(f"No existe el directorio de evidencia: {run_dir}")

    audit_directory(run_dir)

    files = sorted(
        p for p in run_dir.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt"
    )
    manifest_lines = [
        f"{sha256_file(p)}  {p.relative_to(run_dir).as_posix()}" for p in files
    ]
    sums_path = run_dir / "SHA256SUMS.txt"
    sums_path.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    zip_path = run_dir.parent / f"{run_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(run_dir.rglob("*")):
            if p.is_file():
                arcname = f"{run_dir.name}/{p.relative_to(run_dir).as_posix()}"
                zf.write(p, arcname=arcname)

    zip_sha = sha256_file(zip_path)
    zip_sha_path = run_dir.parent / f"{run_dir.name}.zip.sha256"
    zip_sha_path.write_text(f"{zip_sha}  {zip_path.name}\n", encoding="utf-8")

    print(f"ZIP generado: {zip_path}")
    print(f"SHA-256 ZIP:  {zip_sha}")
    print(f"Manifiesto:   {zip_sha_path}")
    return zip_path, zip_sha_path


def find_latest_run(evidence_root: Path) -> Path:
    candidates = sorted(
        (p for p in evidence_root.iterdir() if p.is_dir() and (p / "manifest.json").is_file()),
        key=lambda p: p.name,
    )
    if not candidates:
        raise FileNotFoundError(f"No se encontraron carpetas de evidencia en {evidence_root}")
    return candidates[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Empaquetar evidencias Doppler en ZIP con SHA-256")
    parser.add_argument("run_dir", nargs="?", type=Path, default=None)
    args = parser.parse_args()
    target = args.run_dir if args.run_dir else find_latest_run(Path("evidence"))
    pack_run(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
