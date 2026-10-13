#!/usr/bin/env python3
"""bundle/ 을 ~/.claude 에 설치한다. 받는 쪽 서버에서 쓴다.

    python3 install.py --dry-run                          # 무엇이 바뀔지만 보여 준다
    python3 install.py                                    # 전부 설치한다
    python3 install.py --skip skills/foo settings:model   # 일부는 빼고 설치한다

내용이 다른 파일이 이미 있으면 백업 폴더로 옮긴 뒤 복사한다.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent / "bundle"
PAYLOAD = BUNDLE / "payload"
DEST = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def check_manifest():
    for line in (BUNDLE / "MANIFEST.sha256").read_text().splitlines():
        digest, rel = line.split("  ", 1)
        if hashlib.sha256((BUNDLE / rel).read_bytes()).hexdigest() != digest:
            sys.exit(f"묶음이 손상됐다: {rel}")


def setting_steps(fragment):
    """settings.fragment.json 을 따로 넣고 뺄 수 있는 (항목, 경로, 값) 으로 쪼갠다."""
    steps = []
    for key, val in fragment.items():
        if isinstance(val, dict):
            steps += [(f"settings:{key}.{sub}", (key, sub), v) for sub, v in val.items()]
        else:
            steps.append((f"settings:{key}", (key,), val))
    return steps


def show(value):
    return "(없음)" if value is None else json.dumps(value, ensure_ascii=False)


def merge(settings, path, value):
    """목록은 없는 것만 더하고, 나머지는 값을 바꾼다. 바뀐 내용을 한 줄로 돌려준다 (같으면 None)."""
    d = settings
    for k in path[:-1]:
        d = d.setdefault(k, {})
    old = d.get(path[-1])
    if isinstance(value, list) and isinstance(old, list):
        added = [v for v in value if v not in old]
        if not added:
            return None
        d[path[-1]] = old + added
        return "+ " + ", ".join(show(v) for v in added)
    if old == value:
        return None
    d[path[-1]] = value
    return f"{show(old)} -> {show(value)}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="무엇이 바뀔지만 보여 주고 아무것도 바꾸지 않는다")
    ap.add_argument("--skip", nargs="*", default=[], metavar="ID", help="설치하지 않을 항목 (미리 보기에 나온 이름)")
    args = ap.parse_args()
    check_manifest()

    items = {}  # 항목(skills/이름, CLAUDE.md ...) -> 그 안의 파일들
    for f in sorted(p for p in PAYLOAD.rglob("*") if p.is_file()):
        rel = f.relative_to(PAYLOAD)
        items.setdefault("/".join(rel.parts[:2]), []).append(rel)
    steps = setting_steps(json.loads((BUNDLE / "settings.fragment.json").read_text()))
    unknown = [i for i in args.skip if i not in set(items) | {s[0] for s in steps}]
    if unknown:
        ap.error("모르는 항목: " + ", ".join(unknown))

    backup = DEST / "claude-setup-backup" / datetime.now().strftime("%Y%m%d-%H%M%S")
    for item, files in items.items():
        if item in args.skip:
            print(f"skipped   {item}")
            continue
        new = [f for f in files if not (DEST / f).is_file()]
        differ = [f for f in files if f not in new and (DEST / f).read_bytes() != (PAYLOAD / f).read_bytes()]
        label = "same" if not new and not differ else "new" if len(new) == len(files) else "changed"
        print(f"{label:<9} {item}  (new {len(new)}, replaced {len(differ)}, same {len(files) - len(new) - len(differ)})")
        for f in differ:
            print(f"          replaced {f}")
        if args.dry_run:
            continue
        for f in differ:
            (backup / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(DEST / f, backup / f)
        for f in new + differ:
            (DEST / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PAYLOAD / f, DEST / f)

    path = DEST / "settings.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    new = json.loads(json.dumps(old))
    for item, where, value in steps:
        if item in args.skip:
            print(f"skipped   {item}")
            continue
        change = merge(new, where, value)
        print(f"{'set' if change else 'same':<9} {item}" + (f"  {change}" if change else ""))
    if new != old and not args.dry_run:
        if path.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
        DEST.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n")

    if args.dry_run:
        print("\n미리 보기다. 아무것도 바꾸지 않았다.")
    else:
        print(f"\n{DEST} 에 설치했다." + (f" 바뀌기 전 파일: {backup}" if backup.exists() else ""))


if __name__ == "__main__":
    main()
