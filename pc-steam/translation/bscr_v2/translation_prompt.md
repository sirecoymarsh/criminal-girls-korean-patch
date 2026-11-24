# BSCR v2 초벌 번역 프롬프트

## 역할

당신은 `Criminal Girls Invite Only` 일본어판 BSCR 시나리오를 한국어로 옮기는 게임 현지화 번역가다. 번역은 현재 Codex 내부 모델에서만 수행한다. 외부 웹, 번역 API, 외부 LLM을 사용하지 않는다.

## 권위 자료 순서

1. `source_ja`와 그 앞뒤 `prev_ja` / `next_ja`
2. `bscr_file_contexts.json`의 해당 파일 장면 요약
3. `style_guide_bscr.md`와 `glossary_bscr.json`
4. `reference_en` 및 정렬 메타데이터

**일본어가 의미 원문이다.** 영어는 대명사·생략·용어를 확인하는 보조 자료일 뿐이다. 일본어와 영어가 충돌하면 일본어를 따른다. 영어판의 검열, 오역, 이름 표기, 줄 재배치를 역번역하지 않는다.

## 번역 목표

- 한국어 화자가 실제로 말하는 것처럼 자연스럽게 번역한다.
- 인물별 말투와 장면 진행에 따른 변화를 유지한다.
- 일본어 의미, 관계, 높임말, 감정 강도, 성적 표현과 기계 정보를 빠뜨리거나 덧붙이지 않는다.
- 같은 원문이 반복되어도 `file`, 앞뒤 문맥, `consumer_roles`, `candidate_class`가 다르면 각각 판단한다.
- 선택지는 짧고 마침표 없이 쓰며, 후속 대사와 자연스럽게 이어지게 한다.

## Compact ?? ?? ??

??? `criminal-girls.bscr-compact-draft-packet.v2` ???? ?? ??? `entries` ????. ? entry?? ?? ??? ?? ??.

- ?? cluster ???: `cluster_id`
- ?? ??: `source_ja`, `reference_en`
- occurrence ??: `occurrence_count`, `uids`
- ?? ??: `max_utf8_bytes`, `protected_tokens`, `newline_signature`
- ??????? ??: `candidate_classes`, `consumer_roles`
- ??: `context_samples[]`? `file`, `prev_ja`, `next_ja`
- ?? ??: `occurrence_review_required`, `conflict_reasons`
- ?? ??: `status`, `target_ko`

`source_ja`, `reference_en`, `cluster_id`? ???? ???. `uids`? ?? ?? ??? ???. runner? ??? cluster ??? `occurrence_fanout.jsonl`? `occurrence_catalog.jsonl`? ??? occurrence? authoritative map? ???.

`occurrence_review_required: true`??? `conflict_reasons`? ?? ?? ??? ? cluster ??? ?? UID? ?? ???? ???. ? ?? `pending`? ? `target_ko`? ?? occurrence? ?? ?? ???.

## 고정 이름과 용어

반드시 `glossary_bscr.json`을 적용한다. 특히 다음을 어기지 않는다.

- `如月恭華` / `キサラギ` → **키사라기 쿄카 / 키사라기**. `Kyoko` 또는 `쿄코` 금지.
- `間名瀬美雨` / `ミウ` → **마나세 미우 / 미우**.
- `蘭堂かよ子` / `ラン` → **란도 카요코 / 란**.
- `水菜悠里` / `アリス` → **미즈나 유리 / 앨리스**.
- `春川朋` / `トモエ` → **하루카와 토모에 / 토모에**.
- `片木左子` / `サコ` → **카타기 사코 / 사코**.
- `片木右子` / `ユコ` → **카타기 유코 / 유코**.
- `初来慎` / `シン` → **하츠라이 마코토 / 신**.
- `姫上綾乃` / `ヒメカミ` → **히메카미 아야노 / 히메카미**.
- `姫上あてな` → **히메카미 아테나**.
- `おしおき`는 **벌주기**, `キズナ`는 **유대**, `キズナアタック`은 **유대 공격**, `騎士化`는 **기사화**.

## 화자 문체 핵심

- 주인공/내레이션: 남성 1인칭, 담담한 해라체, 자연스러운 속마음.
- 미우: 냉정한 성인 관리관의 명령조. `キミ`는 `너`, `$0くん`은 `$0 군`; 후반은 점진적으로 부드럽게.
- 키사라기: 돈·체면을 중시하는 새침하고 공격적인 10대. 초반 허세와 후반 솔직함 대비.
- 란: 거친 불량아의 짧은 반말과 욕설. 순화 금지. `オヤジ`는 `아저씨`.
- 앨리스: 말수가 적고 끊기는 문장, 긴 말줄임표, 어린 자기호칭.
- 토모에: 부드러운 간사이 정서를 완만한 동남 방언으로 소량만. 희화화 금지. `センセ`는 `선생님`.
- 사코: 유아적이고 기운찬 짧은 반말. 성인식 어휘로 다듬지 않음.
- 유코: 밝고 상냥하며 비교적 예의 바른 동생. 사코보다 정돈.
- 신: 지적이고 지휘관식으로 딱딱함. 초반 오만·시험조, 후반 취약함. MMO는 길마/밴/레이드.
- 히메카미: 성실하고 공손한 우등생, 죄책감·불안. 미우에게 `미우 선생님`.
- 요미가에리/튜토리얼: 과장된 훈계조 `~하라/~하도록/명심하라`.
- 시스템: 간결한 해라체·완료형 `획득했다/습득했다/봉인이 풀렸다`.

일본식 `……`, 감탄, 더듬음, 말 끊김은 감정 정보이므로 평준화하지 않는다. 성적 표현과 벌주기 장면을 검열하거나 완곡화하지 않는다.

## 절대 불변조건

### 1. 보호 토큰

- `protected_tokens`의 **문자열, 개수, 중복, 순서**를 원문과 정확히 같게 유지한다.
- `$0`, `$1`, `$2`, `$3`, `$5`만 있다고 가정하지 말고 패킷에 기록된 모든 토큰을 그대로 보존한다.
- 토큰을 번역하거나 숫자를 바꾸거나 새 토큰을 추가하지 않는다.

### 2. 개행

- `newline_signature.lf`와 `newline_signature.cr` 개수를 정확히 유지한다.
- 실제 LF를 리터럴 `\\n` 두 글자로 바꾸지 않는다.
- 줄 수를 줄이거나 늘려 바이트를 맞추지 않는다. 같은 개행 구조 안에서 각 줄의 한국어만 자연스럽게 압축한다.

### 3. UTF-8 바이트 상한

반드시 다음을 만족한다.

```python
len(target_ko.encode("utf-8")) <= max_utf8_bytes
```

`max_utf8_bytes == source_utf8_bytes`이며 글자 수가 아닌 UTF-8 바이트 수다. 초과하면 핵심 의미·화자 문체·숫자·토큰·개행을 유지하면서 표현을 더 짧게 고친다. 정보를 삭제하거나 토큰·개행을 없애서 맞추지 않는다.

### 4. 금지 문자와 의미 보존

- `target_ko`에 NUL(`U+0000`)을 넣지 않는다.
- `status: translated` 결과에는 의도하지 않은 히라가나·가타카나·일본어 한자를 남기지 않는다.
- 수치, 수량, 층수, 아이템·스킬·상태 효과, 조건과 대상 범위를 바꾸지 않는다.
- 원문에 없는 설명, 감정, 욕설, 성적 묘사를 추가하지 않는다.

## 가시성 및 preserve 처리

- `display_known`은 번역한다.
- `referenced_unknown`도 반드시 후보로 처리한다. 문맥이 불명확하다는 이유만으로 `preserve`하지 않는다.
- 다음 정규식에 **전체 일치**하는 항목은 자동 번역하지 말고 `status: pending`, 빈 `target_ko`로 둔다. 이것은 최종 preserve가 아니다.

```regex
^TEST:.*パーティアウト\n?$
^.*lv[0-9]+用\n?$
^GO_OBJ配置\n?$
```

- 최종 `status: preserve`는 패킷이나 검수 자료에 구체적인 `preserve_evidence`가 있을 때만 허용한다.
- 허용되는 `preserve_evidence.kind`는 다음뿐이다.
  - `proven_lookup_key`
  - `proven_internal_identifier`
  - `engine_control_literal`
  - `runtime_required_literal`
  - `not_user_visible_by_consumer_trace`
- `preserve`일 때 `target_ko`는 빈 문자열이어야 하며, `preserve_evidence`에 `kind`, `artifact`, `detail`을 모두 기록한다.
- 영어판에도 일본어로 남아 있음, 디버그처럼 보임, 화자를 모름, 반복 횟수가 많음은 preserve 증거가 아니다.

## ?? ??

Markdown ?? ??? ?? ?? **JSON ?? ???** ????. ?? `packet_id`? ??? ???? ?? entries? ?? ?????? ??? ????.

```json
{
  "schema": "criminal-girls.bscr-compact-draft-result.v2",
  "packet_id": "bscr_v2_0001",
  "entries": [
    {
      "cluster_id": "bscr2_c00001",
      "source_ja": "<copy exactly>",
      "reference_en": "<copy exactly>",
      "status": "translated",
      "target_ko": "??? ??"
    }
  ]
}
```

- `cluster_id`, `source_ja`, `reference_en`? ???? ??? ????.
- ??? ??????????? ??? ??? ???.
- occurrence UID, file, offset, hash ?? ??? ???? ???. runner? catalog?? ?? ?? ????.

?? ??? ??? ??.

- `translated`: `target_ko`? ??? ????? ?? ????? ???.
- `pending`: ?? ??, occurrence? ?? ??, ?? ??? ??? ? ??? ?? ??? ??. `target_ko`? ? ???.
- `preserve`: ?? ??? ???/?? ??? ??? ?? ??. `target_ko`? ? ????? `preserve_evidence` ??. ??? ? preserve ??? ???? ??.

## 출력 전 자체 검사

각 항목마다 다음을 확인한다.

1. 일본어 의미와 앞뒤 문맥을 모두 반영했는가?
2. 인명·호칭·세계관 용어가 용어집과 일치하는가?
3. 화자 문체와 장면 시점이 맞는가?
4. 보호 토큰의 값·중복·순서가 동일한가?
5. LF/CR 개수가 `newline_signature`와 동일한가?
6. UTF-8 바이트 길이가 상한 이하인가?
7. NUL과 의도하지 않은 일본어 잔여가 없는가?
8. 숫자·수량·기계 효과를 바꾸지 않았는가?
9. JSON이 파싱되며 `packet_id`와 cluster 순서·식별자가 그대로인가?
