"""여러 단계가 같이 쓰는 도구: JSONL 읽기/쓰기, 마크다운 표, LLM·임베딩 모델, 파일명 정규화"""

import json
import logging
import os
import re
import unicodedata
import warnings

from rag import config

# 결과와 상관없는 라이브러리 경고 끄기 (gemini-3.x temperature 안내, google-genai 로그)
warnings.filterwarnings("ignore", message=r"Model .* uses fixed sampling defaults", category=UserWarning)
logging.getLogger("google_genai").setLevel(logging.ERROR)


# ---------------- JSONL ----------------

def read_jsonl(path):
    """JSONL -> dict 목록. 깨진 줄(끊긴 마지막 줄 등)은 건너뛴다"""
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def append_jsonl(path, row):
    """한 줄 바로 저장 (중간에 끊겨도 앞의 결과는 남는다)"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl(path, rows):
    """통째로 다시 쓰기. tmp에 다 쓴 뒤 교체해서 중간에 끊겨도 원본이 깨지지 않게 한다"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def jsonl_files(only=None):
    """추출 JSONL 목록. only를 주면 파일명에 그 문자열이 들어간 것만"""
    return [f for f in sorted(config.JSONL_DIR.rglob("*.jsonl")) if not only or only in f.name]


def load_pages(jsonl_file):
    """추출 JSONL -> 페이지 dict 목록 (쪽 번호 순)"""
    return sorted(read_jsonl(jsonl_file), key=lambda r: r["page_no"])


# ---------------- 마크다운 표 ----------------

def markdown_row(values):
    return "| " + " | ".join(str(v).replace("|", r"\|") for v in values) + " |"


def markdown_table(headers, rows):
    return "\n".join([markdown_row(headers), markdown_row(["---"] * len(headers))] + [markdown_row(r) for r in rows])


def is_real_table(rows):
    """1행 또는 1열(1행 1열 포함)은 표가 아니라 안내 박스 등 일반 텍스트로 본다"""
    return len(rows) >= 2 and len(rows[0]) >= 2


# ---------------- 모델 ----------------

API_KEYS = {"google_genai": "GOOGLE_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def check_key(provider):
    key = API_KEYS.get(provider)
    if key and not os.getenv(key):
        raise SystemExit(f".env에 {key}가 없습니다 ({provider} 사용).")


def chat_model(model=None, max_retries=2):
    """채팅 모델 (config.LLM_PROVIDER). 속도 제한 429 등은 max_retries만큼 알아서 재시도"""
    from langchain.chat_models import init_chat_model
    check_key(config.LLM_PROVIDER)
    return init_chat_model(model or config.LLM_MODEL, model_provider=config.LLM_PROVIDER,
                           timeout=120, max_retries=max_retries)


def embedding_model():
    """임베딩 모델 (config.EMBEDDING_PROVIDER). 모델을 바꾸면 벡터DB를 다시 만들어야 한다"""
    from langchain.embeddings import init_embeddings
    check_key(config.EMBEDDING_PROVIDER)
    return init_embeddings(config.EMBEDDING_MODEL, provider=config.EMBEDDING_PROVIDER)


# ---------------- 기타 ----------------

def norm_name(name):
    """파일명 비교용: 유니코드 정규화, 확장자 제거, 공백 정리 (골든셋 파일명과 청크 파일명 맞추기)"""
    name = unicodedata.normalize("NFC", name or "").strip()
    return re.sub(r"\s+", " ", re.sub(r"\.[A-Za-z0-9]{2,5}$", "", name))
