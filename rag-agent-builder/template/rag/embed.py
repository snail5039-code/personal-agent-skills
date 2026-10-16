"""5. 임베딩: chunks.jsonl -> Chroma 벡터DB (청킹 설정마다 컬렉션을 따로, 이름 = 설정 이름)

- 임베딩 모델: config.EMBEDDING_PROVIDER/EMBEDDING_MODEL (기본 gemini-embedding-2), 코사인 거리
- 컬렉션 이름 = 청킹 설정 이름. 임베딩 모델을 바꾸면 vectordb/를 지우고 다시 만든다
- 이어서 실행: 저장된 것과 본문이 같은 청크는 건너뛰고, 새 청크·바뀐 청크만 임베딩, 없어진 청크는 지운다

실행
    python -m rag.embed                              # 기본 설정 (base_500_60)
    python -m rag.embed --config base_300_50
    python -m rag.embed --query "질문" --k 5          # 저장된 컬렉션으로 검색 확인
"""

import argparse
import time

from rag import config
from rag.common import embedding_model, read_jsonl

BATCH = 100


def get_store(collection):
    """임베딩 모델 + Chroma 컬렉션(코사인). retriever.py도 이걸로 연다"""
    import chromadb
    from langchain_chroma import Chroma
    client = chromadb.PersistentClient(path=str(config.VECTORDB_DIR))
    return Chroma(collection_name=collection, client=client, collection_metadata={"hnsw:space": "cosine"},
                  embedding_function=embedding_model())


def chroma_meta(c):
    # Chroma 메타데이터는 문자열·숫자·불리언만 된다 (None 불가)
    return {**{k: v for k, v in c["metadata"].items() if isinstance(v, (str, int, float, bool))}, "chunk_id": c["chunk_id"]}


def embed(name):
    chunks = read_jsonl(config.CHUNK_DIR / name / "chunks.jsonl")
    if not chunks:
        raise SystemExit(f"{name}/chunks.jsonl이 없습니다. 먼저 python -m rag.chunk 를 실행하세요.")
    store = get_store(name)
    saved = store.get(include=["documents"])
    existing = dict(zip(saved["ids"], saved["documents"]))
    todo = [c for c in chunks if existing.get(c["chunk_id"]) != c["text"]]
    todo_ids = {c["chunk_id"] for c in todo}
    new_ids = {c["chunk_id"] for c in chunks}
    stale = [cid for cid in existing if cid not in new_ids or cid in todo_ids]
    if stale:
        store.delete(ids=stale)
    print(f"청크 {len(chunks)} / 저장됨 {len(existing)} / 지움 {len(stale)} / 이번에 임베딩 {len(todo)}", flush=True)

    t0 = time.time()
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        for attempt in range(5):
            try:
                store.add_texts(texts=[c["text"] for c in batch], metadatas=[chroma_meta(c) for c in batch],
                                ids=[c["chunk_id"] for c in batch])
                break
            except Exception as e:  # 속도 제한 등 -> 쉬었다가 재시도
                if attempt == 4:
                    raise
                print(f"  재시도 {attempt + 1} ({10 * (attempt + 1)}초 대기): {repr(e)[:120]}", flush=True)
                time.sleep(10 * (attempt + 1))
        print(f"  {min(i + BATCH, len(todo))}/{len(todo)} ({time.time() - t0:.0f}초)", flush=True)
    print(f"컬렉션 '{name}': {store._collection.count()}개 -> {config.VECTORDB_DIR}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=config.DEFAULT_CONFIG)
    parser.add_argument("--query")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    if not args.query:
        return embed(args.config)
    for doc, dist in get_store(args.config).similarity_search_with_score(args.query, k=args.k):
        m = doc.metadata
        print(f"[{dist:.3f}] {m['file_name']} p.{m['page_no']} ({m['content_type']}) {m['chunk_id']}")
        print("   ", doc.page_content[:150].replace("\n", " "))


if __name__ == "__main__":
    main()
