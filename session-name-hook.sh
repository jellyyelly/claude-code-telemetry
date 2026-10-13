#!/usr/bin/env bash
# Claude Code Stop 훅: 세션 이름과 프로젝트를 Loki 에 기록한다(OTel 이벤트에는 세션 이름이 없다).
# 이름은 세션 기록 파일의 custom-title(/rename) 이 있으면 그것, 없으면 ai-title 을 쓴다.
# 실패해도 Claude Code 를 막지 않도록 항상 조용히 0 으로 끝낸다.
dir=$(cd "$(dirname "$0")" && pwd)
[ -f "$dir/.env" ] && eval "$(tr -d '\r' < "$dir/.env")"  # CRLF 로 저장된 .env 대비
in=$(cat)
sid=$(jq -r '.session_id // empty' <<<"$in" 2>/dev/null)
t=$(jq -r '.transcript_path // empty' <<<"$in" 2>/dev/null)
cwd=$(jq -r '.cwd // empty' <<<"$in" 2>/dev/null)
[ -n "$sid" ] || exit 0
name=""
if [ -f "$t" ]; then
  name=$(grep -E '"type":"(custom-title|ai-title)"' "$t" 2>/dev/null \
    | jq -rs '(map(select(.type=="custom-title") | .customTitle) | last) // (map(select(.type=="ai-title") | .aiTitle) | last) // ""' 2>/dev/null)
fi
# macOS 의 date 는 나노초(%N)를 지원하지 않아 초 단위에 0 을 붙인다.
jq -nc --arg ts "$(date +%s)000000000" --arg sid "$sid" --arg name "$name" --arg project "$(basename "${cwd:-unknown}")" --arg cwd "$cwd" \
  '{streams: [{stream: {service_name: "claude-code-session"},
     values: [[$ts, ($name + " (" + $project + ")"),
       ({session_id: $sid, session_name: $name, project: $project, cwd: $cwd} | with_entries(select(.value != "")))]]}]}' \
  | curl -s -o /dev/null --max-time 2 -H 'Content-Type: application/json' --data-binary @- "http://localhost:${LOKI_PORT:-23100}/loki/api/v1/push"
exit 0
