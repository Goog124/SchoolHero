"""Собрать работу на сдачу: архив исходников и (если есть Docker) образ.

    python tools/package.py              # zip + sha256, образ — если доступен docker
    python tools/package.py --no-image   # только исходники
    python tools/package.py --version 1.0.0

Результат в dist/:
    school-hero-<версия>.zip            исходники из `git archive HEAD`
    school-hero-<версия>.zip.sha256
    school-hero-image-<версия>.tar.gz   `docker save` образа (если есть docker)
    school-hero-image-<версия>.tar.gz.sha256

В архив попадает только закоммиченное: .env, data/, static/, node_modules и
прочее из .gitignore туда не попадают. Скрипт дополнительно проверяет
содержимое архива и останавливается, если там нашлось запрещённое.
Работает на Windows, Linux и macOS; нужен только git (и docker для образа).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
NAME = "school-hero"

# Закоммиченное, но ненужное проверяющему: настройки IDE.
EXCLUDE_FROM_ARCHIVE = (".idea",)

# Пути (относительно корня проекта), которых не должно быть в архиве.
FORBIDDEN_EXACT = {".env"}
FORBIDDEN_PREFIXES = ("data/", "static/", "dist/", ".venv/", ".idea/")
FORBIDDEN_PARTS = {"node_modules", "__pycache__", ".pytest_cache"}
FORBIDDEN_SUFFIXES = (".db", ".db-wal", ".db-shm", ".pyc")


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, check=True, text=True, capture_output=True, **kw)


def git(*args: str) -> str:
    return run(["git", *args]).stdout.strip()


def detect_version() -> str:
    """Тег, указывающий на HEAD, иначе дата коммита и короткий хеш."""
    try:
        tag = git("describe", "--tags", "--exact-match", "HEAD")
        if tag:
            return tag.lstrip("v")
    except subprocess.CalledProcessError:
        pass
    stamp = git("show", "-s", "--format=%cd", "--date=format:%Y%m%d", "HEAD")
    return f"{stamp}-{git('rev-parse', '--short', 'HEAD')}"


def sha256_file(path: Path) -> Path:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    out = path.with_name(path.name + ".sha256")
    # Формат sha256sum: проверка `sha256sum -c <файл>.sha256` из dist/.
    out.write_text(f"{h.hexdigest()}  {path.name}\n", encoding="ascii", newline="\n")
    return out


def forbidden(rel: str) -> bool:
    if rel in FORBIDDEN_EXACT or rel.endswith("/.env"):
        return True
    if rel.startswith(FORBIDDEN_PREFIXES) or rel.endswith(FORBIDDEN_SUFFIXES):
        return True
    return any(part in FORBIDDEN_PARTS for part in rel.split("/"))


def build_zip(version: str) -> Path:
    prefix = f"{NAME}-{version}/"
    out = DIST / f"{NAME}-{version}.zip"
    excludes = [f":(exclude){p}" for p in EXCLUDE_FROM_ARCHIVE]
    run(["git", "archive", "--format=zip", f"--prefix={prefix}", "-o", str(out), "HEAD", "--", ".", *excludes])
    with zipfile.ZipFile(out) as zf:
        names = [n[len(prefix):] for n in zf.namelist() if n.startswith(prefix)]
    bad = [n for n in names if n and forbidden(n)]
    if bad:
        out.unlink()
        sys.exit("В архив попали файлы, которых там быть не должно (уберите их из git):\n  "
                 + "\n  ".join(bad))
    for required in ("Dockerfile", "docker-compose.yml", "README.md", ".env.example"):
        if required not in names:
            print(f"Внимание: в архиве нет {required}")
    print(f"Исходники: {out} ({out.stat().st_size // 1024} КБ, файлов: {len([n for n in names if n and not n.endswith('/')])})")
    return out


def docker_available() -> str | None:
    exe = shutil.which("docker")
    if not exe:
        return None
    try:
        subprocess.run([exe, "info"], check=True, capture_output=True, timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    return exe


def build_image(zip_path: Path, version: str, docker: str) -> Path:
    """Собирает образ из того же содержимого, что и zip (а не из рабочей папки)."""
    tag = f"{NAME}:{version}"
    out = DIST / f"{NAME}-image-{version}.tar.gz"
    with tempfile.TemporaryDirectory(prefix="school-hero-pkg-") as tmp:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
        context = Path(tmp) / f"{NAME}-{version}"
        print(f"docker build -t {tag} … (несколько минут)")
        subprocess.run([docker, "build", "-t", tag, str(context)], check=True)
    print(f"docker save {tag} | gzip > {out.name}")
    proc = subprocess.Popen([docker, "save", tag], stdout=subprocess.PIPE)
    assert proc.stdout is not None
    with gzip.open(out, "wb", compresslevel=6) as gz:
        shutil.copyfileobj(proc.stdout, gz, 1 << 20)
    if proc.wait() != 0:
        out.unlink(missing_ok=True)
        sys.exit("docker save завершился с ошибкой")
    print(f"Образ: {out} ({out.stat().st_size // (1024 * 1024)} МБ)")
    print(f"  загрузка у проверяющего: docker load -i {out.name}  (тег {tag})")
    return out


def _fix_console_encoding() -> None:
    """Windows с перенаправленным выводом (cp1252 и т. п.) не умеет кириллицу."""
    for stream in (sys.stdout, sys.stderr):
        try:
            "Ж".encode(stream.encoding or "ascii")
        except (UnicodeEncodeError, LookupError):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except AttributeError:
                pass


def main() -> None:
    _fix_console_encoding()
    parser = argparse.ArgumentParser(description="Собрать архив на сдачу в dist/")
    parser.add_argument("--version", help="версия в именах файлов (по умолчанию тег или дата-хеш)")
    parser.add_argument("--no-image", action="store_true", help="не собирать Docker-образ")
    args = parser.parse_args()

    try:
        git("rev-parse", "HEAD")
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("Нужен git и хотя бы один коммит: архив собирается из `git archive HEAD`.")

    dirty = run(["git", "status", "--porcelain", "--untracked-files=no"]).stdout.rstrip()
    if dirty:
        print("Внимание: есть незакоммиченные изменения — в архив они НЕ попадут:")
        for line in dirty.splitlines()[:20]:
            print(f"  {line}")

    version = args.version or detect_version()
    DIST.mkdir(exist_ok=True)
    print(f"Версия: {version}")

    zip_path = build_zip(version)
    produced = [zip_path, sha256_file(zip_path)]

    if args.no_image:
        print("Образ: пропущен (--no-image)")
    else:
        docker = docker_available()
        if docker is None:
            print("Образ: пропущен — docker не найден или демон не запущен. "
                  "Соберите позже на машине с Docker: python tools/package.py")
        else:
            image = build_image(zip_path, version, docker)
            produced += [image, sha256_file(image)]

    print("\nГотово, файлы в dist/:")
    for p in produced:
        print(f"  {p.name}")
    print("Что входит и как проверять: docs/submission.md")


if __name__ == "__main__":
    main()
