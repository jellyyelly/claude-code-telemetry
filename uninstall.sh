#!/usr/bin/env bash
# 제거: settings.json 에서 텔레메트리 설정과 Stop 훅을 빼고 컨테이너를 내린다.
#   (옵션 없음)      수집된 데이터(Docker 볼륨)는 남긴다
#   --purge          수집된 데이터까지 지운다
#   --settings-only  컨테이너는 그대로 두고 설정만 뺀다
set -eu
. "$(dirname "$0")/lib.sh"
need jq ""

if [ -f "$SETTINGS" ]; then
  echo "Claude Code 설정 제거: $SETTINGS"
  edit_settings --argjson keys "$ENV_KEYS" '
    (if .env then .env |= with_entries(select(.key as $k | $keys | index($k) | not)) else . end)
    | (if .env == {} then del(.env) else . end)
    | (if .hooks.Stop then .hooks.Stop = ('"$JQ_DROP_HOOK"') else . end)
    | (if .hooks.Stop == [] then del(.hooks.Stop) else . end)
    | (if .hooks == {} then del(.hooks) else . end)'
fi

case "${1:-}" in
  --settings-only) ;;
  --purge) (cd "$ROOT" && docker compose down -v); echo "컨테이너와 수집 데이터를 지웠습니다." ;;
  *) (cd "$ROOT" && docker compose down); echo "컨테이너를 내렸습니다. 수집 데이터는 남아 있습니다(지우려면 --purge)." ;;
esac
echo "제거 완료. 실행 중인 Claude Code 세션은 다시 시작해야 전송을 멈춥니다."
