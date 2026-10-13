#!/usr/bin/env bash
# bundle/ 을 ~/.claude 에 설치한다. 받는 쪽 서버에서: bash install.sh
# 내용이 다른 파일이 이미 있으면 백업 폴더로 옮긴 뒤 복사한다.
set -euo pipefail
B="$(cd "$(dirname "$0")" && pwd)/bundle"
DEST="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
BACKUP="$DEST/claude-setup-backup/$(date +%Y%m%d-%H%M%S)"

(cd "$B" && sha256sum --check --quiet MANIFEST.sha256)

cd "$B/payload"
find . -type f | sed 's|^\./||' | while read -r f; do
  if [ -f "$DEST/$f" ] && cmp -s "$f" "$DEST/$f"; then
    echo "same      $f"
    continue
  fi
  if [ -f "$DEST/$f" ]; then
    mkdir -p "$BACKUP/$(dirname "$f")"
    mv "$DEST/$f" "$BACKUP/$f"
    echo "replaced  $f  (옛 파일: $BACKUP/$f)"
  else
    echo "new       $f"
  fi
  mkdir -p "$DEST/$(dirname "$f")"
  cp "$f" "$DEST/$f"
done

# settings.json: settings.fragment.json 의 키만 합친다. 다른 키는 그대로 둔다.
python3 - "$DEST/settings.json" "$B/settings.fragment.json" "$BACKUP" <<'EOF'
import json, os, shutil, sys
path, fragment, backup = sys.argv[1:4]
old = json.load(open(path)) if os.path.exists(path) else {}
new = json.loads(json.dumps(old))
for key, val in json.load(open(fragment)).items():
    if key == "permissions":
        perms = new.setdefault(key, {})
        for sub, v in val.items():
            if isinstance(v, list):
                cur = perms.setdefault(sub, [])
                cur += [rule for rule in v if rule not in cur]
            else:
                perms[sub] = v
    elif isinstance(val, dict):
        new.setdefault(key, {}).update(val)
    else:
        new[key] = val
if new == old:
    print("same      settings.json")
else:
    changed = ", ".join(k for k in new if new[k] != old.get(k))
    print(f"set       settings.json: {changed}")
    if os.path.exists(path):
        os.makedirs(backup, exist_ok=True)
        shutil.copy(path, backup)
    with open(path, "w") as f:
        json.dump(new, f, indent=2, ensure_ascii=False)
        f.write("\n")
EOF
