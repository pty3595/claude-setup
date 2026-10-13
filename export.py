#!/usr/bin/env python3
"""Claude Code 설정을 다른 서버로 옮길 묶음(bundle/)을 만든다.

이 서버의 ~/.claude 를 훑어 옮길 수 있는 것만 골라 bundle/ 에 담고,
받는 쪽 Claude가 읽고 따라 할 bundle/INSTALL.md 를 함께 쓴다.

    python3 export.py                         # 받는 쪽이 제한된 서버라고 본다
    python3 export.py --target-allows web     # 받는 쪽에서 되는 것을 알려 준다
    python3 export.py --include skills/foo --exclude settings:autoMemoryEnabled

화면에 나온 "옮긴다 / 뺀다"를 확인한 뒤 저장소를 커밋 · push 한다.
받는 쪽에서는 저장소를 받고 Claude에게 "bundle/INSTALL.md 대로 설치해 줘"라고 한다.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
GLOBAL_CONFIG = SRC / ".claude.json" if os.environ.get("CLAUDE_CONFIG_DIR") else Path.home() / ".claude.json"

# ~/.claude 에서 옮길 후보. 여기 없는 것(세션 기록, 캐시, 인증 파일)은 보지 않는다.
TOP_FILES = ["CLAUDE.md", "keybindings.json"]
TOP_DIRS = ["skills", "agents", "commands", "output-styles", "rules"]
SKIP = {"synced"}  # claude.ai 계정에서 내려오는 스킬. 받는 쪽 계정이 알아서 받는다

# 이유 문구는 INSTALL.md 에 그대로 실린다. 걸린 글 자체는 어디에도 쓰지 않는다.
SECRET = "비밀 정보로 보이는 글"
MACHINE_PATH = "이 기기에만 있는 경로"
MODEL_WHY = "받는 쪽에서 쓸 수 있는 모델이 다름"
MARKERS = [
    (re.compile(r"(?:/home|/Users)/[\w.-]+|~/(?!\.claude\b)[\w.-]+"), MACHINE_PATH),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "IP 주소"),
    (re.compile(r"ghp_\w{20,}|github_pat_\w+|sk-ant-[\w-]+|BEGIN [A-Z ]*PRIVATE KEY"
                r"|(?i:password|passwd|secret|token)\s*[:=]\s*\S|비밀번호|자격 증명"), SECRET),
]
WEB = (re.compile(r"\b(?:WebFetch|WebSearch)\b"), "웹 도구(WebFetch · WebSearch)를 쓴다")
RUNTIME = {"package.json", "requirements.txt", "pyproject.toml", "Cargo.toml", "go.mod"}
RULE_PATH = re.compile(r"(?<!:)//|~/|/home/|/Users/")

MODEL_KEYS = {"model", "fallbackModel", "modelSettings", "effortLevel", "maxEffortLevel",
              "advisorModel", "fastMode", "availableModels", "modelOverrides"}
PLUGIN_KEYS = {"enabledPlugins", "extraKnownMarketplaces", "pluginConfigs"}
MACHINE_KEYS = {"hooks", "statusLine", "subagentStatusLine", "fileSuggestion", "apiKeyHelper",
                "awsAuthRefresh", "awsCredentialExport", "gcpAuthRefresh", "otelHeadersHelper",
                "proxyAuthHelper", "autoMemoryDirectory", "plansDirectory", "sshConfigs",
                "remote", "sandbox", "worktree", "forceLoginMethod", "forceLoginOrgUUID"}


def load(path):
    return json.loads(path.read_text()) if path.exists() else {}


def scan(path, allows):
    """파일이나 폴더에서 옮기기 어려운 표시를 찾는다. {이유: [위치, ...]}"""
    hits = {}
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    markers = MARKERS + ([] if "web" in allows else [WEB])
    for f in files:
        rel = f.name if path.is_file() else str(f.relative_to(path))
        if f.name in RUNTIME:
            hits.setdefault("추가 설치가 필요하다", []).append(rel)
        if f.stat().st_size > 1_000_000:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for rx, why in markers:
                if rx.search(line):
                    hits.setdefault(why, []).append(f"{rel}:{n}")
    return hits


def file_item(item_id, path, allows, note=""):
    return {"id": item_id, "src": path, "why": scan(path, allows), "note": note}


def env_reason(name, value, allows):
    if "MODEL" in name:
        return "" if "models" in allows else MODEL_WHY
    if re.search(r"KEY|TOKEN|SECRET|PASSWORD|AUTH", name):
        return SECRET
    if re.search(r"URL|PROXY|PATH|DIR|HOME", name) or any(rx.search(value) for rx, _ in MARKERS):
        return "이 기기에 묶인 환경 변수"
    return ""


def setting_items(settings, allows):
    """settings.json 을 옮길지 따로 정할 수 있는 낱개로 쪼갠다."""
    items = []

    def add(item_id, path, value, why="", is_list=False):
        items.append({"id": f"settings:{item_id}", "set": (path, value, is_list),
                      "why": {why: []} if why else {}, "note": ""})

    for key, val in settings.items():
        if key == "permissions":
            for sub, v in val.items():
                if sub == "additionalDirectories":
                    add(f"permissions.{sub}", (key, sub), v, MACHINE_PATH)
                elif isinstance(v, list):
                    for rule in v:
                        add(f"permissions.{sub}:{rule}", (key, sub), rule,
                            MACHINE_PATH if RULE_PATH.search(rule) else "", True)
                else:
                    add(f"permissions.{sub}", (key, sub), v)
        elif key == "env":
            for name, v in val.items():
                add(f"env.{name}", (key, name), v, env_reason(name, str(v), allows))
        elif key in MODEL_KEYS:
            add(key, (key,), val, "" if "models" in allows else MODEL_WHY)
        elif key in PLUGIN_KEYS:
            add(key, (key,), val, "플러그인은 받는 쪽에서 직접 설치한다")
        elif key in MACHINE_KEYS:
            add(key, (key,), val, "명령 · 경로 · 인증이 이 기기에 묶인 설정")
        elif isinstance(val, (dict, list)):
            add(key, (key,), val, "모르는 구조의 설정 (확인 후 --include)")
        else:
            add(key, (key,), val)
    return items


def plugin_style(value):
    """outputStyle 이 '플러그인:이름' 꼴이면 그 스타일 파일과 라이선스를 찾는다."""
    plugin, _, name = value.partition(":")
    for pid, entries in load(SRC / "plugins/installed_plugins.json").get("plugins", {}).items():
        if pid.split("@")[0] != plugin:
            continue
        root = Path(entries[0]["installPath"])
        for f in sorted(root.glob("output-styles/*.md")):
            if re.search(rf"^name:\s*{re.escape(name)}\s*$", f.read_text(), re.M):
                return f, next(iter(sorted(root.glob("LICENSE*"))), None), name
    return None


def collect(allows):
    items = [file_item(n, SRC / n, allows) for n in TOP_FILES if (SRC / n).exists()]
    for d in TOP_DIRS:
        for p in sorted((SRC / d).glob("*")):
            if not p.name.startswith(".") and p.name not in SKIP:
                items.append(file_item(f"{d}/{p.name}", p, allows))
    if (SRC / "settings.local.json").exists():
        items.append({"id": "settings.local.json", "why": {"이 기기 전용 설정 파일": []}, "note": ""})

    for it in setting_items(load(SRC / "settings.json"), allows):
        path, value, _ = it["set"]
        if path == ("outputStyle",) and ":" in str(value):
            # 플러그인은 옮기지 않으므로, 설정이 가리키는 스타일만 파일로 꺼낸다
            found = plugin_style(value)
            if found:
                f, lic, name = found
                plugin = value.split(":")[0]
                style = file_item(f"output-styles/{f.name}", f, allows, f"플러그인 {plugin} 에서 꺼냄")
                style["license"] = (lic, f"{plugin}-{lic.name}") if lic else None
                items.append(style)
                it["set"], it["needs"] = (path, name, False), style["id"]
            else:
                it["why"] = {"플러그인 스타일 파일을 찾지 못함": []}
        items.append(it)

    for name in load(GLOBAL_CONFIG).get("mcpServers", {}):
        items.append({"id": f"mcp:{name}", "note": "",
                      "why": {"MCP 서버는 명령 · 주소 · 인증이 이 기기에 묶여 있다": []}})
    return items


def public_id(item_id):
    """INSTALL.md 는 공개될 수 있어 뺀 항목은 종류만 싣는다. 이름과 규칙 본문은 화면에만 나온다."""
    kind, _, rest = item_id.partition(":")
    if kind == "settings" and rest:
        key = rest.split(":")[0]
        return "settings:" + ("env" if key.startswith("env.") else key)
    if kind == "mcp" and rest:
        return "mcp 서버"
    return item_id.split("/")[0] + "/*" if "/" in item_id else item_id


def install_md(included, excluded, fragment, allows):
    files = [it for it in included if "src" in it]
    gone = {}
    for it in excluded:
        gone.setdefault(public_id(it["id"]), []).append(it)
    assumed = [w for k, w in (("web", "웹 도구 없음"), ("models", "쓸 수 있는 모델이 다름")) if k not in allows]
    return "\n".join([
        "# Claude Code 설정 설치",
        "",
        "다른 서버의 Claude Code 설정에서 옮길 수 있는 것만 골라 담은 묶음이다.",
        "이 문서를 읽은 Claude는 아래를 그대로 따른다.",
        "",
        "- 파일 내용을 직접 다시 쓰지 않는다. 복사는 `install.sh`가 한다.",
        "- 명령이 실패하면 고쳐서 넘어가지 말고, 출력을 그대로 사용자에게 알리고 멈춘다.",
        "- \"뺀 것\"의 항목은 만들거나 비슷하게 흉내 내지 않는다.",
        "",
        f"생성일 {date.today()} · 받는 쪽 가정: {', '.join(assumed) or '제한 없음'}",
        "",
        "## 설치",
        "",
        "저장소 루트(이 문서의 위 폴더)에서 실행한다.",
        "",
        "```bash",
        "bash install.sh",
        "```",
        "",
        "`install.sh`는 묶음이 온전한지 `MANIFEST.sha256`으로 확인한 뒤, `payload/`의 파일을",
        "`~/.claude/`의 같은 자리에 복사하고 `settings.fragment.json`의 키를 `~/.claude/settings.json`에 합친다.",
        "내용이 다른 파일이 이미 있으면 `~/.claude/claude-setup-backup/<시각>/`으로 옮긴 뒤 복사한다.",
        "",
        "## 들어 있는 것",
        "",
        "| 항목 | 설치 위치 | 비고 |",
        "|---|---|---|",
        *[f"| `{it['id']}` | `~/.claude/{it['id']}` | {it['note']} |" for it in files],
        "",
        "## 바뀌는 설정",
        "",
        "권한 규칙 목록은 기존 목록에 더해지고, 나머지 키는 이 값으로 바뀐다. 여기 없는 키는 건드리지 않는다.",
        "",
        "```json",
        json.dumps(fragment, indent=2, ensure_ascii=False),
        "```",
        "",
        "## 확인",
        "",
        "1. `install.sh` 출력에 오류가 없는지 본다. 줄 머리는 `new` · `replaced` · `same` · `set` 중 하나다.",
        "2. `bash install.sh`를 한 번 더 돌려 모든 줄이 `same`인지 본다.",
        "3. 설정은 새 세션부터 적용된다고 사용자에게 알린다.",
        "",
        "## 뺀 것",
        "",
        "| 항목 | 이유 |",
        "|---|---|",
        *[f"| `{i}`{f' ({len(its)}개)' if len(its) > 1 else ''} "
          f"| {' / '.join(sorted({w for it in its for w in it['why']}))} |" for i, its in gone.items()],
        "",
        "## 사용자에게 알릴 것",
        "",
        "- `install.sh` 출력 전체",
        "- 백업 폴더가 생겼다면 그 경로",
        "- 실패한 단계가 있으면 그 출력",
        "",
    ])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target-allows", nargs="*", default=[], choices=["web", "models"],
                    help="받는 쪽 서버에서 되는 것. 안 주면 둘 다 안 된다고 본다")
    ap.add_argument("--include", nargs="*", default=[], metavar="ID", help="규칙이 뺀 항목을 넣는다")
    ap.add_argument("--exclude", nargs="*", default=[], metavar="ID", help="규칙이 넣은 항목을 뺀다")
    args = ap.parse_args()
    allows = set(args.target_allows)

    items = collect(allows)
    unknown = [i for i in args.include + args.exclude if i not in {it["id"] for it in items}]
    if unknown:
        ap.error("모르는 항목: " + ", ".join(unknown))
    for it in items:
        if it["id"] in args.exclude:
            it["why"] = {"--exclude 로 지정": []}
        elif it["id"] in args.include and SECRET not in it["why"] and ("src" in it or "set" in it):
            it["why"] = {}
    out_ids = {it["id"] for it in items if it["why"]}
    for it in items:
        if it.get("needs") in out_ids and not it["why"]:
            it["why"] = {"가리키는 스타일 파일을 옮기지 않는다": []}
    included = [it for it in items if not it["why"]]
    excluded = [it for it in items if it["why"]]

    out = HERE / "bundle"
    shutil.rmtree(out, ignore_errors=True)
    (out / "payload").mkdir(parents=True)
    fragment = {}
    for it in included:
        if "src" in it:
            dest = out / "payload" / it["id"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            (shutil.copytree if it["src"].is_dir() else shutil.copy2)(it["src"], dest)
            if it.get("license"):
                (out / "licenses").mkdir(exist_ok=True)
                shutil.copy2(it["license"][0], out / "licenses" / it["license"][1])
        else:
            path, value, is_list = it["set"]
            d = fragment
            for k in path[:-1]:
                d = d.setdefault(k, {})
            if is_list:
                d.setdefault(path[-1], []).append(value)
            else:
                d[path[-1]] = value
    (out / "settings.fragment.json").write_text(json.dumps(fragment, indent=2, ensure_ascii=False) + "\n")
    (out / "INSTALL.md").write_text(install_md(included, excluded, fragment, allows))
    listed = sorted(p for p in out.rglob("*") if p.is_file())
    (out / "MANIFEST.sha256").write_text("".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n" for p in listed))

    print(f"옮긴다 ({len(included)})")
    for it in included:
        value = f" = {json.dumps(it['set'][1], ensure_ascii=False)}" if "set" in it and not it["set"][2] else ""
        print(f"  {it['id']}{value}" + (f"   ← {it['note']}" if it["note"] else ""))
    print(f"\n뺀다 ({len(excluded)})")
    for it in excluded:
        whys = [w + (f" ({loc[0]}" + (f" 외 {len(loc) - 1}곳)" if len(loc) > 1 else ")") if loc else "")
                for w, loc in it["why"].items()]
        print(f"  {it['id']} — {' / '.join(whys)}")

    # 옮기는 글이 뺀 스킬을 이름으로 부르면 받는 쪽에서 헛돈다
    gone = [it["id"].split("/", 1)[1] for it in excluded if it["id"].startswith("skills/")]
    for f in sorted(p for p in (out / "payload").rglob("*") if p.is_file()):
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name in gone:
            if name in text:
                print(f"\n주의: {f.relative_to(out / 'payload')} 가 뺀 스킬 `{name}` 을 부른다")
    print(f"\n{out} 에 썼다. 확인한 뒤 커밋 · push 한다.")


if __name__ == "__main__":
    main()
