"""프로젝트 설정 - 경로·모델·추출/청킹/검색/에이전트 기본값을 모두 여기서만 바꾼다.

새 문서에 맞출 때 보통 바꾸는 것: CORPUS_DESCRIPTION, (필요하면) MARGIN·PARAGRAPH_*·CHUNK_*
분야(domain)는 data/<분야>/ 폴더 이름에서 자동으로 정해진다.
모델은 .env의 LLM_PROVIDER·EMBEDDING_PROVIDER와 모델 이름으로 바꾼다 (기본 Google Gemini).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

# ---------------- 경로 ----------------
DATA_DIR = BASE_DIR / "data"                  # data/<분야>/문서들 (+ data/ 바로 아래 골든셋 csv)
OUT_DIR = BASE_DIR / "output"
EXTRACT_DIR = OUT_DIR / "extracted"
JSONL_DIR = EXTRACT_DIR / "jsonl"             # 페이지별 추출 결과 (청킹 입력)
IMAGES_DIR = EXTRACT_DIR / "images"           # OCR한 이미지 영역 PNG
FIG_DIR = EXTRACT_DIR / "figures"             # Gemini로 변환한 그림 PNG + 결과
CHUNK_DIR = OUT_DIR / "chunks"
EVAL_DIR = OUT_DIR / "eval"
RUNS_DIR = OUT_DIR / "runs"
VECTORDB_DIR = BASE_DIR / "vectordb"

# ---------------- 모델 (.env로 덮어쓸 수 있음) ----------------
# provider: google_genai(기본) / openai / anthropic ... (LangChain init_chat_model·init_embeddings 이름)
# anthropic은 임베딩이 없으므로 EMBEDDING_PROVIDER는 google_genai·openai 등으로 둔다
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google_genai")
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "google_genai")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")          # 에이전트 답변
VISION_MODEL = os.getenv("VISION_MODEL", "gemini-3.6-flash")         # 차트·다이어그램 -> 마크다운
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-3.5-flash-lite")      # 평가 채점 (실험끼리 고정)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2")

# 에이전트 프롬프트에 들어가는 문서 설명
CORPUS_DESCRIPTION = "한국어 문서"  # 예: "금융·법률 분야 한국어 보고서와 판례"

# ---------------- 추출 ----------------
MARGIN = {"top": 0.06, "bottom": 0.07, "left": 0.03, "right": 0.03}  # 머리말·꼬리말·쪽번호 영역
MIN_IMAGE_AREA_RATIO = 0.10   # 페이지 면적 10% 넘는 이미지만 OCR/Gemini 대상
MIN_TABLE_TEXT_RATIO = 0.7    # 표로 읽은 글자가 표 영역 실제 글자의 70% 미만이면 깨진 표 -> 본문으로

# ---------------- 청킹 ----------------
CHUNK_SIZE, CHUNK_OVERLAP = 500, 60   # 300/50·500/60·800/100 비교에서 에이전트 정답률이 가장 높았던 값
PARAGRAPH_MODE = "auto"               # auto: 2단·글자 많은 PDF(논문)는 문단 단위 / none: 모두 길이 기준 / all: 모두 문단
PARAGRAPH_FILES: set[str] = set()     # auto 판정과 상관없이 문단 단위로 자를 파일명
PARAGRAPH_MIN_CHARS = 1500            # auto 판정: 쪽당 평균 글자 수 하한
MIN_CHUNK = 20                        # 이보다 짧은 조각은 버린다

# ---------------- 검색 ----------------
TOP_K = 5
FETCH_K = 20       # Hybrid에서 벡터·BM25 각각 가져올 후보 수
NEIGHBORS = 1      # 찾은 청크의 같은 쪽 앞뒤 청크를 몇 개씩 붙일지
RRF_C = 60

# ---------------- 에이전트 ----------------
MAX_SEARCHES = 3      # 최초 포함 최대 검색 횟수
PROMPT_VERSION = "p1"  # 프롬프트를 바꾸면 올린다 (평가 결과 폴더가 섞이지 않게)


def config_name(size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """청킹 설정 이름 = 청크 폴더·Chroma 컬렉션 이름"""
    return f"base_{size}_{overlap}"


DEFAULT_CONFIG = config_name()


def domains():
    """data/ 아래 하위 폴더 이름 = 분야 목록"""
    return sorted(p.name for p in DATA_DIR.iterdir() if p.is_dir()) if DATA_DIR.exists() else []
