# Fides 1차 모델: CEN + SENN으로 ACCS 가중치 학습

시스템의 최종 산출물은 **Analysis Engine이 계산하는 0~100의 ACCS와 최종 판정**입니다. CEN+SENN으로 학습한 모듈은 **HES·TES·CES 가중치만 반환**합니다. Suspicious는 소비자가 추가로 확인해야 하는 상태로 유지하며, 학습에서 제외하거나 Washing으로 합치지 않습니다.

이번 수정본(v0.2.0)은 가중치 생성과 최종 결과 계산의 책임을 분리합니다.

| 단계 | 담당 | 입력 → 출력 |
|---|---|---|
| 근거 채점 | Analysis Engine | 수집 근거 → HES·TES·CES·ECS, 근거 품질 |
| 가중치 생성 | WeightPredictor | 채널 점수·근거 품질·제품군·마스크 → HES·TES·CES 가중치 |
| 최종 분석 | Analysis Engine | 점수 + 반환된 가중치 → ACCS·CONF·판정·설명·로그 |

서비스에서는 이미 학습한 모델을 불러와 가중치를 **추론**합니다. 요청마다 새로 학습하지 않습니다. SENN은 학습 시 가중치를 안정화하는 정규화 손실이며, 서비스에서 별도 판정을 내리는 두 번째 모델이 아닙니다.

기준 저장소: https://github.com/yejxjj/EASy

확인한 main 커밋: `424263d50e382c2df613015a78d6b0b58b3ef754` (2026-09-14).

## 1. 이번에 학습하는 것

기존 `analysis_engine.py`가 만든 HES·TES·CES는 고정된 개념 점수로 사용합니다. CEN이 제품군과 근거 품질을 받아 제품별 가중치를 학습하고, SENN 정규화가 작은 연속 입력 변화에 대한 민감도를 제한합니다.

```text
h = [HES, TES, CES] / 100
D = softmax(학습 가능한 4개 가중치 원형)
alpha = softmax(MLP(제품군, 채널별 근거 품질, 채널 존재 마스크))
w = normalize(mask * (alpha @ D))
evidence_score = 100 * sum(w * h)
ACCS = 0.85 * evidence_score + 0.15 * ECS
```

- `wH, wT, wC >= 0`, 사용 가능한 채널의 가중치 합은 1입니다.
- 근거가 없는 채널의 가중치는 0입니다. CSV에서 **관측된 0점**은 `mask=1`로 표현할 수 있으며, 결측과 다릅니다.
- ECS의 0.15는 현재 main의 고정 계수입니다. ECS는 가중치 생성기의 입력이 아닙니다. `--ecs-alpha 0`이면 HES·TES·CES 가중합 자체가 ACCS가 됩니다.
- CONF, 기존 ACCS, 기존 판정, 라벨 설명 `matched_patterns`, 제품명·URL·모델 ID는 가중치 생성기에 들어가지 않습니다.
- 모델의 반환값은 가중치·상태·모델 버전입니다. 소비자에게 제공할 ACCS·판정은 엔진 결과를 사용합니다. ACCS를 ‘진짜 AI일 확률’이라고 해석하지 않습니다.
- 원문/OCR로 점수 자체를 만드는 학습, ABMIL, 문장 임베딩 학습은 이번 단계에 포함하지 않습니다.

입력의 연속 근거 품질은 채널마다 5개입니다: 근거 개수/4, 출처 개수/3, 직접 관련성, 최신성, 한 출처에 대한 집중도. 앞 두 값은 1에서 상한 처리합니다. 제품군은 학습 집합에서만 vocabulary를 만들고, 처음 보는 제품군은 영벡터로 처리합니다. HES·TES·CES는 API에 전달하지만, 현재 gate는 점수 크기 자체를 읽지 않고 근거 품질·제품군·마스크로 가중치를 생성합니다.

## 2. ACCS 구간과 학습 목표

**아래 기본 경계값은 기준 커밋의 `fides_config.py`를 따른 값입니다. 과거에 사용했던 60점 기준과는 다릅니다.** 학습 설정은 체크포인트에 저장됩니다. 엔진 연결 시 ECS 혼합 계수와 세 경계값이 일치하는지 검사하며, 다르면 오류를 내어 서로 다른 점수 정의로 실행되는 것을 막습니다.

| ACCS 구간 | 학습/오프라인 평가 라벨 | 보조 구간 |
|---|---|---|
| 0 이상, 21.8 미만 | Washing | 워싱 위험 |
| 21.8 이상, 35 미만 | Suspicious | 추가 확인 권고 |
| 35 이상, 67.5 미만 | Genuine | 일반 신뢰 구간 |
| 67.5 이상 | Genuine | Credible |

이 표는 **학습과 오프라인 평가용 점수 구간**입니다. 서비스 최종 `verdict`는 기존 엔진의 주장 검출·근거 충분성·CONF 조건까지 적용합니다. 예를 들어 낮은 ACCS라도 CONF가 35 이상이면 엔진은 `Suspected`를 반환할 수 있고, AI 기능 주장이 없으면 `Not Evaluated`입니다. 데이터의 `Suspicious`와 엔진의 `Suspected`는 의심/추가 확인이라는 목적을 공유하지만, 점수 경계만으로 산출한 학습 라벨과 전체 엔진 판정은 구분합니다. 반환된 `AnalysisResult`를 모델 결과로 사후 덮어쓰지 않습니다.

현재 CSV에는 제품마다 전문가가 정한 정답 ACCS가 없습니다. 따라서 Genuine=100, Suspicious=50, Washing=0처럼 임의의 점수 정답을 만들지 않습니다. 대신 **순서형 손실(ordered logistic likelihood)**로 해당 라벨의 점수 구간을 학습합니다.

```text
a = (washing_cutoff - ACCS) / temperature
b = (genuine_cutoff - ACCS) / temperature
P(Washing)    = sigmoid(a)
P(Suspicious) = sigmoid(b) - sigmoid(a)
P(Genuine)   = 1 - sigmoid(b)
Lordinal = -log(P(관측 라벨))
```

위 P는 구간 학습을 위한 내부 likelihood이며, 보정된 소비자용 확률이 아닙니다. 오프라인 평가 라벨은 P의 argmax가 아니라 **ACCS에 경계값을 적용해** 정합니다. 세 라벨만으로 각 구간 안의 정확한 정답 점수까지 식별할 수는 없습니다.

**학습 중에는 ACCS 계산이 필요합니다.** 반환할 가중치가 정답 라벨에 맞는 점수를 만드는지 평가하고 역전파하기 위해서입니다. `fides_ml/objective.py`가 학습용 계산을 담당하고, 엔진과 함께 `fides_scoring.py`의 동일한 산식을 사용합니다. 서비스용 `WeightPredictor`와 `CENWeightModel`은 ACCS나 판정을 계산하지 않습니다.

SENN의 핵심 손실은 논문 식 (3)의 제곱형입니다. `u=[h,c]`, `f=sum(w(c)*h)`, `J_h=[I,0]`로 두고 아래 항을 계산합니다.

```text
Lsenn = ||gradient_u(f) - [w, 0]||²
L = Lordinal + lambda_senn*Lsenn
    + lambda_prior*KL(w || masked_prior)
    + lambda_weight_stability*Lweight_noise
```

이 모델에서는 gate가 h를 읽지 않으므로 `gradient_h(f)-w`만 계산하면 항상 0이 됩니다. 이를 피하기 위해 **context에 대한 미분도 포함**하고, `create_graph=True`로 정규화 손실까지 역전파합니다. 별도의 작은 근거 품질 노이즈에 대한 가중치 변화 손실은 스칼라 점수의 미분에서 상쇄되는 변화도 보조적으로 억제합니다. 이 노이즈 손실은 원 SENN 식과 구분되는 추가 보조항입니다.

범주형 제품군과 존재 마스크는 미분에서 고정합니다. 현재의 안정성 검증은 연속 근거 품질에 대한 것으로, 원문 문구 변경이나 제품군 변경에 대한 안정성을 보장하지 않습니다. 설명값은 실제 점수 계산 경로에 있지만 인과적 중요도를 뜻하지 않습니다.

## 3. 설치와 빠른 실행 확인

압축 파일의 `START_HERE.txt`에 적용 방법이 있습니다. 새로 추가되는 `fides_scoring.py`, `fides_ml/`, `requirements-ml.txt`, 테스트·문서와 함께 **수정된 `analysis_engine.py`, `fides_integration.py`도 적용**해야 합니다. 기존 프로젝트의 별도 수정 사항이 있다면 전체 파일 덮어쓰기보다 제공된 패치를 검토해 병합합니다. 학습·테스트만 할 때는 서버·크롤러를 실행할 필요가 없습니다.

Python 3.10 이상을 사용합니다. Windows/Anaconda에서도 EASy 루트에서 동일한 명령을 실행할 수 있습니다.

```bash
python -m pip install -r requirements-ml.txt
python -m unittest discover -s tests -p "test_fides_ml.py" -v

python -m fides_ml demo-data --output artifacts/demo_data.csv
python -m fides_ml train --data artifacts/demo_data.csv --output artifacts/demo_run --epochs 140
python -m fides_ml predict-weights --checkpoint artifacts/demo_run --data artifacts/demo_data.csv --output artifacts/demo_weights.csv
```

이 demo는 학습·저장·추론 검사용 **합성 데이터**입니다. 실제 제품 성능을 의미하지 않습니다. 이미 존재하는 실행 폴더를 덮어쓰지 않으므로 재실행 때는 `--output artifacts/demo_run_2`처럼 새 폴더를 사용합니다.

CPU로 실행할 수 있는 소형 모델입니다. CUDA 환경이 준비된 경우 `--device cuda` 또는 `--device auto`를 사용할 수 있습니다. CPU 설치와 CUDA 설치는 [PyTorch 공식 설치 안내](https://pytorch.org/get-started/locally/)를 따릅니다.

## 4. 실제 데이터 준비

확인한 `benchmark_dataset_labeled_strict_integrated_1286.csv`에는 다음 8개 열이 있습니다.

```text
domain, product_type, product_name, label, certainty, url, specs_text, matched_patterns
```

라벨은 Genuine 473, Suspicious 614, Washing 199건입니다. **HES·TES·CES·ECS 점수와 base_model_id/split_group은 이 CSV에 없습니다.** 이전 발표자료의 데이터 설명과 실제 파일 사이에 차이가 있으므로, 실제 파일을 기준으로 변환합니다.

기존 `pipeline_main.py`는 크롤링 근거를 `dataset/evidence_cache/*.json`에 다음 형식으로 저장합니다.

```json
{
  "url": "제품 URL",
  "bundle_kwargs": {
    "product_json": {},
    "norm_info": {},
    "db_results": [],
    "patent_items_df": [],
    "cert_results": []
  }
}
```

변환기는 이 캐시를 기존 온톨로지 엔진으로 다시 채점합니다. API 키, MySQL, Selenium, 외부 API 호출이 필요하지 않습니다. `ntis_result`, `iitp_result` 등 기존 adapter가 지원하는 다른 근거도 넘깁니다. 라벨은 CSV에서만 읽으며, 엔진이 낸 판정을 학습 정답으로 쓰지 않습니다.

**권장: 검토한 모델 계열 ID로 분할**

`dataset/model_groups.csv`는 아래처럼 URL별 그룹을 지정합니다. 용량·색상·판매처가 다른 동일 계열은 같은 ID를 줍니다. `base_model_id`와 `split_group` 중 하나만 있어도 됩니다.

```csv
url,base_model_id,split_group
https://example.invalid/product-a-256,family-a,family-a
https://example.invalid/product-a-512,family-a,family-a
https://example.invalid/product-b,family-b,family-b
```

```bash
python -m fides_ml prepare --labels dataset/benchmark_dataset_labeled_strict_integrated_1286.csv --cache-dir dataset/evidence_cache --groups dataset/model_groups.csv --output artifacts/train_features.csv
python -m fides_ml train --data artifacts/train_features.csv --output artifacts/cen_senn_run --mode cen_senn
```

그룹 정보를 생략하면 변환기는 `*.groups_to_review.csv`를 함께 만듭니다. 그룹 ID가 없는 상태에서는 학습을 시작하지 않습니다. 두 그룹 열에 서로 엇갈린 정보가 있어도 같은 모델 계열을 연결 요소로 묶어 분할 누수를 막습니다.

**그룹 ID가 아직 없을 때: 제품군 전체를 분리한 초기 실험**

```bash
python -m fides_ml prepare --labels dataset/benchmark_dataset_labeled_strict_integrated_1286.csv --cache-dir dataset/evidence_cache --group-column product_type --output artifacts/category_features.csv
python -m fides_ml train --data artifacts/category_features.csv --output artifacts/category_run
```

이는 모델 계열별 표준 평가 대신 **보지 못한 제품군에 대한 평가**입니다. 예를 들어 특정 제품군 전체가 test로 이동합니다. 표본 수가 큰 제품군 때문에 60/20/20 비율에서 벗어날 수 있으며 실제 분할 수를 저장합니다. 제품군 이름도 정규화해 같은 계열이 여러 제품군으로 잘못 분류되지 않았는지 확인해야 합니다.

**근거 캐시가 없는 환경에서 파이프라인 연결만 확인**

```bash
python -m fides_ml prepare --labels dataset/benchmark_dataset_labeled_strict_integrated_1286.csv --seller-only --group-column product_type --output artifacts/seller_only_features.csv
python -m fides_ml train --data artifacts/seller_only_features.csv --output artifacts/seller_only_run --epochs 40
```

`--seller-only`는 상품명·스펙·제공된 OCR만 사용합니다. 독립적인 외부 인증·특허 근거를 만들어 넣지 않습니다. 외부 근거를 포함한 전체 파이프라인의 평가 결과로 사용하면 안 됩니다. 다운로드한 main에는 근거 캐시가 포함되어 있지 않으므로, 실제 full-evidence 실험은 기존 실행 PC의 캐시를 사용해야 합니다.

**이미 분석 결과 JSON/JSONL을 저장했다면** `--cache-dir` 대신 `--results dataset/analysis_results.jsonl`을 사용합니다. 각 레코드는 `url`과 `AnalysisResult` 필드들을 포함하거나, `{"url": ..., "analysis_result": {...}}` 형식이어야 합니다. `details.channel_details`까지 필요합니다. 기존 `export_attention_features.py`의 축약 결과에는 이 정보가 충분하지 않을 수 있습니다.

## 5. 학습 옵션과 비교 실험

```bash
python -m fides_ml train --data artifacts/train_features.csv --output artifacts/run_global --mode global
python -m fides_ml train --data artifacts/train_features.csv --output artifacts/run_cen --mode cen
python -m fides_ml train --data artifacts/train_features.csv --output artifacts/run_cen_senn --mode cen_senn
```

| mode | 학습 내용 |
|---|---|
| fixed | 기존 0.35/0.40/0.25 고정 가중치, 학습 없이 평가 |
| global | 모든 제품에 공통인 3개 가중치 학습 |
| cen | 제품 맥락별 CEN 가중치 학습, SENN·노이즈 항 없음 |
| cen_senn | CEN + SENN + 보조 가중치 안정성 항 |

동일 파일과 seed를 쓰면 split이 같습니다. 각 실행에서 고정 가중치와 기존 근거 품질 기반 동적 가중치도 같은 ACCS 식·같은 test 데이터로 평가합니다. 기존 엔진 전체 verdict와 동일한 비교는 아니며 점수 경로에 대한 비교입니다.

경계값 변경 예시(숫자는 설정 예시이며 검증된 새 기준이 아님):

```bash
python -m fides_ml train --data artifacts/train_features.csv --output artifacts/custom_bands --washing-cutoff 30 --genuine-cutoff 60 --credible-cutoff 80
```

학습 전에 원하는 점수 의미와 경계값을 정합니다. test 결과를 보고 경계값을 반복 조정하지 않습니다. 클래스 불균형 보정은 train 라벨 비율만 사용하며 `--no-balanced`로 끌 수 있습니다. validation의 순서형 손실로 최적 epoch를 고르고 test는 최종 모델에만 사용합니다.

## 6. 실행 결과와 기존 코드 연결

| 파일 | 내용 |
|---|---|
| model.pt | 최적 validation 시점의 PyTorch state_dict |
| metadata.json | 모델·학습 설정, ACCS 경계값, 제품군 vocabulary |
| training_history.csv | epoch별 순서형·SENN·보조 손실 |
| metrics.json | 3개 라벨 macro-F1, balanced accuracy, 혼동행렬, 설명 안정성 |
| split_assignments.csv | 제품별 train/validation/test 및 그룹 ID |
| test_predictions.csv | 오프라인 진단용 ACCS, score_band_label, 가중치, 점수별 기여. 엔진 최종 verdict가 아님 |
| data_audit.json | 입력 해시, 라벨 수, 그룹 누수, 점수로 달성 불가능한 라벨 수 |

기존 분석 함수를 **호출할 때 predictor를 전달**합니다. 엔진이 HES·TES·CES를 만든 직후 가중치 모듈을 호출하고, 반환된 가중치로 최종 결과를 계산합니다. 실제 서비스에서는 predictor를 요청마다 다시 로드하지 말고 서버 시작 시 한 번 로드합니다.

```python
from fides_ml.predict import WeightPredictor
from fides_integration import secure_analyze_bundle

predictor = WeightPredictor("artifacts/cen_senn_run")

# bundle_kwargs: 기존 pipeline_main에서 구성하는 크롤링 결과
result = secure_analyze_bundle(
    **bundle_kwargs,
    weight_predictor=predictor,
    product_type=product_category,  # 학습 CSV와 같은 제품군 표기
)

print(result.accs)       # 최종 ACCS: 엔진에서 계산
print(result.conf)       # 기존 CONF: 엔진에서 계산
print(result.verdict)    # Washing / Suspected / Normal / Credible / Not Evaluated
print(result.details["dynamic_weighting"]["weights"])
print(result.details["dynamic_weighting"]["contributions"])
```

`product_type`을 생략하면 `product_json.category`, `product_json.product_type` 순서로 사용합니다. predictor를 전달하지 않으면 기존 근거 품질 기반 동적 가중치 경로로 실행됩니다. 기본 엔진 사용에는 PyTorch가 필요하지 않습니다. 기존 `pipeline_main.py`의 호출부는 위와 같이 predictor를 전달해야 학습 가중치가 활성화됩니다.

가중치 모듈만 직접 호출할 수도 있습니다. `channel_details`에는 채널별 근거 개수·출처 종류·직접성·최신성·집중도가 들어갑니다. 엔진이 이미 이 정보를 생성하므로 위 주입 방식에서는 별도로 만들 필요가 없습니다.

```python
weight_result = predictor.predict_weights(
    channel_scores={"hes": 40.0, "tes": 25.0, "ces": 20.0},
    channel_details=channel_details,
    product_type=product_category,
    channel_mask={"hes": True, "tes": True, "ces": True},
)
# {"weights": {"hes": ..., "tes": ..., "ces": ...},
#  "method": "cen_senn", "model_version": "sha256:...", "status": "ok"}
```

계산 예시: HES=40, TES=25, CES=20, ECS=10이고 반환된 가중치가 0.2/0.5/0.3이라면, **엔진이** 가중합 26.5와 ACCS **24.025**를 계산합니다. 기여도는 HES 6.8점 + TES 10.625점 + CES 5.1점 + ECS 1.5점입니다. 기본 점수 구간에서는 `Suspicious`이며, 최종 판정에는 주장 유무 등 엔진 조건도 적용됩니다. 이 숫자는 구조 설명용 가상 예시입니다.

모든 채널이 결측이면 가중치 모듈은 세 가중치 모두 0과 `status=no_usable_channels`를 반환합니다. 최종 결과 처리는 엔진에 맡깁니다. 예를 들어 아무 근거·주장이 없는 입력은 엔진의 기존 규칙에 따라 ACCS 0과 `Not Evaluated`가 됩니다. 학습에서는 모든 채널이 결측인 행 수와 ID를 따로 기록하고 목적함수에서 제외합니다.

CSV 가중치 추론은 `predict-weights` 명령을 사용합니다. `ecs`와 `label`은 필요하지 않으며, 식별 열 외에는 `weight_hes`, `weight_tes`, `weight_ces`, `status`, `method`, `model_version`만 저장합니다. 최종 ACCS를 얻으려면 엔진을 호출합니다.

### 기존 v0.1 코드에서 변경되는 부분

- `ACCSPredictor.predict_analysis(...)` 호출을 삭제하고 위 `WeightPredictor` 주입 방식으로 바꿉니다. 점수·판정을 사후 덮어쓰는 코드는 삭제합니다.
- 기존 CLI `predict`는 `predict-weights`로 바뀝니다. 출력 CSV에 ACCS·판정이 없으므로 이를 소비하던 코드는 엔진 결과를 사용하도록 수정합니다.
- 학습용 내부 클래스 `CENSENN`과 손실 함수는 `fides_ml.objective`로 이동했습니다. 서비스용 생성기는 `fides_ml.model.CENWeightModel`입니다.
- **v1 체크포인트의 파라미터 이름·크기는 그대로 유지했습니다. 구조 분리만을 위해 다시 학습할 필요는 없습니다.** `model.pt`와 `metadata.json`을 같은 폴더에 두면 새 predictor가 읽습니다. 기존 특징 정의와 점수 설정이 같아야 합니다. 새 학습 결과는 format_version 2로 저장합니다.
- 학습 가중치를 연결한 경우 `raw_accs`는 ECS 혼합 전의 학습 가중합입니다. 예전 점수는 `details.legacy_details`에 남습니다. 최종 점수·설명·로그는 엔진이 한 번에 생성합니다.

## 7. 해석할 때 반드시 알아야 하는 한계

**가중치만으로는 입력 점수의 범위를 벗어날 수 없습니다.** HES=80, TES=75, CES=85인 제품을 Washing으로 내려야 한다면, 양수 가중치 조정만으로 낮은 점수를 만들 수 없습니다. ECS 고정 혼합까지 포함해 이 한계를 행별로 검사하고 `data_audit.json`에 기록합니다. 이런 사례는 개념 점수 추출, 라벨 정의, ACCS 구간의 정합성을 확인해야 합니다.

HES·TES·CES가 동일하면 어떤 가중치라도 점수가 같습니다. 사용 가능한 채널이 하나뿐이면 그 채널 가중치는 1이며 학습할 자유도가 없습니다. 이런 경우 가중치의 유일한 정답을 주장할 수 없습니다. 근거 개념이 잘못되었는데 gate만 학습해서 전체 문제를 해결할 수도 없습니다.

현재 데이터는 제품군별 라벨 편중이 있으므로, 모델 계열 분할뿐 아니라 제품군 holdout도 함께 확인하는 것이 유용합니다. 사람이 검토하지 않은 초안 라벨에 대한 성능은 독립적으로 검증된 정답에 대한 성능과 구분해야 합니다.

## 8. 코드 위치와 근거

| 파일 | 역할 |
|---|---|
| analysis_engine.py | 가중치 모듈 호출 후 최종 ACCS·CONF·판정·설명·로그 생성 |
| fides_integration.py | secure_analyze_bundle에서 predictor를 엔진에 주입 |
| fides_scoring.py | 학습/엔진 공통 ACCS 산식, 가중치 검증. torch 의존성 없음 |
| fides_ml/model.py | CEN dictionary와 masked weights만 생성 |
| fides_ml/objective.py | 학습용 ACCS·ordinal 손실·SENN 정규화 |
| fides_ml/features.py | 채널 점수 단계 입력 및 기존 AnalysisResult adapter, 공통 feature 계약 |
| fides_ml/prepare.py | 캐시/기존 분석 결과/명시적 seller-only 변환 |
| fides_ml/data.py | 세 라벨 정규화, 모델 계열 연결, 그룹 분할 |
| fides_ml/train.py | 학습, validation 선택, 체크포인트·평가 저장 |
| fides_ml/evaluate.py | ACCS 구간 평가, baseline, 점수 도달 가능성 검사 |
| fides_ml/predict.py | 가중치만 반환하는 WeightPredictor, v1/v2 체크포인트 로드 |
| tests/test_fides_ml.py | 수치 미분, 누수 방지, 기존 엔진 연결, 저장·복원 테스트 |

이 구현은 논문의 모든 실험을 재현한 패키지가 아니라 **Fides의 고정 개념 점수와 ACCS 식에 맞춘 CEN+SENN 적용 구현**입니다. 순서형 점수 학습, 양수 가중치 제약, ECS 고정 혼합은 이 프로젝트에 맞춘 설계입니다.

- CEN: Al-Shedivat, Dubey, Xing, *Contextual Explanation Networks*, JMLR 21(194), 2020. https://jmlr.org/papers/v21/18-856.html
- SENN: Alvarez-Melis, Jaakkola, *Towards Robust Interpretability with Self-Explaining Neural Networks*, NeurIPS 2018, 식 (3). https://proceedings.neurips.cc/paper/2018/file/3e9f0fc9b2f89e043bc6233994dfcf76-Paper.pdf
- PyTorch 자동 미분: https://docs.pytorch.org/docs/stable/generated/torch.autograd.grad.html
- 안전한 state_dict 로드: https://docs.pytorch.org/docs/stable/generated/torch.load.html
- 기존 점수 식: `analysis_engine.py::_calculate_dynamic_weighting`, `fides_config.py::DynamicWeightConfig`.
