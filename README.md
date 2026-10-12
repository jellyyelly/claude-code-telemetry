# claude-code-telemetry

Claude Code 의 토큰 사용량과 비용을 **내 PC 에서만** 수집해 Grafana 대시보드로 보는 구성이다.
Claude Code 가 내보내는 OpenTelemetry 이벤트를 로컬 Loki 가 받아 저장하고, Grafana 가 세션·턴·스킬·MCP·서브에이전트·도구 단위로 집계한다.
데이터는 PC 밖으로 나가지 않는다(Loki·Grafana 모두 `127.0.0.1` 에만 열린다).

## 준비물

- Docker (Docker Desktop 또는 OrbStack) — 실행 중이어야 한다
- `jq`, `curl` — macOS: `brew install jq` / Ubuntu: `sudo apt install jq`
- Claude Code

## 설치

```bash
git clone <이 저장소> ~/claude-code-telemetry
cd ~/claude-code-telemetry
./install.sh
```

설치 스크립트가 하는 일:

1. Loki 와 Grafana 컨테이너를 띄운다.
2. `~/.claude/settings.json` 의 `env` 에 텔레메트리 변수 5개를 넣는다.
3. `~/.claude/settings.json` 의 `Stop` 훅에 `session-name-hook.sh` 를 등록한다.

`settings.json` 은 고치기 전에 `settings.json.bak-telemetry-<시각>` 으로 백업한다. 여러 번 실행해도 된다.

설치 후 **새로 시작하는** Claude Code 세션부터 기록된다. 대시보드는 <http://localhost:23000> 이다(로그인 없음).

### 포트 바꾸기

기본 포트는 Grafana 23000, Loki 23100 이다. 설치할 때 바꿀 수 있다.

```bash
./install.sh --grafana-port 24000 --loki-port 24100
```

지정한 포트는 `.env` 에 저장되어 다음 실행, 제거, 훅에서 그대로 쓰인다. 이미 설치한 뒤에 바꿀 때도 같은 명령을 다시 실행하면 된다
(수집 데이터는 유지된다. 실행 중이던 Claude Code 세션은 다시 시작해야 새 포트로 보낸다).

### 저장소 위치를 옮겼을 때

훅이 절대 경로로 등록되므로 옮긴 뒤 `./install.sh --settings-only` 를 실행한다.

## 제거

```bash
./uninstall.sh           # 설정을 빼고 컨테이너를 내린다. 수집 데이터는 남긴다
./uninstall.sh --purge   # 수집 데이터(Docker 볼륨)까지 지운다
```

## 무엇이 기록되는가

| 기록됨 | 기록 안 됨 |
|---|---|
| API 요청별 모델, 토큰 4종(입력·출력·캐시 읽기·캐시 쓰기), 비용 | 프롬프트와 응답 본문 |
| 세션 ID, 턴 ID(`prompt.id`), 세션 이름, 작업 디렉터리 | 파일 내용, 도구 결과 본문 |
| 도구 이름과 **입력 원문**(Bash 명령, SQL 등), 입출력 크기 | |
| 계정 이메일·계정 ID | |

도구 입력 원문은 `OTEL_LOG_TOOL_DETAILS=1` 때문에 남는다. 스킬·MCP 별 집계에 필요해서 켜 두었다.
보존 기간 제한이 없어 지우기 전까지 계속 쌓인다.

## 대시보드 읽는 법

- **세션별 사용량**: `session_id` 를 누르면 아래 표들이 그 세션으로 좁혀진다. 위쪽 "세션 ID" 칸에 ID 앞부분만 넣어도 된다. 비우면 전체.
- **초기 컨텍스트**: 세션 첫 요청의 프롬프트 크기. 시스템 프롬프트·도구 정의·메모리 파일·스킬 목록의 합에 가깝다.
- **턴 번호**: 선택한 시간 범위 안에서 그 세션의 몇 번째 턴인지. 범위가 세션 시작보다 늦으면 1번부터 다시 매겨진다.
- **스킬·MCP 귀속 사용량**: 서로 겹칠 수 있으니 더하지 않는다.
- **주간 대비 증감**: 시간 범위의 끝 시각 기준으로 최근 7일과 직전 7일을 비교한다. 세션 필터와 무관하다.
- **세션 이름**: `/rename` 으로 붙인 제목이 있으면 그것, 없으면 자동 생성 제목. 첫 턴이 끝나야 채워진다.

## 대시보드 고치기

Grafana 화면에서 고친 내용은 `grafana/dashboards/claude-code-tokens.json` 이 다시 생성될 때 덮어써진다.
유지할 변경은 `generate-dashboard.py` 를 고치고 다시 생성한 뒤 커밋한다.

```bash
python3 generate-dashboard.py   # JSON 재생성. Grafana 가 10초 안에 읽어 들인다
```

## 구성 파일

| 파일 | 역할 |
|---|---|
| `docker-compose.yml`, `loki-config.yaml` | Loki·Grafana 컨테이너 |
| `grafana/provisioning/` | 데이터소스와 대시보드 자동 등록 |
| `grafana/dashboards/claude-code-tokens.json` | 대시보드 (생성물) |
| `generate-dashboard.py` | 대시보드 생성기 |
| `session-name-hook.sh` | Stop 훅. 세션 이름·프로젝트를 Loki 에 기록 |
| `install.sh`, `uninstall.sh`, `lib.sh` | 설치·제거 |

## 알려진 한계

- 컨테이너가 꺼져 있는 동안의 이벤트는 유실된다.
- 메모리 파일·스킬 목록별 토큰(`/context` 의 분류)은 이벤트에 없어 볼 수 없다.
- 도구 하나가 쓴 토큰 수는 없다. 결과 크기(bytes)가 가장 가까운 지표다.
- 같은 종류의 서브에이전트를 한 턴에 여러 개 띄우면 종류별 합계로만 나온다.
- macOS 에서는 아직 실제로 설치해 보지 않았다.
