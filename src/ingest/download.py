"""Télécharge le zip NASA (vérifié par sha256) et extrait les zips imbriqués. Idempotent."""

import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path

from .config import DATA_DIR, DEFAULT_SOURCE, SOURCE_SHA256, SOURCE_URL


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(zip_path: Path = DATA_DIR / "nasa_zip" / "battery.zip") -> Path:
    if zip_path.exists() and sha256_file(zip_path) == SOURCE_SHA256:
        print(f"zip déjà présent et vérifié : {zip_path}")
        return zip_path
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = zip_path.with_suffix(".part")
    print(f"téléchargement de {SOURCE_URL}")
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as resp, tmp.open("wb") as out:
        shutil.copyfileobj(resp, out)
    got = sha256_file(tmp)
    if got != SOURCE_SHA256:
        tmp.unlink()
        raise RuntimeError(
            f"sha256 inattendu ({got}). Le fichier NASA a peut-être changé : "
            "vérifier le contenu puis mettre à jour SOURCE_SHA256 dans config.py."
        )
    tmp.replace(zip_path)
    return zip_path


def extract(zip_path: Path, out_dir: Path = DEFAULT_SOURCE) -> Path:
    marker = out_dir / f".extracted-{SOURCE_SHA256[:12]}"
    if marker.exists():
        print(f"déjà extrait : {out_dir}")
        return out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)  # extractall neutralise les chemins absolus et ".."
    for inner in sorted(out_dir.rglob("*.zip")):
        with zipfile.ZipFile(inner) as z:
            z.extractall(inner.with_suffix(""))
    marker.touch()
    return out_dir


if __name__ == "__main__":
    extract(download())
