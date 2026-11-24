# BSCR v2 내부 Codex 배치 번역기·검증·Repair 사양

## 1. 목적과 비범위

이 문서는 `translation/bscr_v2`의 compact cluster 패킷을 Codex 내부 모델로 초벌 번역하고, 기계 검증 뒤 실패 cluster만 제한적으로 다시 번역하며, 최종적으로 occurrence별 authoritative map을 만드는 절차를 정의한다.

- 번역 의미 원문: 일본어 BSCR.
- 영어 BSCR: 문맥 보조 전용.
- 모델: Codex 내부 모델만 사용. 외부 번역 API·외부 LLM 금지.
- 본 단계는 **초벌 번역과 구조 검증**이다. 전체 초벌 완료 뒤 별도의 통합 언어 검수를 수행한다.
- 이 문서는 runner 계약이며, BSCR payload 주입·아카이브 재패킹·UI·게임 실행은 다루지 않는다.

## 2. 권위 입력과 산출물

### 2.1 권위 입력

| 경로 | 역할 |
|---|---|
| `occurrence_catalog.jsonl` | occurrence 원문, 안정 UID, 구조·해시·문맥의 권위 자료 |
| `occurrence_fanout.jsonl` | `cluster_id`에서 occurrence UID로 확장하는 고정 관계 |
| `draft_units.jsonl` | compact cluster 초벌 상태의 집계 자료 |
| `packets/packet_NNNN.json` | 모델에 투입할 compact cluster 패킷 |
| `packets_manifest.json` | 패킷 수·카탈로그 해시·패킷 해시의 권위 manifest |
| `translation_prompt.md` | 초벌 번역 지시 |
| `style_guide_bscr.md` | 인물 문체·기본 원칙 |
| `glossary_bscr.json` | 인명·호칭·고정 용어 |
| `audit/bscr_file_contexts.json` | 파일별 장면 방향성 보조 자료 |
| `audit/bscr_visibility_audit.json` | 가시성·preserve 정책 |

runner는 시작 전에 manifest가 기록한 카탈로그·빈 map·각 패킷 SHA-256을 다시 계산해 일치하지 않으면 중단한다. 모델 출력의 원문 필드는 권위가 아니며, merge 때 항상 위 입력에서 다시 가져온다.

### 2.2 단계별 산출물

1. `results/draft/packet_NNNN.result.json`: cluster 초벌 결과.
2. `reports/packet_NNNN.validation.json`: cluster 구조·번역 검증 결과.
3. `repair/round_R/packet_NNNN.repair-input.json`: 해당 round 실패 cluster만 담은 입력.
4. `repair/round_R/packet_NNNN.repair-result.json`: 실패 cluster의 교체 후보.
5. `draft_units.translated.jsonl`: 검증 통과 cluster만 반영한 전체 cluster 지도.
6. `translation_map.draft.jsonl`: catalog 순서를 유지한 occurrence별 초벌 지도.
7. `reports/translation_map.draft.validation.json`: occurrence-level 완전성·불변 필드·번역 구조 보고서.

원시 응답, 파싱된 응답, 각 repair round는 덮어쓰지 않고 별도로 보존한다. 최종 map에 사용된 결과의 packet·round를 provenance에 기록한다.

## 3. Compact 패킷 계약

패킷 schema는 `criminal-girls.bscr-compact-draft-packet.v2`다. 최상위 필드는 다음과 같다.

```json
{
  "schema": "criminal-girls.bscr-compact-draft-packet.v2",
  "packet_id": "bscr_v2_0001",
  "source_language": "ja",
  "target_language": "ko",
  "semantic_source": "Japanese BSCR",
  "reference_only": "paired English BSCR aligned by normalized records",
  "cluster_key": "exact (source_ja, reference_en)",
  "entry_count": 80,
  "entries": []
}
```

각 `entries[]`는 다음 필드를 가진다.

```json
{
  "cluster_id": "bscr2_c00001",
  "source_ja": "$0……\n……ありがとね。",
  "reference_en": "$0……\n……ありがとね。",
  "occurrence_count": 8,
  "uids": ["bscr2:..."],
  "max_utf8_bytes": 33,
  "protected_tokens": ["$0"],
  "newline_signature": {"lf": 1, "cr": 0},
  "candidate_classes": ["display_known"],
  "consumer_roles": ["message"],
  "context_samples": [],
  "occurrence_review_required": false,
  "conflict_reasons": [],
  "status": "pending",
  "target_ko": ""
}
```

cluster는 정확한 `(source_ja, reference_en)` 쌍으로 묶였지만, 이것만으로 모든 occurrence가 같은 번역을 가져도 된다고 단정하지 않는다. `occurrence_review_required: true` 또는 비어 있지 않은 `conflict_reasons`가 있으면 자동 fanout을 금지하고 occurrence별 검수 큐로 보낸다.

## 4. Draft 모델 출력 JSON schema

### 4.1 출력 외형

모델은 Markdown 코드 펜스·설명 없이 다음 객체 하나만 반환한다. 배열만 반환하는 형태보다 `packet_id`와 개수를 함께 바인딩하여 wrong-packet 응답을 검출한다.

```json
{
  "schema": "criminal-girls.bscr-compact-draft-result.v2",
  "packet_id": "bscr_v2_0001",
  "entries": [
    {
      "cluster_id": "bscr2_c00001",
      "source_ja": "$0……\n……ありがとね。",
      "reference_en": "$0……\n……ありがとね。",
      "status": "translated",
      "target_ko": "$0……\n……고마워."
    }
  ]
}
```

### 4.2 JSON Schema 의미 규칙

최상위:

- `schema`: 상수 `criminal-girls.bscr-compact-draft-result.v2`.
- `packet_id`: 입력과 정확히 동일.
- `entries`: 입력과 같은 길이와 순서. 모든 `cluster_id`가 정확히 한 번 등장해야 한다.
- `additionalProperties: false` 권장.

entry 공통 필드:

- 필수: `cluster_id`, `source_ja`, `reference_en`, `status`, `target_ko`.
- `cluster_id`, `source_ja`, `reference_en`는 입력과 byte-for-byte 동일.
- `status`는 `translated | pending | preserve`만 허용.
- `target_ko`는 항상 JSON string.
- `additionalProperties: false`, 단 `preserve` 분기에서만 `preserve_evidence` 허용.

상태별 조건:

```text
translated => target_ko != ""; preserve_evidence 없음
pending    => target_ko == ""; preserve_evidence 없음
preserve   => target_ko == ""; preserve_evidence 필수
```

`preserve_evidence` schema:

```json
{
  "kind": "proven_internal_identifier",
  "artifact": "audit/path.json#stable-entry",
  "detail": "어느 consumer trace가 왜 표시되지 않음을 증명하는지 구체적으로 설명"
}
```

`kind` 허용값:

- `proven_lookup_key`
- `proven_internal_identifier`
- `engine_control_literal`
- `runtime_required_literal`
- `not_user_visible_by_consumer_trace`

초벌 모델은 새 소비자 증거를 만들 수 없으므로, 입력에 이미 허용된 evidence가 없다면 `preserve`를 선택해서는 안 된다. debug 정규식 일치 항목은 `pending`이며 최종 preserve가 아니다.

## 5. 검증 파이프라인

검증은 **파싱/구조 → 입력 결속 → 상태 → 문자열 불변조건 → 숫자 → fanout → occurrence map** 순으로 한다. 앞 단계 실패가 뒤 단계의 가짜 오류를 만들 수 있으므로 오류를 누적하되 해당 단계에 필요한 필드가 없으면 종속 검사는 생략한다.

각 오류는 최소한 다음 필드를 기록한다.

```json
{
  "code": "protected_token_mismatch",
  "packet_id": "bscr_v2_0001",
  "cluster_id": "bscr2_c00001",
  "uid": null,
  "expected": ["$0"],
  "actual": [],
  "detail": "보호 토큰의 값·개수·순서가 다름",
  "repairable": true
}
```

### 5.1 파싱·구조 validator

필수 검사:

- strict UTF-8 decode. BOM은 입력 정책에 따라 한 번만 허용하되 결과를 UTF-8 no-BOM으로 정규화한다.
- JSON 객체 하나만 허용. 코드 펜스, 선행·후행 설명, 중복 JSON 값 금지.
- duplicate JSON key를 거부하는 parser 사용.
- schema, packet_id, 필수 필드, 타입, enum, additional property 검사.
- 입력 `entry_count`, 결과 배열 길이, cluster ID 집합과 순서 검사.
- 중복·누락·미지 cluster ID 거부.

권장 cluster 오류 코드:

- `invalid_json`
- `duplicate_json_key`
- `invalid_result_schema`
- `packet_id_mismatch`
- `entry_count_mismatch`
- `unknown_cluster_id`
- `duplicate_cluster_id`
- `missing_cluster_result`
- `missing_cluster_field`
- `cluster_immutable_field_mismatch`
- `invalid_status`
- `target_not_string`

JSON 자체가 파싱되지 않거나 packet_id가 다르면 항목별 repair가 아니라 동일 패킷 전체를 **format retry**한다. 첫 응답에서 복원 가능한 JSON 조각을 임의 추출해 merge하지 않는다.

### 5.2 상태 validator

- `pending` + 비어 있지 않은 target: `pending_has_target`.
- 완성 map gate에서 남은 `pending`: `pending_not_allowed_in_complete_map`.
- `preserve` + 비어 있지 않은 target: `preserve_has_target`.
- 허용 evidence가 없거나 kind/artifact/detail이 빈 preserve: `unproven_preserve`.
- `translated` + 빈 target: `empty_translation`.

초벌 단계에서 모델이 해결하지 못한 항목은 `pending`으로 남기는 것이 허위 `preserve`보다 낫다. 다만 complete-map gate에서는 `pending`을 단 한 건도 허용하지 않는다.

### 5.3 보호 토큰 validator

권위 expected는 모델 출력이 아니라 패킷의 `protected_tokens`다. 현재 카탈로그의 토큰은 `$0`, `$1`, `$2`, `$3`, `$5`지만 구현은 이 목록을 하드코딩하지 않고 entry의 배열을 사용한다.

검사 절차:

1. target에서 **전체 토큰 시퀀스**를 추출한다. 최소 패턴은 `\$[0-9]+`이며, 향후 카탈로그가 더 긴 엔진 토큰을 정의하면 catalog tokenizer와 동일 구현을 공유한다.
2. `actual_tokens == protected_tokens`를 배열 비교한다. Counter 비교만 하지 않는다.
3. 토큰 값, 중복 수, 등장 순서 중 하나라도 다르면 `protected_token_mismatch`.
4. expected에 없는 `$숫자`가 target에 있으면 역시 mismatch.

예: expected `[$3,$2,$1,$2]`에 대해 `[$1,$2,$3,$2]`는 multiset은 같아도 실패다. 토큰 사이 텍스트의 위치 이동은 허용하지만 토큰 쌍의 의미 범위를 바꾸지 않았는지는 통합 검수에서 추가 확인한다.

### 5.4 개행 validator

- Python 기준 `actual_lf = target_ko.count("\n")`, `actual_cr = target_ko.count("\r")`.
- 각각 `newline_signature.lf`, `.cr`와 정확히 일치해야 한다.
- CRLF는 CR 1 + LF 1로 센다. `.lf`, `.cr`를 독립 비교한다.
- 실제 개행을 두 글자 backslash+n으로 만든 출력은 JSON decode 뒤 `\\n`으로 남으므로 LF count가 맞지 않아 실패한다.
- mismatch 오류: `newline_mismatch`.

개행 위치와 각 줄의 의미 대응은 기계 count 검사만으로 완전히 증명되지 않는다. 원문의 줄 순서가 바뀌거나 문장 조각이 다른 줄로 이동한 의심은 통합 검수 대상으로 기록한다.

### 5.5 UTF-8 byte cap·NUL validator

```python
if "\x00" in target_ko:
    error("nul_in_translation")
if len(target_ko.encode("utf-8")) > max_utf8_bytes:
    error("utf8_byte_cap_exceeded")
```

- `max_utf8_bytes`는 패킷에서 가져오며 cluster의 모든 occurrence에 안전한 상한이다.
- Unicode code point나 UTF-16 code unit가 아닌 strict UTF-8 byte length를 잰다.
- normalization(NFC/NFKC)을 **검사 전에 자동 적용하지 않는다**. 모델이 제출한 실제 bytes를 검사하고, repair 결과도 그대로 검사한다.
- 바이트를 줄이려고 토큰·개행·숫자·의미를 삭제한 결과는 각각의 validator나 언어 검수에서 실패시킨다.

### 5.6 일본어 잔여 validator

`status: translated`에만 적용한다. 기본 강한 오류 대상은 다음이다.

```regex
[\u3040-\u309F\u30A0-\u30FF]
```

- 히라가나·가타카나 잔여는 `japanese_residue_in_translation`.
- CJK 통합 한자는 한국어에서도 합법이고 인명·기호·코드일 수 있으므로 범위 전체를 자동 오류로 처리하지 않는다.
- `々`, `〆`, `ヵ`, `ヶ`, 일본어 인용부호 등 일본어 전용 기호는 별도 residue set으로 탐지할 수 있다. 다만 `$` 토큰과 일반 `「」` 같은 의도적 문장부호 정책은 명시적 allowlist로 관리한다.
- 고정 용어가 의도적으로 일본 문자 표기를 요구한다면 UID·정확 문자열 allowlist와 근거가 있어야 한다. 전역 예외 금지.
- 카타카나가 보호 토큰 내부에 들어갈 가능성이 생기면 토큰 범위를 먼저 마스킹하고 검사한다.

한자 원문 복사, 의미 누락, 한국어 조사만 덧붙인 혼합문은 이 정규식만으로 잡히지 않는다. 다음 통합 검수에서 source-target 유사도·한국어 문자 비율·용어 검사를 추가하되, 구조 validator가 이를 완성 증거로 과장하지 않는다.

### 5.7 숫자·수치 보존 validator

숫자 보존은 잘못 설계하면 일본어 전각 숫자→한국어 반각 숫자 같은 정상 번역을 거부한다. 따라서 원문과 target을 `NFKC`로 **검사용 복사본에서만** 정규화하고, 보호 토큰을 먼저 마스킹한 뒤 비교한다. 실제 target을 수정하지 않는다.

#### A. 강제 오류 비교

1. ASCII/전각 아라비아 숫자열을 NFKC 후 추출한다.
2. 소수점, 부호, `%`, 배수 `×`, 범위 `- / ～ / 〜`, 층수·레벨 등 바로 붙은 단위를 포함한 수치 원자를 만든다.
3. 원문과 target의 수치 원자 sequence를 비교한다.
4. 값, 개수, 순서가 바뀌면 `numeric_literal_mismatch`.
5. 영숫자 코드(`KN18A`, `832-00`, `1F`, `lv1`)는 하나의 identifier 원자로 보존한다. 내부 숫자만 떼어 비교하지 않는다.

일본어 단위가 한국어로 번역되는 것은 허용하되 숫자 값은 동일해야 한다. 예: `５個`→`5개`, `１Ｆ`→`1층`은 통과 가능하다. `832-00`→`832-0`은 실패다.

#### B. 수동 검수 경고

- 일본어 한자 수사(`一二三四五六七八九十百千万億兆`)는 고유명사·관용구와 충돌하므로 전역 강제 비교하지 않는다.
- 단, 전후 문맥상 명확한 수량·서수·층수인 경우 `numeric_semantic_review` 경고를 내고 통합 검수에서 확인한다.
- `ひとつ`, `ふたり`처럼 철자로 쓴 수량도 의미 검수 대상이지 단순 literal validator 대상이 아니다.

숫자 validator는 **값 보존**만 증명하며 효과 범위, 증가/감소, 이상/이하, 대상 수 같은 기계 의미 보존을 대신하지 않는다.

### 5.8 occurrence fanout 및 authoritative map validator

compact 결과의 cluster 필드를 그대로 occurrence map으로 신뢰하지 않는다. runner가 다음 절차로 확장한다.

1. `occurrence_fanout.jsonl`에서 `cluster_id -> uid[]` 관계를 로드하고 중복 UID·미지 cluster를 거부한다.
2. 각 UID의 authoritative occurrence를 `occurrence_catalog.jsonl`에서 조회한다.
3. compact 결과에서 오직 `status`, `target_ko`, 검증 provenance만 가져온다.
4. 아래 immutable occurrence 필드는 **catalog에서 복제**한다.
   - `uid`
   - `file`
   - `segment_index`
   - `relative_offset`
   - `absolute_offset`
   - `source_ja`
   - `source_sha256`
   - `source_utf8_bytes`
   - `max_utf8_bytes`
   - `original_file_sha256`
5. catalog 순서 그대로 `translation_map.draft.jsonl`을 쓴다.
6. `occurrence_review_required` 또는 `conflict_reasons`가 있으면 cluster target을 자동 fanout하지 말고 occurrence-specific 결과가 해결될 때까지 pending 처리한다.
7. occurrence별 validator를 전체 map에 다시 실행한다. cluster 검증 통과는 fanout·불변 필드·전체 coverage 통과를 대신하지 않는다.

authoritative occurrence validator의 기존 오류 코드는 다음을 고정한다.

- `unknown_uid`
- `missing_translation_row`
- `missing_immutable_field`
- `immutable_field_mismatch`
- `invalid_status`
- `target_not_string`
- `pending_has_target`
- `pending_not_allowed_in_complete_map`
- `preserve_has_target`
- `unproven_preserve`
- `empty_translation`
- `nul_in_translation`
- `protected_token_mismatch`
- `newline_mismatch`
- `utf8_byte_cap_exceeded`
- `japanese_residue_in_translation`

이 문서가 추가로 권장하는 `numeric_literal_mismatch`, `numeric_semantic_review`는 기존 코드를 깨지 않도록 별도 확장 코드로 기록하거나 `detail.check="numeric"`로 namespace한다.

## 6. Repair 설계

### 6.1 원칙

- repair 입력에는 **해당 검증 round에서 실패한 cluster만** 포함한다.
- 통과한 cluster를 모델에 다시 보내거나 다시 쓰지 않는다.
- runner가 immutable 필드를 원래 패킷에서 채운다. 실패 응답의 손상된 원문·ID를 다음 prompt의 권위 자료로 재사용하지 않는다.
- 동일 cluster에 여러 오류가 있으면 한 repair 요청에 모두 제공한다.
- repair 결과도 전체 validator를 처음부터 다시 통과해야 한다. 해당 오류 하나만 사라졌다고 승인하지 않는다.
- repair merge는 `cluster_id` exact replacement이며 새 cluster·누락 cluster를 허용하지 않는다.
- round별 원본·입력·결과·검증 보고서 SHA-256을 남긴다.

### 6.2 오류 분류

| 분류 | 예 | 처리 |
|---|---|---|
| 전역 포맷 오류 | `invalid_json`, wrong packet ID | 같은 패킷 전체 1회 format retry. 조각 구조 복원 금지 |
| 항목 구조 오류 | 누락 필드, 미지/중복 cluster | 실패 cluster만 권위 입력에서 재구성 후 repair |
| 번역 불변조건 오류 | 토큰, 개행, byte cap, NUL, 일본어 잔여, 숫자 | 실패 cluster만 번역 repair |
| preserve 증거 오류 | `unproven_preserve` | 입력에 증거가 없으면 `translated`로 다시 번역; debug exact match면 `pending` |
| 문맥 충돌 | occurrence review required | 자동 cluster repair 금지; occurrence별 문맥 패킷으로 분기 |

### 6.3 Repair 입력 schema

```json
{
  "schema": "criminal-girls.bscr-compact-repair-packet.v2",
  "packet_id": "bscr_v2_0001",
  "repair_round": 1,
  "style_guide_sha256": "...",
  "glossary_sha256": "...",
  "entries": [
    {
      "cluster_id": "bscr2_c00001",
      "source_ja": "$0……\n……ありがとね。",
      "reference_en": "$0……\n……ありがとね。",
      "max_utf8_bytes": 33,
      "protected_tokens": ["$0"],
      "newline_signature": {"lf": 1, "cr": 0},
      "consumer_roles": ["message"],
      "context_samples": [],
      "previous_status": "translated",
      "previous_target_ko": "……고마워.",
      "errors": [
        {
          "code": "protected_token_mismatch",
          "expected": ["$0"],
          "actual": [],
          "detail": "토큰 $0 누락"
        }
      ]
    }
  ]
}
```

Repair 출력은 draft result와 같은 구조를 쓰되 schema만 `criminal-girls.bscr-compact-repair-result.v2`로 하고 `repair_round`를 추가한다. 입력 entries와 같은 길이·순서·cluster 집합만 허용한다.

### 6.4 Repair prompt 사양

runner는 고정된 `translation_prompt.md`, 스타일·용어집 hash, 다음 repair 지시, repair JSON만 모델에 준다.

```text
다음은 BSCR 한국어 초벌 번역 검증에 실패한 항목만 모은 repair 요청이다.
일본어 source_ja가 의미 원문이며 reference_en은 보조 자료다.

규칙:
1. entries에 있는 항목만 고쳐라. 새 항목을 추가하거나 순서를 바꾸지 마라.
2. cluster_id/source_ja/reference_en을 정확히 복사하라.
3. previous_target_ko를 최소 수정하는 것이 목표가 아니다. 의미와 문체를 지키며 모든 errors를 함께 해결한 완전한 target_ko를 다시 써라.
4. protected_tokens의 값·개수·중복·순서를 정확히 유지하라.
5. newline_signature의 LF/CR 개수를 정확히 유지하라.
6. UTF-8 bytes가 max_utf8_bytes 이하여야 한다.
7. NUL과 의도하지 않은 일본어 잔여를 넣지 마라.
8. 원문의 숫자·영숫자 코드·수량·층수·기계 효과를 보존하라.
9. preserve 근거가 입력에 없으면 preserve로 바꾸지 마라.
10. 해결할 수 없으면 pending + 빈 target_ko로 반환하되, 통과한 척하지 마라.

오직 criminal-girls.bscr-compact-repair-result.v2 JSON 객체 하나만 출력하라.
```

오류별 추가 힌트는 deterministic하게 붙인다.

- `protected_token_mismatch`: expected/actual을 보여 주고 exact sequence를 요구.
- `newline_mismatch`: expected LF/CR와 actual 수치를 명시.
- `utf8_byte_cap_exceeded`: actual bytes와 cap을 명시하고 의미를 유지한 압축을 요구.
- `japanese_residue_in_translation`: 검출 substring과 위치를 명시하고 한국어로 치환하도록 요구. 고유명사도 용어집 표기를 사용.
- `numeric_literal_mismatch`: source/target 수치 원자 sequence를 보여 주고 원문 값을 복원하도록 요구.
- `unproven_preserve`: 허용 증거가 없음을 명시하고 translated로 재작성. debug exact match라면 pending 유지.

### 6.5 재시도 상한과 격리

- format retry: 패킷당 최대 1회.
- 항목 repair: 기본 최대 3 round.
- 같은 error code가 3회 연속 남으면 자동 무한 반복을 중단하고 `manual_review_required` 큐로 보낸다.
- byte cap만 반복 실패하면 더 작은 묶음 또는 단일 cluster repair로 좁힌다.
- repair가 새로운 오류를 만들면 새 오류를 포함해 다음 round로 보내며 이전 통과 상태로 자동 rollback하지 않는다. 다만 모든 round를 보존해 검수자가 비교할 수 있게 한다.
- complete-map 승인은 수동 큐, pending, unproven preserve, validator error가 모두 0일 때만 가능하다.

## 7. 원자적 merge와 재개

- 각 결과는 임시 파일에 UTF-8로 쓰고 JSON parse·검증·SHA-256 계산 후 원자적으로 rename한다.
- packet 상태는 `not_started | raw_received | parsed | validated | repair_needed | passed | manual_review_required`로 journal에 기록한다.
- 재개 시 `passed` 결과의 hash를 다시 검증하고 일치하면 모델을 재호출하지 않는다.
- 같은 `cluster_id`를 여러 packet 결과가 소유하면 manifest 오류로 즉시 중단한다.
- merge 전 전체 cluster 집합이 manifest/draft_units와 exact-set 일치하는지 확인한다.
- fanout 뒤 occurrence UID 집합이 카탈로그 후보 exact-set과 일치해야 한다.

## 8. 완료 게이트와 보고 수치

초벌 완료를 선언하려면 다음이 모두 0이어야 한다.

- 누락·중복·미지 cluster
- 누락·중복·미지 occurrence UID
- `pending`
- 증거 없는 `preserve`
- 토큰·개행·NUL·UTF-8 cap·일본어 잔여 오류
- 숫자 literal 오류
- unresolved occurrence context conflict

보고서에는 최소한 다음을 기록한다.

- manifest와 style/glossary/prompt SHA-256
- packet/cluster/occurrence 총수
- 최초 통과 수, 오류 코드별 실패 수
- repair round별 입력·통과·잔여 수
- translated/preserve/pending 수
- 최대·평균 UTF-8 cap 사용률
- 일본어 잔여·숫자 경고 수
- manual review 수와 UID 목록
- 생성된 `translation_map.draft.jsonl` SHA-256

이 구조 검증 PASS는 번역 품질의 최종 승인과 동일하지 않다. 이후 통합 검수에서 인물 문체, 장면 연속성, 용어 일관성, 숫자의 의미 범위, 성적 표현 누락을 전체 지도 단위로 한 번 더 검수해야 한다.
