#!/usr/bin/env bash
# Claude Code 토큰 사용량 대시보드 설치: Loki·Grafana 기동 + ~/.claude/settings.json 에 텔레메트리 설정과 Stop 훅 등록.
# 여러 번 실행해도 된다. 옵션은 ./install.sh --help 참고.
set -eu
usage() {
  cat <<USAGE
사용법: ./install.sh [--grafana-port 포트] [--loki-port 포트] [--settings-only]
  --grafana-port N   Grafana 포트 (기본 23000)
  --loki-port N      Loki 포트 (기본 23100)
  --settings-only    컨테이너는 건드리지 않고 Claude Code 설정만 다시 등록
포트 옵션은 .env 에 저장되어 다음 실행과 제거, 훅에서 그대로 쓰인다.
USAGE
}
OPT_GRAFANA=""; OPT_LOKI=""; SETTINGS_ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --grafana-port) OPT_GRAFANA=${2:-}; shift 2 || { usage; exit 1; } ;;
    --loki-port) OPT_LOKI=${2:-}; shift 2 || { usage; exit 1; } ;;
    --settings-only) SETTINGS_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "알 수 없는 옵션: $1" >&2; usage; exit 1 ;;
  esac
done
. "$(dirname "$0")/lib.sh"

check_port() {  # 이름, 값
  case "$2" in ''|*[!0-9]*) die "$1 포트는 숫자여야 합니다: '$2'" ;; esac
  [ "$2" -ge 1024 ] && [ "$2" -le 65535 ] || die "$1 포트는 1024~65535 범위여야 합니다: $2"
}
[ -n "$OPT_GRAFANA" ] && GRAFANA_PORT=$OPT_GRAFANA
[ -n "$OPT_LOKI" ] && LOKI_PORT=$OPT_LOKI
check_port Grafana "$GRAFANA_PORT"; check_port Loki "$LOKI_PORT"
[ "$GRAFANA_PORT" != "$LOKI_PORT" ] || die "Grafana 와 Loki 포트가 같습니다: $GRAFANA_PORT"

need jq "macOS: brew install jq / Ubuntu: sudo apt install jq"
need curl ""
if [ -z "$SETTINGS_ONLY" ]; then
  need docker "Docker Desktop 또는 OrbStack 을 설치하고 실행하세요."
  docker compose version >/dev/null 2>&1 || die "docker compose (v2) 가 필요합니다."
  docker info >/dev/null 2>&1 || die "Docker 가 실행 중이 아닙니다."
  # 이미 이 스택이 쓰고 있는 포트가 아니라면, 다른 프로그램이 점유 중인지 미리 확인한다.
  busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
  mine() { (cd "$ROOT" && docker compose port "$1" "$2" 2>/dev/null) | grep -q ":$3\$"; }
  mine grafana 3000 "$GRAFANA_PORT" || ! busy "$GRAFANA_PORT" || die "포트 $GRAFANA_PORT 를 다른 프로그램이 쓰고 있습니다. --grafana-port 로 바꾸세요."
  mine loki 3100 "$LOKI_PORT" || ! busy "$LOKI_PORT" || die "포트 $LOKI_PORT 를 다른 프로그램이 쓰고 있습니다. --loki-port 로 바꾸세요."
  echo "컨테이너 기동 (Grafana :$GRAFANA_PORT, Loki :$LOKI_PORT)"
  (cd "$ROOT" && GRAFANA_PORT=$GRAFANA_PORT LOKI_PORT=$LOKI_PORT docker compose up -d) || die "컨테이너 기동 실패"
  printf "Loki 준비 대기"
  i=0; until curl -sf "http://localhost:$LOKI_PORT/ready" >/dev/null 2>&1; do
    i=$((i + 1)); [ $i -gt 60 ] && { echo; die "Loki 가 2분 안에 준비되지 않았습니다: docker compose logs loki"; }
    printf "."; sleep 2
  done; echo " 완료"
fi

# 포트 검사와 기동이 끝난 뒤에만 저장한다(실패한 포트가 남지 않게).
if [ -n "$OPT_GRAFANA$OPT_LOKI" ]; then
  printf 'GRAFANA_PORT=%s\nLOKI_PORT=%s\n' "$GRAFANA_PORT" "$LOKI_PORT" > "$ROOT/.env"
  echo "포트 설정 저장: $ROOT/.env"
fi

chmod +x "$HOOK"
echo "Claude Code 설정 등록: $SETTINGS"
edit_settings --arg endpoint "http://localhost:$LOKI_PORT/otlp/v1/logs" --arg hook "bash \"$HOOK\"" '
  .env = ((.env // {}) + {
    CLAUDE_CODE_ENABLE_TELEMETRY: "1",
    OTEL_LOGS_EXPORTER: "otlp",
    OTEL_EXPORTER_OTLP_LOGS_PROTOCOL: "http/protobuf",
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: $endpoint,
    OTEL_LOG_TOOL_DETAILS: "1"
  })
  | .hooks = (.hooks // {})
  | .hooks.Stop = ('"$JQ_DROP_HOOK"') + [{hooks: [{type: "command", command: $hook, timeout: 5}]}]'

cat <<MSG

설치 완료.
  대시보드: http://localhost:$GRAFANA_PORT
  지금부터 새로 시작하는 Claude Code 세션이 기록됩니다(실행 중인 세션은 다시 시작해야 합니다).
  제거: ./uninstall.sh
MSG
