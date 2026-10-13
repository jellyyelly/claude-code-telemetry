# install.sh / uninstall.sh 공용. macOS 기본 bash(3.2)에서도 돌도록 쓴다.
ROOT=$(cd "$(dirname "$0")" && pwd)
# .env 는 Windows 편집기로 고치면 CRLF 가 되므로 CR 을 떼고 읽는다.
[ -f "$ROOT/.env" ] && eval "$(tr -d '\r' < "$ROOT/.env")"
GRAFANA_PORT=${GRAFANA_PORT:-23000}
LOKI_PORT=${LOKI_PORT:-23100}
SETTINGS=${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}
HOOK="$ROOT/session-name-hook.sh"
ENV_KEYS='["CLAUDE_CODE_ENABLE_TELEMETRY","OTEL_LOGS_EXPORTER","OTEL_EXPORTER_OTLP_LOGS_PROTOCOL","OTEL_EXPORTER_OTLP_LOGS_ENDPOINT","OTEL_LOG_TOOL_DETAILS"]'

die() { echo "오류: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "$1 이(가) 필요합니다. $2"; }

# settings.json 을 jq 필터로 고친다. 고치기 전 내용을 백업하고 백업 경로를 출력한다.
edit_settings() {
  mkdir -p "$(dirname "$SETTINGS")"
  [ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
  jq empty "$SETTINGS" 2>/dev/null || die "$SETTINGS 가 올바른 JSON 이 아닙니다. 고친 뒤 다시 실행하세요."
  bak="$SETTINGS.bak-telemetry-$(date +%Y%m%d-%H%M%S)"
  cp "$SETTINGS" "$bak"
  tmp=$(mktemp)
  jq "$@" "$bak" > "$tmp" || { rm -f "$tmp"; die "settings.json 수정 실패 (원본은 그대로입니다)"; }
  cat "$tmp" > "$SETTINGS"; rm -f "$tmp"
  echo "  설정 백업: $bak"
}
# 이 저장소의 훅 항목(경로가 달라졌어도)을 Stop 훅 목록에서 뺀다.
JQ_DROP_HOOK='(.hooks.Stop // []) | map(select(((.hooks // []) | any((.command // "") | contains("session-name-hook.sh"))) | not))'
