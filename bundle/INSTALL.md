# Claude Code 설정 설치

다른 서버의 Claude Code 설정에서 옮길 수 있는 것을 모두 담은 묶음이다.
보내는 쪽은 이 서버를 보지 못하고 골랐다. 이 서버에 맞는지는 이 문서를 읽는 Claude가 판단하고,
무엇을 넣을지는 사용자가 정한다.

- 사용자가 정하기 전에는 아무것도 설치하지 않는다.
- 항목마다 넣거나 빼기만 한다. 파일 내용을 직접 다시 쓰거나 이 서버에 맞게 고치지 않는다.
  고쳐야 맞는 항목은 빼고, 무엇을 고쳐야 하는지 사용자에게 알린다 (보내는 쪽에서 고쳐 다시 보낸다).
- "뺀 것"의 항목은 만들거나 비슷하게 흉내 내지 않는다.

생성일 2026-10-13 · 보내는 쪽이 가정한 이 서버: 웹 도구 없음, 쓸 수 있는 모델이 다름

## 미리 보기

저장소 루트(이 문서의 위 폴더)에서 실행한다. 아무것도 바꾸지 않는다.

```bash
python3 install.py --dry-run
```

줄 머리의 뜻: `new` 이 서버에 없던 것 · `changed` 이미 있고 내용이 다른 것 · `same` 이미 같은 것 ·
`set` 설정 값이 바뀌는 것. 줄 머리 다음이 항목 이름이다.

## 판단

항목마다 이 서버에서 그대로 써도 되는지 본다.

- `changed` · `set` 항목은 이 서버에 원래 있던 것과 겹친다. 지금 내용과 무엇이 달라지는지 확인한다.
- "들어 있는 것"의 비고에 "필요"가 있는 항목은 그것이 이 서버에 있는지 확인한다 (예: `node --version`).
- 이 서버의 정책이나 구성 때문에 동작하지 않을 항목이 있는지 본다
  (쓸 수 없는 도구, 막힌 네트워크, 관리자가 고정한 설정).

## 사용자에게 묻기

아래 꼴의 표로 보여 주고, 넣을 것과 뺄 것을 확인받는다. `same`인 항목은 한 줄로 묶어도 된다.

| 항목 | 지금 이 서버 | 설치하면 | 의견 |
|---|---|---|---|
| (항목 이름) | (없음 / 지금 값 / 지금 내용 요약) | (들어올 값이나 내용) | 넣기 또는 빼기, 이유 한 줄 |

## 설치

사용자가 정한 대로 실행한다. 뺄 항목의 이름은 미리 보기에 나온 그대로 쓴다.

```bash
python3 install.py                       # 전부 넣을 때
python3 install.py --skip <항목> <항목>   # 뺄 항목이 있을 때
```

`payload/`의 파일을 `~/.claude/`의 같은 자리에 복사하고, `settings.fragment.json`의 키를
`~/.claude/settings.json`에 합친다. 내용이 달라 바뀌는 파일과 바뀌기 전의 settings.json 은
`~/.claude/claude-setup-backup/<시각>/`에 남는다.

## 플러그인

플러그인도 "사용자에게 묻기"의 표에 넣어 묻고, 사용자가 넣기로 했을 때만 아래 명령을 실행한다.
실패하면 고치려 하지 말고 출력을 사용자에게 알린 뒤 넘어간다. 실패해도 "설치"에서 한 일은 그대로 유효하다.

```bash
claude plugin marketplace add alexgreensh/attention-span
claude plugin install attention-span@attention-span
```

## 확인

1. 설치할 때와 같은 `--skip`을 붙여 `python3 install.py --dry-run`을 다시 돌린다.
   넣기로 한 항목이 모두 `same`이어야 한다.
2. 설정은 새 세션부터 적용된다고 사용자에게 알린다.

## 들어 있는 것

| 항목 | 설치 위치 | 비고 |
|---|---|---|
| `CLAUDE.md` | `~/.claude/CLAUDE.md` |  |
| `skills/archify` | `~/.claude/skills/archify` | node >=18 필요 |
| `skills/verification-before-completion` | `~/.claude/skills/verification-before-completion` |  |
| `output-styles/attention-kind.md` | `~/.claude/output-styles/attention-kind.md` | 플러그인 attention-span 에서 꺼냄 |

## 바뀌는 설정

권한 규칙 같은 목록은 기존 목록에 더해지고, 나머지 키는 이 값으로 바뀐다. 여기 없는 키는 건드리지 않는다.

```json
{
  "permissions": {
    "ask": [
      "Bash(sudo *)"
    ]
  },
  "outputStyle": "Attention-kind",
  "alwaysThinkingEnabled": true,
  "autoMemoryEnabled": false,
  "effortLevel": "xhigh"
}
```

## 뺀 것

보내는 쪽에서 옮기지 않기로 한 것이다.

| 항목 | 이유 |
|---|---|
| `skills/*` (3개) | 내부망 IP 주소 / 비밀 정보로 보이는 글 / 이 기기에만 있는 경로 |
| `settings.local.json` | 이 기기 전용 설정 파일 |
| `settings:env` | 받는 쪽에서 쓸 수 있는 모델이 다름 |
| `settings:model` | 받는 쪽에서 쓸 수 있는 모델이 다름 |
| `settings:enabledPlugins` | 설정 키 대신 설치 명령으로 옮긴다 (플러그인) |
| `settings:extraKnownMarketplaces` | 설정 키 대신 설치 명령으로 옮긴다 (플러그인) |
| `settings:modelSettings` | 받는 쪽에서 쓸 수 있는 모델이 다름 |

## 사용자에게 알릴 것

- 넣은 항목과 뺀 항목, 뺀 이유
- 백업 폴더가 생겼다면 그 경로
- 고쳐야 맞는 항목이 있었다면 무엇을 고쳐야 하는지
- 실패한 단계가 있으면 그 출력
