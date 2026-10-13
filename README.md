# SCI Papers Briefing Board

연구 주제를 정하면 관련 SCI 논문을 매일 자동으로 수집·분류해서 웹 보드로 보여주는 시스템입니다.

```
OpenAlex (논문 검색) ─▶ Claude (관련성 판정·소분류·Lab score·한 줄 요약)
        ─▶ data/papers.json (DOI 기준 누적) ─▶ site/ (GitHub Pages 웹 보드)
                     ▲ GitHub Actions가 매일 06:47 KST 자동 실행
```

## 폴더 구조

| 경로 | 역할 |
|---|---|
| `config.yaml` | **주제·검색식·소분류·저널 티어·연구실 관심사** — 주제를 바꿀 땐 이것만 수정 |
| `board/openalex.py` | OpenAlex에서 후보 논문 수집 |
| `board/classify.py` | Claude API로 분류 (관련성, 소분류 multi-label, Lab score, 요약) |
| `board/store.py` | 누적 저장소 (중복 없이 쌓임) |
| `board/run.py` | 실행 명령 모음 |
| `site/` | 정적 웹 보드 (통계, 연도 그래프, 필터 칩, 검색, 정렬, ★저장, 다크모드) |
| `.github/workflows/update.yml` | 매일 자동 실행 + 웹 배포 |

## 처음 설정 (약 20분)

### 1. API 키 두 개 발급
- **Claude API 키**: https://console.anthropic.com → API Keys (결제 수단 등록 필요)
- **OpenAlex API 키(무료)**: https://openalex.org 가입 → https://openalex.org/settings/api
  - 키 없이도 되지만 하루 한도가 매우 작아 백필이 중간에 막힐 수 있어요.

### 2. GitHub 저장소 만들기
1. GitHub에서 새 저장소 생성 (예: `papers-board`, Public 권장 — 무료 계정은 Private 저장소에서 Pages 불가)
2. 이 폴더 전체를 올리기
   ```bash
   cd paper-board
   git init && git add . && git commit -m "init"
   git branch -M main
   git remote add origin https://github.com/<아이디>/papers-board.git
   git push -u origin main
   ```
3. 저장소 **Settings → Secrets and variables → Actions → New repository secret**
   - `ANTHROPIC_API_KEY`
   - `OPENALEX_API_KEY`
4. **Settings → Pages → Build and deployment → Source: GitHub Actions**
5. **Settings → Actions → General → Workflow permissions: Read and write**

### 3. 주제 설정 — `config.yaml`
- `board.title` / `subtitle`: 보드 제목
- `queries`: 후보를 넓게 잡는 검색식. 조금 넓어도 괜찮아요 — Claude가 관련 없는 건 걸러냅니다.
- `categories`: 소분류. `description`이 Claude의 분류 기준이 되니 구체적으로 적으세요.
- `journal_tiers`: SCI 저널 화이트리스트와 티어. 저널명은 OpenAlex 표기와 맞아야 합니다
  (확인: `https://api.openalex.org/sources?search=저널이름`).
- `only_listed_journals`: `true`면 화이트리스트 저널만, `false`면 나머지는 "Other journals"로 표시.
- `lab_profile`: 연구실 관심사 — Lab score의 기준.

### 4. 먼저 로컬에서 소규모 테스트 (권장)
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
export OPENALEX_API_KEY=...
python -m board.run backfill --limit 30     # 검색어당 30편만
cd site && python -m http.server 8000        # http://localhost:8000
```
분류 결과가 괜찮으면 `data/`와 `site/data/`를 지우고 본 백필로 갑니다.

### 5. 백필 → 소분류 다듬기 → 자동 운영
1. GitHub **Actions 탭 → Update papers board → Run workflow → mode: backfill** (수십 분~1시간)
2. (선택) 소분류를 데이터에 맞게 다듬기:
   ```bash
   git pull
   python -m board.run suggest-categories      # Claude가 소분류 체계 초안을 YAML로 제안
   ```
   제안을 참고해 `config.yaml`의 `categories`를 고친 뒤 push → Actions에서 **mode: reclassify** 실행
3. 이후로는 매일 06:47(KST) 자동 실행. 월요일엔 인용수도 갱신됩니다.
4. 보드 주소: `https://<아이디>.github.io/papers-board/`

## 명령어

| 명령 | 설명 |
|---|---|
| `python -m board.run backfill` | `start_year`부터 전체 수집·분류 (최초 1회) |
| `python -m board.run daily` | 최근 `daily_lookback_days`일 출판분 중 신규만 추가 |
| `python -m board.run refresh-citations` | 전체 논문 인용수 갱신 |
| `python -m board.run reclassify` | 관련 논문 재분류 (소분류 변경 후). `--all`은 탈락 논문까지 |
| `python -m board.run suggest-categories` | 소분류 체계 초안 제안 |
| `python -m board.run build` | 웹 데이터만 재생성 (저널 티어만 바꿨을 때 — API 호출 없음) |

## 보드 기능
- **Papers shown / Relevant found / Citations / New this week** 통계
- 연도별 막대그래프 (클릭 → 해당 연도만)
- 소분류·저널 티어·Other journals·New·Reviews·★Saved 칩 — 여러 칩을 조합하면 AND 필터, 숫자는 다른 필터를 반영해 갱신
- 검색 (제목·초록·요약·저자·저널·DOI), Lab score / 인용수 / 최신순 정렬
- 논문 카드: 한 줄 요약, 소분류 태그(클릭 시 해당 분류로 이동), 초록 펼치기, Lab score 70+ 강조
- ★ 저장과 다크모드는 각자 브라우저에 저장됩니다 (연구실 공용 저장이 아님)

## 비용 감각
- 분류는 기본 `claude-haiku-5-5` (저렴·빠름). 논문 10편을 한 번에 보내고 공통 지시문은 프롬프트 캐싱을 적용합니다.
- 백필은 후보 수천 편을 한 번 분류하는 게 비용의 대부분이고, 이후 매일은 신규 수십 편 수준이라 미미합니다.
- 이미 분류한 논문은 다시 분류하지 않습니다 (`reclassify` 할 때만).
- 정확한 단가는 Anthropic 가격 페이지를 확인하세요. 처음엔 Console에서 월 사용 한도를 걸어두는 걸 권장합니다.

## 문제 해결
- **Actions에서 push 실패** → 5번 설정(Workflow permissions: Read and write) 확인
- **Pages 배포 실패** → Settings → Pages Source가 "GitHub Actions"인지 확인
- **특정 저널이 Other로 나옴** → OpenAlex 저널명이 다름. `aliases`에 OpenAlex 표기를 추가하고 `build` 실행
- **엉뚱한 논문이 많음** → `categories`/`lab_profile` 설명을 구체화하거나, `classify.py`의 관련성 기준 문장에 제외 예시를 추가
- **60일 동안 저장소 활동이 없으면** GitHub가 예약 실행을 멈춥니다 — 매일 커밋되므로 보통 문제 없지만, 멈췄다면 Actions 탭에서 다시 켜세요
