#!/usr/bin/env python3
"""grafana/dashboards/claude-code-tokens.json 생성기. 실행: python3 generate-dashboard.py"""
import json, os

DS = {"type": "loki", "uid": "loki"}
SEL = '{service_name="claude-code"}'
API = SEL + ' | event_name="api_request" | session_id=~"${session}.*"'
# tool_result 의 tool_name 은 MCP 도구면 "mcp_tool", 스킬이면 "Skill" 뿐이라 tool_parameters 에서 실제 이름을 꺼낸다.
TOOL = (SEL + ' | event_name="tool_result" | session_id=~"${session}.*" | label_format tool=`'
        '{{ if eq .tool_name "mcp_tool" }}mcp:{{ regexReplaceAll ".*mcp_server_name\\":\\"([^\\"]+)\\".*mcp_tool_name\\":\\"([^\\"]+)\\".*" .tool_parameters "${1}/${2}" }}'
        '{{ else if eq .tool_name "Skill" }}Skill:{{ regexReplaceAll ".*skill_name\\":\\"([^\\"]+)\\".*" .tool_parameters "${1}" }}'
        '{{ else }}{{ .tool_name }}{{ end }}`')
# 요청 1건의 프롬프트 전체 크기(입력 + 캐시 읽기 + 캐시 쓰기)
CTX = API + ' | label_format ctx=`{{ add (int .input_tokens) (int .cache_read_tokens) (int .cache_creation_tokens) }}`'
# session-name-hook.sh 가 Stop 훅에서 남기는 세션 이름·프로젝트. 이름이 바뀌어도 가장 최근 기록만 고른다.
_META = ('max by (session_id, session_name, project) (max_over_time({service_name="claude-code-session"} | session_id=~"${session}.*" '
         '| label_format ts=`{{ __timestamp__ | unixEpoch }}` | keep session_id, session_name, project, ts | unwrap ts [$__range]))')
META = f"{_META} == on (session_id) group_left() max by (session_id) ({_META})"
TOK = [("input_tokens", "입력"), ("output_tokens", "출력"), ("cache_read_tokens", "캐시 읽기"), ("cache_creation_tokens", "캐시 쓰기")]

def by_(by): return f" by ({', '.join(by)})" if by else ""

def agg(field, by=(), rng="$__range", base=API):
    return f"sum{by_(by)} (sum_over_time({base} | keep {', '.join(list(by) + [field])} | unwrap {field} [{rng}]))"

def cnt(by=(), rng="$__range", base=API):
    return f"sum{by_(by)} (count_over_time({base} | keep {', '.join(by) if by else 'event_name'} [{rng}]))"

def ts(fn, by):
    k = ", ".join(by)
    return (f'{fn} by ({k}) ({fn}_over_time({API} | label_format ts="{{{{ __timestamp__ | unixEpoch }}}}" '
            f'| keep {k}, ts | unwrap ts [$__range])) * 1000')

def ctx(fn, by):
    k = ", ".join(by)
    return f"{fn}_over_time({CTX} | keep {k}, ctx | unwrap ctx [$__range]) by ({k})"

def usage_cols(by, base=API):
    return [(agg(f, by, base=base), label) for f, label in TOK] + [(agg("cost_usd", by, base=base), "비용 (USD)")]

def tgt(ref, expr, instant=True, legend=None):
    t = {"refId": ref, "datasource": DS, "expr": expr, "queryType": "instant" if instant else "range"}
    if legend: t["legendFormat"] = legend
    return t

pid = [0]
def panel(typ, title, grid, targets, **kw):
    pid[0] += 1
    p = {"id": pid[0], "type": typ, "title": title, "datasource": DS, "gridPos": dict(zip("xywh", grid)), "targets": targets}
    p.update(kw)
    return p

def stat(title, x, expr, unit="sishort", decimals=None):
    return panel("stat", title, (x, 0, 3, 4), [tgt("A", expr)],
                 fieldConfig={"defaults": {"unit": unit, **({"decimals": decimals} if decimals is not None else {}), "noValue": "0",
                                           "color": {"mode": "fixed", "fixedColor": "text"}}, "overrides": []},
                 options={"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "none", "graphMode": "none"})

def table(title, grid, keys, cols, sort, links_on=None, description=None, no_sum=(), extra_keys=(), hide=(),
          pre=(), extra_overrides=(), sort_desc=True, key_order=None, hide_raw=()):
    """cols: [(LogQL, 열 이름)]. Grafana 가 쿼리별 값 필드를 "Value #A" 식으로 이름 붙이므로 keys 기준으로 합친 뒤 열 이름으로 바꾼다."""
    targets = [tgt(chr(65 + i), e) for i, (e, n) in enumerate(cols)]
    raw = {n: f"Value #{chr(65 + i)}" for i, (e, n) in enumerate(cols)}
    order = list(key_order or (list(keys) + list(extra_keys))) + [raw[n] for _, n in cols]
    dates = ("시작", "마지막 활동")
    overrides = [
        {"matcher": {"id": "byName", "options": "비용 (USD)"}, "properties": [{"id": "unit", "value": "currencyUSD"}, {"id": "decimals", "value": 4}]},
        {"matcher": {"id": "byRegexp", "options": "^(%s)$" % "|".join(dates)}, "properties": [{"id": "unit", "value": "dateTimeAsIso"}, {"id": "custom.width", "value": 170}]},
        {"matcher": {"id": "byRegexp", "options": "^(%s)$" % "|".join(tuple(keys) + tuple(extra_keys))}, "properties": [{"id": "unit", "value": "string"}]},
        {"matcher": {"id": "byRegexp", "options": "^(session_id|prompt_id)$"}, "properties": [{"id": "custom.width", "value": 300}]},
        {"matcher": {"id": "byRegexp", "options": "bytes"}, "properties": [{"id": "unit", "value": "bytes"}]},
        {"matcher": {"id": "byRegexp", "options": "\\(ms\\)"}, "properties": [{"id": "unit", "value": "ms"}]},
    ]
    overrides += list(extra_overrides)
    if links_on:
        overrides.append({"matcher": {"id": "byName", "options": links_on}, "properties": [{"id": "links", "value": [
            {"title": "이 세션만 보기", "url": "/d/claude-code-tokens?var-session=${__value.raw}&${__url_time_range}"}]}]})
    kw = {"description": description} if description else {}
    return panel("table", title, grid, targets,
                 transformations=[
                     {"id": "labelsToFields", "options": {"mode": "columns"}},
                     {"id": "filterFieldsByName", "options": {"exclude": {"names": ["Time"]}}},
                     {"id": "merge", "options": {}},
                 ] + list(pre) + [
                     {"id": "organize", "options": {"excludeByName": {**{raw[h]: True for h in hide}, **{h: True for h in hide_raw}}, "indexByName": {n: i for i, n in enumerate(order)},
                                                    "renameByName": {v: k for k, v in raw.items()}}},
                 ],
                 fieldConfig={"defaults": {"unit": "sishort", "custom": {"align": "auto", "filterable": True}}, "overrides": overrides},
                 options={"showHeader": True, "sortBy": [{"displayName": sort, "desc": sort_desc}], "footer": {"show": False}},
                 **kw)

panels = []
for i, (f, label) in enumerate(TOK):
    panels.append(stat(f"{label} 토큰", i * 3, agg(f)))
panels.append(stat("비용 (USD)", 12, agg("cost_usd"), "currencyUSD", 4))
panels.append(stat("API 요청", 15, cnt()))
panels.append(stat("턴", 18, f"count({cnt(('prompt_id',))})"))
panels.append(stat("세션", 21, f"count({cnt(('session_id',))})"))

legend = {"tooltip": {"mode": "multi"}, "legend": {"displayMode": "table", "placement": "bottom", "calcs": ["sum"]}}
bars = lambda unit, dec=None: {"defaults": {"unit": unit, **({"decimals": dec} if dec else {}),
                                            "custom": {"drawStyle": "bars", "fillOpacity": 70, "lineWidth": 0, "stacking": {"mode": "normal"}}}, "overrides": []}
panels.append(panel("timeseries", "토큰 사용량 추이 (종류별)", (0, 4, 14, 8),
                    [tgt("ABCD"[i], agg(f, rng="$__interval"), False, label) for i, (f, label) in enumerate(TOK)],
                    fieldConfig=bars("sishort"), options=legend))
panels.append(panel("timeseries", "비용 추이 (모델별)", (14, 4, 10, 8),
                    [tgt("A", agg("cost_usd", ("model",), "$__interval"), False, "{{model}}")],
                    fieldConfig=bars("currencyUSD", 4), options=legend))

ALL = SEL + ' | event_name="api_request"'
def wk(expr_fn):
    """expr_fn(범위) -> 라벨 없는 단일 값 LogQL. 이번 7일 / 직전 7일 / 증감 / 증감률 네 식을 돌려준다."""
    cur, prev = expr_fn("[7d]"), expr_fn("[7d] offset 7d")
    return cur, f"({prev} or vector(0))", f"({cur} - ({prev} or vector(0)))", f"(({cur} - {prev}) / {prev})"
def w_sum(f): return lambda r: f"sum(sum_over_time({ALL} | keep {f} | unwrap {f} {r}))"
def w_cnt(by): return lambda r: (f"count(sum by ({by}) (count_over_time({ALL} | keep {by} {r})))" if by
                                else f"sum(count_over_time({ALL} | keep event_name {r}))")
w_turns = w_cnt("prompt_id")
ROWS = [("1. 비용", w_sum("cost_usd")), ("2. 턴당 평균 비용", lambda r: f"({w_sum('cost_usd')(r)} / {w_turns(r)})"),
        ("1. 세션", w_cnt("session_id")), ("2. 턴", w_turns), ("3. API 요청", w_cnt(None)),
        ("4. 입력 토큰", w_sum("input_tokens")), ("5. 출력 토큰", w_sum("output_tokens")),
        ("6. 캐시 읽기 토큰", w_sum("cache_read_tokens")), ("7. 캐시 쓰기 토큰", w_sum("cache_creation_tokens"))]
def wow(title, grid, rows, unit_props=()):
    col = lambda i: " or ".join(f'label_replace({wk(fn)[i]}, "metric", "{name}", "", "")' for name, fn in rows)
    return table(title, grid, ("metric",),
                 [(col(0), "최근 7일"), (col(1), "직전 7일"), (col(2), "증감"), (col(3), "증감률")], sort="metric", sort_desc=False,
                 description="대시보드 시간 범위의 끝 시각을 기준으로 최근 7일과 그 직전 7일을 비교한다(시간 범위 길이·세션 필터와 무관, 전체 세션 대상). "
                             "직전 7일에 데이터가 없으면 증감률 열은 나오지 않는다.",
                 extra_overrides=[
                     {"matcher": {"id": "byName", "options": "metric"}, "properties": [{"id": "displayName", "value": "항목"}, {"id": "custom.width", "value": 230}]},
                     {"matcher": {"id": "byRegexp", "options": "^(최근 7일|직전 7일|증감)$"}, "properties": list(unit_props)},
                     {"matcher": {"id": "byName", "options": "증감률"}, "properties": [
                         {"id": "unit", "value": "percentunit"}, {"id": "decimals", "value": 1},
                         {"id": "custom.cellOptions", "value": {"type": "color-text"}},
                         {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "text", "value": -0.05}, {"color": "red", "value": 0.05}]}}]},
                 ])
# 비용과 건수·토큰은 단위가 달라 표를 나눈다. UI 에서 옮긴 위치(도구별 표 아래)에 둔다.
WOW = [wow("주간 대비 증감: 비용 (최근 7일 vs 직전 7일)", (0, 58, 9, 10), ROWS[:2],
           [{"id": "unit", "value": "currencyUSD"}, {"id": "decimals", "value": 4}]),
       wow("주간 대비 증감: 사용량 (최근 7일 vs 직전 7일)", (9, 58, 15, 10), ROWS[2:])]
panels += WOW

S = ("session_id",)
panels.append(table("세션별 사용량", (0, 12, 24, 9), S, [
    (ts("min", S), "시작"), (ts("max", S), "마지막 활동"),
    (f"count by (session_id) ({cnt(('session_id', 'prompt_id'))})", "턴"), (cnt(S), "API 요청"),
    (ctx("first", S), "초기 컨텍스트"), (ctx("max", S), "최대 컨텍스트")] + usage_cols(S) + [(META, "이름 기록 시각")],
    sort="마지막 활동", links_on="session_id", no_sum=("초기 컨텍스트", "최대 컨텍스트"),
    extra_keys=("session_name", "project"), hide=("이름 기록 시각",),
    description="초기 컨텍스트 = 세션 첫 API 요청의 프롬프트 크기(입력+캐시 읽기+캐시 쓰기). 시스템 프롬프트·도구 정의·메모리 파일·스킬 목록을 합친 고정 부담의 근사값이다. "
                "최대 컨텍스트 = 세션 중 가장 컸던 요청의 프롬프트 크기. session_name·project 는 Stop 훅(session-name-hook.sh)이 기록한 값이라 첫 턴이 끝나기 전에는 비어 있다. session_id 를 누르면 아래 표들이 그 세션으로 좁혀진다."))
T = ("session_id", "prompt_id", "model")
panels.append(table("턴별 사용량 (prompt.id 기준)", (0, 21, 24, 11), T,
                    [(ts("min", T), "시작"), (cnt(T), "API 요청")] + usage_cols(T), sort="턴 번호",
                    description="턴 번호 = 선택한 기간 안에서 그 세션의 몇 번째 턴인지(시작 시각 순). 기간이 세션 시작보다 늦게 잡히면 번호가 1부터 다시 매겨진다.",
                    key_order=("session_id", "턴 번호", "prompt_id", "model"), hide_raw=("_idx",),
                    pre=[  # "Value #A" = 시작 시각(이름을 바꾸기 전)
                        {"id": "sortBy", "options": {"sort": [{"field": "Value #A", "desc": False}]}},
                        {"id": "partitionByValues", "options": {"fields": ["session_id"], "keepFields": True}},
                        {"id": "calculateField", "options": {"mode": "index", "alias": "_idx", "index": {"asPercentile": False}}},
                        {"id": "calculateField", "options": {"mode": "binary", "alias": "턴 번호", "binary": {
                            "left": {"matcher": {"id": "byName", "options": "_idx"}}, "operator": "+", "right": {"fixed": "1"}}}},
                        {"id": "merge", "options": {}},
                    ],
                    extra_overrides=[{"matcher": {"id": "byName", "options": "턴 번호"}, "properties": [{"id": "unit", "value": "none"}, {"id": "custom.width", "value": 90}]}]))

SK = ("skill_name",)
sk = API + ' | skill_name!=""'
panels.append(table("스킬별 귀속 사용량", (0, 32, 10, 9), SK, [(cnt(SK, base=sk), "API 요청")] + usage_cols(SK, sk), sort="비용 (USD)",
                    description="api_request 이벤트의 skill_name 기준. 스킬이 활성화된 뒤의 요청에 계속 붙으므로 MCP 표와 겹칠 수 있다(합산 금지)."))
MC = ("mcp_server_name", "mcp_tool_name")
mc = API + ' | mcp_server_name!=""'
panels.append(table("MCP 서버·도구별 귀속 사용량", (10, 32, 14, 9), MC, [(cnt(MC, base=mc), "API 요청")] + usage_cols(MC, mc), sort="비용 (USD)",
                    description="api_request 이벤트의 mcp_server_name / mcp_tool_name 기준. MCP 도구 결과를 처리한 요청의 토큰이다."))
AG = ("agent_name",)
ag = API + ' | agent_name!=""'
# subagent_completed 는 이름을 agent_type 으로 싣기 때문에 agent_name 으로 맞춘다.
done = SEL + ' | event_name="subagent_completed" | session_id=~"${session}.*" | label_format agent_name=`{{ .agent_type }}`'
panels.append(table("서브에이전트별 사용량", (0, 41, 24, 8), AG, [
    (cnt(AG, base=done), "실행"), (agg("total_tool_uses", AG, base=done), "도구 호출"), (agg("duration_ms", AG, base=done), "소요 (ms)"),
    (cnt(AG, base=ag), "API 요청")] + usage_cols(AG, ag), sort="비용 (USD)",
    description="api_request 이벤트의 agent_name 기준(서브에이전트가 보낸 요청만). 서브에이전트 요청은 부모 세션의 session_id·prompt_id 를 그대로 쓰므로 "
                "위 세션별·턴별 합계에 이미 포함되어 있다. 실행·도구 호출·소요는 subagent_completed 이벤트 기준이다."))
TL = ("tool",)
panels.append(table("도구별 호출 수와 입출력 크기", (0, 49, 24, 9), TL, [
    (cnt(TL, base=TOOL), "호출"), (cnt(TL, base=TOOL + ' | success="false"'), "실패"),
    (agg("tool_input_size_bytes", TL, base=TOOL), "입력 bytes"), (agg("tool_result_size_bytes", TL, base=TOOL), "결과 bytes"),
    (agg("duration_ms", TL, base=TOOL), "소요 (ms)")], sort="결과 bytes",
    description="tool_result 이벤트 기준. 결과 bytes 가 클수록 이후 요청의 입력 토큰을 많이 차지한다. 토큰 수 자체는 도구 단위로 제공되지 않는다."))

panels.append(panel("logs", "API 요청 원본 이벤트", (0, 58, 24, 10),
                    [tgt("A", API + ' | line_format "{{.model}}  in={{.input_tokens}} out={{.output_tokens}} cache_read={{.cache_read_tokens}} cache_write={{.cache_creation_tokens}} cost=${{.cost_usd}} {{.duration_ms}}ms  agent={{.agent_name}} skill={{.skill_name}} mcp={{.mcp_server_name}}/{{.mcp_tool_name}}  session={{.session_id}} prompt={{.prompt_id}}"', False)],
                    options={"showTime": True, "sortOrder": "Descending", "enableLogDetails": True, "wrapLogMessage": False}))

for p in panels:  # 주간 대비 패널(높이 10)을 끼워 넣은 만큼 그 아래 패널을 내린다.
    if p not in WOW and p["gridPos"]["y"] >= 58:
        p["gridPos"]["y"] += 10

dash = {
    "uid": "claude-code-tokens", "title": "Claude Code 토큰 사용량", "tags": ["claude-code"],
    "timezone": "Asia/Seoul", "schemaVersion": 39, "editable": True, "refresh": "10s",
    "time": {"from": "now-24h", "to": "now"},
    "templating": {"list": [{"name": "session", "label": "세션 ID (비우면 전체)", "type": "textbox",
                             "query": "", "current": {"text": "", "value": ""}, "options": [{"selected": True, "text": "", "value": ""}]}]},
    "panels": panels,
}
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grafana/dashboards/claude-code-tokens.json")
json.dump(dash, open(out, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
if os.environ.get("PRINT_EXPRS"):
    for p in panels:
        for t in p["targets"]:
            if t["queryType"] == "instant": print(t["expr"])
