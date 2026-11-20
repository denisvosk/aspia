"""Package verified MSI assets as a static Caddy-compatible download site."""

import argparse
import hashlib
import html
import json
import re
import shutil
import zipfile
from pathlib import Path

PRODUCTS = {
    "console": ("Консоль", "Адресная книга, журнал сеансов и отчёт по компьютерам."),
    "host": ("Host", "Устанавливается на рабочих компьютерах."),
    "router": ("Router", "Центральный сервер и хранение журнала."),
    "client": ("Клиент", "Отдельное приложение для подключения."),
}


def package_site(packages: Path, output: Path, version: str, commit: str, tag: str):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid version")
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Invalid source commit")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", tag):
        raise ValueError("Invalid release tag")
    required = [f"aspia-{product}-{version}-{arch}.msi" for product in PRODUCTS for arch in ("x86_64", "x86")]
    required += [f"aspia-{version}-audit-inventory-source.zip", "LICENSE.md", "README-preview.md", "build-info-x86.json", "build-info-x86_64.json"]
    for name in required:
        file = packages / name
        if not file.is_file() or file.is_symlink() or file.stat().st_size == 0:
            raise ValueError(f"Missing release file: {name}")
        if name.endswith(".msi"):
            with file.open("rb") as stream:
                if stream.read(8) != bytes.fromhex("d0cf11e0a1b11ae1"):
                    raise ValueError(f"Invalid MSI container: {name}")
    root = output / "aspia-downloads"
    if root.exists():
        raise ValueError("Output already exists; use a new output directory")
    files = root / "site" / "files"
    files.mkdir(parents=True)
    entries = []
    for name in required:
        dst = files / name
        shutil.copyfile(packages / name, dst)
        checksum = hashlib.sha256()
        with dst.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                checksum.update(chunk)
        digest = checksum.hexdigest()
        entries.append({"file": name, "size_bytes": dst.stat().st_size, "sha256": digest})
    manifest = {"version": version, "tag": tag, "source_commit": commit, "channel": "preview", "files": entries}
    (root / "site" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sums = "".join(f"{entry['sha256']}  files/{entry['file']}\n" for entry in entries)
    (root / "site" / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    cards = []
    for product, (title, description) in PRODUCTS.items():
        links = []
        for arch, label in (("x86_64", "Windows x64"), ("x86", "Windows x86")):
            name = f"aspia-{product}-{version}-{arch}.msi"
            size = next(e["size_bytes"] for e in entries if e["file"] == name) / (1024 * 1024)
            links.append(f'<a class="download" href="files/{name}" download>{label}<small>{size:.1f} МиБ · MSI</small></a>')
        cards.append(f'<article><h2>{title}</h2><p>{description}</p><div class="links">{"".join(links)}</div></article>')
    page = """<!doctype html>
<html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aspia+ — загрузки {version}</title>
<style>
:root{{color-scheme:light;font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;color:#193044;background:#eef3f6}}
*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:960px;margin:auto;padding:48px 24px}}
.eyebrow{{color:#47687b;font-weight:650;letter-spacing:.08em}}h1{{font-size:clamp(30px,5vw,44px);line-height:1.15;margin:10px 0 16px}}
.intro{{max-width:760px}}.note{{background:#fff6dd;border-left:4px solid #c48b19;padding:14px 18px;border-radius:6px;margin:24px 0}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}article{{background:white;border:1px solid #d5e0e7;border-radius:12px;padding:24px}}
h2{{font-size:23px;margin:0 0 8px}}article p{{min-height:50px;margin:0 0 18px;color:#526773}}.links{{display:flex;gap:10px;flex-wrap:wrap}}
a{{color:#075d83}}a.download{{display:block;text-decoration:none;border-radius:7px;background:#e6f2f8;padding:10px 16px;font-weight:650}}a.download:hover{{background:#d1e8f3}}small{{display:block;font-weight:400;font-size:12px;color:#526773}}
.details{{margin-top:28px;padding:22px 0;border-top:1px solid #cddce5}}.details a{{margin-right:20px;display:inline-block}}code{{overflow-wrap:anywhere;font-size:13px}}
@media(max-width:620px){{main{{padding:28px 16px}}.grid{{grid-template-columns:1fr}}article p{{min-height:0}}}}
</style><main>
<div class="eyebrow">ASPIA+ · WINDOWS</div><h1>Загрузки {version}</h1>
<p class="intro">Консоль администратора, рабочие компьютеры и сервер. Выберите компонент и разрядность уже установленной программы.</p>
<div class="note"><strong>Предварительный выпуск.</strong> Перед обновлением рабочих компьютеров проверьте подключение на пилотном ПК. Установка пакетов выполняется вручную; автоматическое обновление этим комплектом не включается.</div>
<section class="grid">{cards}</section>
<section class="details"><h2>Перед установкой</h2><p>Для центрального журнала нужны новые Router, Host и Console. Relay остаётся версии 2.7. Сохраните конфигурацию и базу Router перед его обновлением. Подробный состав изменений и ограничения находятся в описании выпуска.</p>
<a href="files/README-preview.md">Описание выпуска</a><a href="SHA256SUMS.txt">Контрольные суммы SHA-256</a><a href="files/aspia-{version}-audit-inventory-source.zip" download>Исходный код</a><a href="files/LICENSE.md">Лицензия</a>
<p><small>Выпуск: {tag}<br>Исходная ревизия: <code>{commit}</code></small></p></section>
</main></html>
""".format(version=html.escape(version), tag=html.escape(tag), commit=html.escape(commit), cards="".join(cards))
    (root / "site" / "index.html").write_text(page, encoding="utf-8")
    resources = Path(__file__).resolve().parents[1] / "ops" / "download-site"
    shutil.copyfile(resources / "Caddy-downloads.fragment", root / "Caddy-downloads.fragment")
    shutil.copyfile(resources / "README.md", root / "README-deploy.md")
    archive = output / f"aspia-downloads-{tag}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for file in sorted(root.rglob("*")):
            if file.is_file():
                bundle.write(file, file.relative_to(output))
    return archive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    print(package_site(args.packages, args.output, args.version, args.commit, args.tag))


if __name__ == "__main__":
    main()
