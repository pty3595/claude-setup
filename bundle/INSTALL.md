# Claude Code 설정 설치

다른 서버의 Claude Code 설정에서 옮길 수 있는 것을 모두 담은 묶음이다.
이 문서를 읽은 Claude는 아래를 그대로 따른다.

- 파일 내용을 직접 다시 쓰지 않는다. 복사는 `install.sh`가 한다.
- 명령이 실패하면 고쳐서 넘어가지 말고, 출력을 그대로 사용자에게 알리고 멈춘다.
- "뺀 것"의 항목은 만들거나 비슷하게 흉내 내지 않는다.

생성일 2026-10-13 · 받는 쪽 가정: 웹 도구 없음, 쓸 수 있는 모델이 다름

## 설치

저장소 루트(이 문서의 위 폴더)에서 실행한다.

```bash
bash install.sh
```

`install.sh`는 묶음이 온전한지 `MANIFEST.sha256`으로 확인한 뒤, `payload/`의 파일을
`~/.claude/`의 같은 자리에 복사하고 `settings.fragment.json`의 키를 `~/.claude/settings.json`에 합친다.
내용이 다른 파일이 이미 있으면 `~/.claude/claude-setup-backup/<시각>/`으로 옮긴 뒤 복사한다.

## 들어 있는 것

| 항목 | 설치 위치 | 비고 |
|---|---|---|
| `CLAUDE.md` | `~/.claude/CLAUDE.md` |  |
| `skills/archify` | `~/.claude/skills/archify` | node >=18 필요 |
| `skills/verification-before-completion` | `~/.claude/skills/verification-before-completion` |  |
| `output-styles/attention-kind.md` | `~/.claude/output-styles/attention-kind.md` | 플러그인 attention-span 에서 꺼냄 |

## 바뀌는 설정

권한 규칙 목록은 기존 목록에 더해지고, 나머지 키는 이 값으로 바뀐다. 여기 없는 키는 건드리지 않는다.

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

## 플러그인

아래 명령으로 설치를 시도한다. 실패하면 고치려 하지 말고 출력을 사용자에게 알린 뒤 넘어간다.
실패해도 위의 설치는 그대로 유효하다.

```bash
claude plugin marketplace add alexgreensh/attention-span
claude plugin install attention-span@attention-span
```

## 확인

1. `install.sh` 출력에 오류가 없는지 본다. 줄 머리는 `new` · `replaced` · `same` · `set` 중 하나다.
2. `bash install.sh`를 한 번 더 돌려 모든 줄이 `same`인지 본다.
3. "들어 있는 것"의 비고에 "필요"가 있으면 받는 쪽에 그것이 있는지 본다 (예: `node --version`).
   없으면 설치하려 하지 말고, 그 항목이 동작하지 않는다고 사용자에게 알린다.
4. 설정은 새 세션부터 적용된다고 사용자에게 알린다.

## 뺀 것

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

- `install.sh` 출력 전체
- 백업 폴더가 생겼다면 그 경로
- 받는 쪽에 없어서 동작하지 않는 항목
- 실패한 단계가 있으면 그 출력
