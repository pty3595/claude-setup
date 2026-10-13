#!/usr/bin/env python3
"""Claude Code 설정을 다른 서버로 옮길 묶음(bundle/)을 만든다.

이 서버의 ~/.claude 에서 기본값이 아닌 것을 모두 훑고, 옮기기 어려운 것만 빼고 bundle/ 에 담는다.
받는 쪽 Claude가 읽고 따라 할 bundle/INSTALL.md 도 함께 쓴다.

기본은 옮긴다. 빼는 것은 이유가 분명할 때뿐이다.
  - 비밀 정보 (토큰, 비밀번호)                      공개 저장소에 올릴 수 없다
  - 이 기기를 가리키는 글 (이 기기가 붙은 네트워크의 IP, 여기 실제로 있는 경로)
                                                 받는 쪽에는 그 자리가 없다
  - 받는 쪽에서 쓸 수 없는 모델을 고정한 설정
  - 인증에 묶인 설정, 이 기기 전용 설정 파일, MCP 서버
node 나 웹 도구처럼 받는 쪽에 있어야 도는 것은 빼지 않고 INSTALL.md 에 적어 둔다.

    python3 export.py                         # 받는 쪽이 제한된 서버라고 본다
    python3 export.py --target-allows web     # 받는 쪽에서 되는 것을 알려 준다
    python3 export.py --include skills/foo --exclude settings:autoMemoryEnabled

화면에 나온 "옮긴다 / 뺀다"를 확인한 뒤 저장소를 커밋 · push 한다.
받는 쪽에서는 저장소를 받고 Claude에게 "bundle/INSTALL.md 대로 설치해 줘"라고 한다.
"""
import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
GLOBAL_CONFIG = SRC / ".claude.json" if os.environ.get("CLAUDE_CONFIG_DIR") else Path.home() / ".claude.json"

# ~/.claude 에서 옮길 후보. 여기 없는 것(세션 기록, 캐시, 인증 파일)은 보지 않는다.
TOP_FILES = ["CLAUDE.md", "keybindings.json"]
TOP_DIRS = ["skills", "agents", "commands", "output-styles", "rules", "hooks"]
SKIP = {"synced"}  # claude.ai 계정에서 내려오는 스킬. 받는 쪽 계정이 알아서 받는다

# 이유 문구는 INSTALL.md 에 그대로 실린다. 걸린 글 자체는 어디에도 쓰지 않는다.
SECRET = "비밀 정보로 보이는 글"
MACHINE_PATH = "이 기기에만 있는 경로"
MODEL_WHY = "받는 쪽에서 쓸 수 있는 모델이 다름"
WEB_NOTE = "웹 도구(WebFetch · WebSearch)를 언급한다"

TOKEN = re.compile(r"ghp_\w{20,}|github_pat_\w+|sk-ant-[\w-]+|BEGIN [A-Z ]*PRIVATE KEY")
# 코드에서는 token = ... 같은 변수가 흔해서, 느슨한 검사는 글과 설정 파일에만 건다
LOOSE_SECRET = re.compile(r"(?i:password|passwd|secret|token)\s*[:=]\s*\S|비밀번호|자격 증명")
PROSE = {".md", ".txt", ".env", ".yaml", ".yml", ".ini", ".toml", ".cfg", ".conf", ""}
IP = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
HOME_PATH = re.compile(r"/home/[\w.-]+|/Users/[\w.-]+|~/([\w-][\w.-]*)")
WEB = re.compile(r"\b(?:WebFetch|WebSearch)\b")
RULE_PATH = re.compile(r"(?<!:)//|~/|/home/|/Users/")

MODEL_KEYS = {"model", "fallbackModel", "modelSettings", "advisorModel", "availableModels", "modelOverrides"}
PLUGIN_KEYS = {"enabledPlugins", "extraKnownMarketplaces", "pluginConfigs"}
LOCAL_KEYS = {"apiKeyHelper", "awsAuthRefresh", "awsCredentialExport", "gcpAuthRefresh",
              "otelHeadersHelper", "proxyAuthHelper", "forceLoginMethod", "forceLoginOrgUUID",
              "sshConfigs", "remote", "autoMemoryDirectory", "plansDirectory"}


def load(path):
    return json.loads(path.read_text()) if path.exists() else {}


PRIVATE = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]


def local_networks():
    """이 기기가 붙어 있는 네트워크. ip 명령이 없으면 사설 대역 전체로 넓게 본다."""
    if not shutil.which("ip"):
        return PRIVATE
    out = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True, text=True).stdout
    nets = [ipaddress.ip_interface(a).network for a in re.findall(r"inet (\S+)", out)]
    return [n for n in nets if not n.is_loopback]


NETWORKS = local_networks()


def local_ip(text, prose):
    """이 기기 주변을 가리키는 주소인가. 그림 좌표나 문서용 예시 주소는 걸리지 않는다.
    사람이 쓴 글에서는 다른 내부망 주소일 수 있어 사설 대역까지 본다."""
    try:
        return any(ipaddress.ip_address(text) in n for n in NETWORKS + (PRIVATE if prose else []))
    except ValueError:
        return False


def here_path(match, prose):
    """글에 나온 경로가 이 기기를 가리키는가. 코드에서는 여기 실제로 있는 경로만 본다
    (테스트용 /home/user 같은 것은 걸리지 않는다). 사람이 쓴 글의 /home/... 은 그대로 건다."""
    under_home = match.group(1)
    if under_home:
        return (Path.home() / under_home).exists()
    return prose or Path(match.group()).exists()


def line_reasons(line, prose):
    if TOKEN.search(line) or (prose and LOOSE_SECRET.search(line)):
        yield SECRET
    if any(local_ip(m.group(), prose) for m in IP.finditer(line)):
        yield "내부망 IP 주소"
    if any(here_path(m, prose) for m in HOME_PATH.finditer(line)):
        yield MACHINE_PATH


def runtime_needs(path):
    """받는 쪽에 있어야 도는 것. 빼는 이유는 아니고 INSTALL.md 에 적는다."""
    needs = []
    if (path / "package.json").exists():
        pkg = load(path / "package.json")
        node = (pkg.get("engines") or {}).get("node")
        needs.append(f"node {node} 필요" if node else "node 필요")
        if pkg.get("dependencies"):
            needs.append("`npm install` 필요")
    needs += [f"추가 설치 필요 ({n})" for n in ("requirements.txt", "pyproject.toml", "Cargo.toml", "go.mod")
              if (path / n).exists()]
    return needs


def scan(path, allows):
    """파일이나 폴더를 읽어 (빼는 이유 {이유: [위치]}, 받는 쪽에 필요한 것 [문구]) 를 낸다."""
    why, needs = {}, []
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    for f in files:
        rel = f.name if path.is_file() else str(f.relative_to(path))
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        prose = f.suffix.lower() in PROSE
        for n, line in enumerate(text.splitlines(), 1):
            for reason in line_reasons(line, prose):
                why.setdefault(reason, []).append(f"{rel}:{n}")
        if prose and "web" not in allows and WEB.search(text) and WEB_NOTE not in needs:
            needs.append(WEB_NOTE)
    if path.is_dir():
        needs += runtime_needs(path)
    return why, needs


def file_item(item_id, path, allows, note=""):
    why, needs = scan(path, allows)
    return {"id": item_id, "src": path, "why": why, "note": " · ".join(filter(None, [note, *needs]))}


def env_reason(name, value, allows):
    if "MODEL" in name:
        return "" if "models" in allows else MODEL_WHY
    if re.search(r"KEY|TOKEN|SECRET|PASSWORD|AUTH", name):
        return SECRET
    if re.search(r"URL|PROXY|PATH|DIR|HOME", name):
        return "이 기기에 묶인 환경 변수"
    return next(line_reasons(value, True), "")


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
            add(key, (key,), val, "설정 키 대신 설치 명령으로 옮긴다 (플러그인)")
        elif key in LOCAL_KEYS:
            add(key, (key,), val, "인증이나 이 기기의 경로에 묶인 설정")
        else:
            add(key, (key,), val, next(line_reasons(json.dumps(val, ensure_ascii=False), True), ""))
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


def plugin_steps(settings):
    """켜져 있는 플러그인을 받는 쪽에서 설치할 명령."""
    markets = settings.get("extraKnownMarketplaces", {})
    steps = []
    for pid, on in settings.get("enabledPlugins", {}).items():
        if not on:
            continue
        source = markets.get(pid.partition("@")[2], {}).get("source", {})
        repo = source.get("repo") or source.get("url")
        if repo and f"claude plugin marketplace add {repo}" not in steps:
            steps.append(f"claude plugin marketplace add {repo}")
        steps.append(f"claude plugin install {pid}")
    return steps


def collect(settings, allows):
    items = [file_item(n, SRC / n, allows) for n in TOP_FILES if (SRC / n).exists()]
    for d in TOP_DIRS:
        for p in sorted((SRC / d).glob("*")):
            if not p.name.startswith(".") and p.name not in SKIP:
                items.append(file_item(f"{d}/{p.name}", p, allows))
    if (SRC / "settings.local.json").exists():
        items.append({"id": "settings.local.json", "why": {"이 기기 전용 설정 파일": []}, "note": ""})

    for it in setting_items(settings, allows):
        path, value, _ = it["set"]
        if path == ("outputStyle",) and ":" in str(value):
            # 플러그인 설치가 안 되는 곳에서도 지금 쓰는 스타일은 돌도록 파일로 꺼내 둔다
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


def install_md(included, excluded, fragment, plugins, allows):
    files = [it for it in included if "src" in it]
    gone = {}
    for it in excluded:
        gone.setdefault(public_id(it["id"]), []).append(it)
    assumed = [w for k, w in (("web", "웹 도구 없음"), ("models", "쓸 수 있는 모델이 다름")) if k not in allows]
    plugin_part = [
        "## 플러그인",
        "",
        "플러그인도 \"사용자에게 묻기\"의 표에 넣어 묻고, 사용자가 넣기로 했을 때만 아래 명령을 실행한다.",
        "실패하면 고치려 하지 말고 출력을 사용자에게 알린 뒤 넘어간다. 실패해도 \"설치\"에서 한 일은 그대로 유효하다.",
        "",
        "```bash",
        *plugins,
        "```",
        "",
    ] if plugins else []
    return "\n".join([
        "# Claude Code 설정 설치",
        "",
        "다른 서버의 Claude Code 설정에서 옮길 수 있는 것을 모두 담은 묶음이다.",
        "보내는 쪽은 이 서버를 보지 못하고 골랐다. 이 서버에 맞는지는 이 문서를 읽는 Claude가 판단하고,",
        "무엇을 넣을지는 사용자가 정한다.",
        "",
        "- 사용자가 정하기 전에는 아무것도 설치하지 않는다.",
        "- 항목마다 넣거나 빼기만 한다. 파일 내용을 직접 다시 쓰거나 이 서버에 맞게 고치지 않는다.",
        "  고쳐야 맞는 항목은 빼고, 무엇을 고쳐야 하는지 사용자에게 알린다 (보내는 쪽에서 고쳐 다시 보낸다).",
        "- \"뺀 것\"의 항목은 만들거나 비슷하게 흉내 내지 않는다.",
        "",
        f"생성일 {date.today()} · 보내는 쪽이 가정한 이 서버: {', '.join(assumed) or '제한 없음'}",
        "",
        "## 미리 보기",
        "",
        "저장소 루트(이 문서의 위 폴더)에서 실행한다. 아무것도 바꾸지 않는다.",
        "",
        "```bash",
        "python3 install.py --dry-run",
        "```",
        "",
        "줄 머리의 뜻: `new` 이 서버에 없던 것 · `changed` 이미 있고 내용이 다른 것 · `same` 이미 같은 것 ·",
        "`set` 설정 값이 바뀌는 것. 줄 머리 다음이 항목 이름이다.",
        "",
        "## 판단",
        "",
        "항목마다 이 서버에서 그대로 써도 되는지 본다.",
        "",
        "- `changed` · `set` 항목은 이 서버에 원래 있던 것과 겹친다. 지금 내용과 무엇이 달라지는지 확인한다.",
        "- \"들어 있는 것\"의 비고에 \"필요\"가 있는 항목은 그것이 이 서버에 있는지 확인한다 (예: `node --version`).",
        "- 이 서버의 정책이나 구성 때문에 동작하지 않을 항목이 있는지 본다",
        "  (쓸 수 없는 도구, 막힌 네트워크, 관리자가 고정한 설정).",
        "",
        "## 사용자에게 묻기",
        "",
        "아래 꼴의 표로 보여 주고, 넣을 것과 뺄 것을 확인받는다. `same`인 항목은 한 줄로 묶어도 된다.",
        "",
        "| 항목 | 지금 이 서버 | 설치하면 | 의견 |",
        "|---|---|---|---|",
        "| (항목 이름) | (없음 / 지금 값 / 지금 내용 요약) | (들어올 값이나 내용) | 넣기 또는 빼기, 이유 한 줄 |",
        "",
        "## 설치",
        "",
        "사용자가 정한 대로 실행한다. 뺄 항목의 이름은 미리 보기에 나온 그대로 쓴다.",
        "",
        "```bash",
        "python3 install.py                       # 전부 넣을 때",
        "python3 install.py --skip <항목> <항목>   # 뺄 항목이 있을 때",
        "```",
        "",
        "`payload/`의 파일을 `~/.claude/`의 같은 자리에 복사하고, `settings.fragment.json`의 키를",
        "`~/.claude/settings.json`에 합친다. 내용이 달라 바뀌는 파일과 바뀌기 전의 settings.json 은",
        "`~/.claude/claude-setup-backup/<시각>/`에 남는다.",
        "",
        *plugin_part,
        "## 확인",
        "",
        "1. 설치할 때와 같은 `--skip`을 붙여 `python3 install.py --dry-run`을 다시 돌린다.",
        "   넣기로 한 항목이 모두 `same`이어야 한다.",
        "2. 설정은 새 세션부터 적용된다고 사용자에게 알린다.",
        "",
        "## 들어 있는 것",
        "",
        "| 항목 | 설치 위치 | 비고 |",
        "|---|---|---|",
        *[f"| `{it['id']}` | `~/.claude/{it['id']}` | {it['note']} |" for it in files],
        "",
        "## 바뀌는 설정",
        "",
        "권한 규칙 같은 목록은 기존 목록에 더해지고, 나머지 키는 이 값으로 바뀐다. 여기 없는 키는 건드리지 않는다.",
        "",
        "```json",
        json.dumps(fragment, indent=2, ensure_ascii=False),
        "```",
        "",
        "## 뺀 것",
        "",
        "보내는 쪽에서 옮기지 않기로 한 것이다.",
        "",
        "| 항목 | 이유 |",
        "|---|---|",
        *[f"| `{i}`{f' ({len(its)}개)' if len(its) > 1 else ''} "
          f"| {' / '.join(sorted({w for it in its for w in it['why']}))} |" for i, its in gone.items()],
        "",
        "## 사용자에게 알릴 것",
        "",
        "- 넣은 항목과 뺀 항목, 뺀 이유",
        "- 백업 폴더가 생겼다면 그 경로",
        "- 고쳐야 맞는 항목이 있었다면 무엇을 고쳐야 하는지",
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

    settings = load(SRC / "settings.json")
    items = collect(settings, allows)
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
    plugins = plugin_steps(settings)
    (out / "settings.fragment.json").write_text(json.dumps(fragment, indent=2, ensure_ascii=False) + "\n")
    (out / "INSTALL.md").write_text(install_md(included, excluded, fragment, plugins, allows))
    listed = sorted(p for p in out.rglob("*") if p.is_file())
    (out / "MANIFEST.sha256").write_text("".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n" for p in listed))

    print(f"옮긴다 ({len(included)})")
    for it in included:
        value = f" = {json.dumps(it['set'][1], ensure_ascii=False)}" if "set" in it and not it["set"][2] else ""
        print(f"  {it['id']}{value}" + (f"   ← {it['note']}" if it["note"] else ""))
    for step in plugins:
        print(f"  (설치 명령) {step}")
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
