"""검색기 - 에이전트와 평가가 같은 검색기를 쓰도록 한곳에 모았다.

검색 방식
- similarity: Chroma 벡터 검색
- mmr       : 벡터 후보 fetch_k개 중 다양성을 고려해 k개 (비교용)
- bm25      : Kiwi 형태소(조사·어미 제외) + BM25Okapi
- hybrid    : similarity·bm25 각각 fetch_k개를 RRF(Σ 1/(60+순위))로 합쳐 k개  <- 에이전트 기본

에이전트 검색 search() (practice 실패 분석으로 정한 기본값)
- Hybrid로 k개 (표 질문도 Hybrid: MMR은 같은 표의 행 청크를 하나만 가져와 표 정답률이 낮았다)
- domain을 주면 그 분야 결과에 전체 결과를 RRF로 섞는다 (분야를 잘못 고르면 정답률이 0.3까지 떨어졌다)
- 찾은 청크마다 같은 쪽의 앞뒤 청크를 붙인다 (쪽은 찾았는데 답이 적힌 옆 청크가 빠지는 문제)

실행
    python -m rag.retriever "질문" [--domain 분야] [--strategy hybrid]
"""

import argparse
import hashlib
import pickle
import time
from collections import defaultdict

from rank_bm25 import BM25Okapi

from rag import config
from rag.common import read_jsonl
from rag.embed import get_store

STRATEGIES = ("similarity", "mmr", "bm25", "hybrid")


class BM25Search:
    """Kiwi 형태소 + BM25. 형태소 분석 결과는 vectordb/bm25_<설정>.pkl에 저장해 두고 청크가 바뀌면 다시 만든다"""
    KEEP = ("NN", "NR", "NP", "VV", "VA", "XR", "SL", "SN", "SH", "MAG")

    def __init__(self, chunks, cache_path):
        from kiwipiepy import Kiwi
        self.kiwi, self.chunks = Kiwi(), chunks
        fingerprint = hashlib.sha1("".join(c["chunk_id"] + c["text"] for c in chunks).encode()).hexdigest()
        cache = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
        if cache.get("fingerprint") == fingerprint:
            corpus = cache["corpus"]
        else:
            t0 = time.time()
            corpus = [self.tokenize(c["text"]) for c in chunks]
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(pickle.dumps({"fingerprint": fingerprint, "corpus": corpus}))
            print(f"  BM25 색인 새로 만듦: {len(chunks)}개 ({time.time() - t0:.1f}초)")
        self.bm25 = BM25Okapi(corpus)

    def tokenize(self, text):
        return [t.form.lower() for t in self.kiwi.tokenize(text) if t.tag.startswith(self.KEEP)]

    def search(self, query, k, domain=None):
        scores = self.bm25.get_scores(self.tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [self.chunks[i] for i in order if not domain or self.chunks[i]["domain"] == domain][:k]


def rrf(*ranked_lists, top):
    """여러 순위 목록을 RRF로 합친다 (청크 dict에 chunk_id 필요)"""
    scores, items = defaultdict(float), {}
    for ranked in ranked_lists:
        for rank, c in enumerate(ranked, start=1):
            scores[c["chunk_id"]] += 1 / (config.RRF_C + rank)
            items[c["chunk_id"]] = c
    return [items[cid] for cid in sorted(scores, key=lambda x: -scores[x])[:top]]


def join_overlap(a, b, max_overlap=100):
    """이어진 두 청크를 합친다. 청킹 overlap으로 b 앞부분이 a 끝과 같으면 한 번만 쓴다"""
    for n in range(min(len(a), len(b), max_overlap), 0, -1):
        if a.endswith(b[:n]):
            return a + b[n:]
    return a + "\n" + b


class Retriever:
    def __init__(self, name=config.DEFAULT_CONFIG, k=config.TOP_K, fetch_k=config.FETCH_K,
                 neighbors=config.NEIGHBORS, domain_fallback=True):
        self.name, self.k, self.fetch_k = name, k, fetch_k
        self.neighbors, self.domain_fallback = neighbors, domain_fallback
        # 검색 결과로 넘기는 평평한 청크 dict
        self.rows = [{"chunk_id": c["chunk_id"], "text": c["text"],
                      **{k: c["metadata"][k] for k in ("file_name", "domain", "page_no", "content_type")}}
                     for c in read_jsonl(config.CHUNK_DIR / name / "chunks.jsonl")]
        if not self.rows:
            raise SystemExit(f"{name}/chunks.jsonl이 없습니다.")
        self.by_id = {r["chunk_id"]: r for r in self.rows}
        self.domains = sorted({r["domain"] for r in self.rows})
        self.store = get_store(name)
        self.bm25_index = BM25Search(self.rows, config.VECTORDB_DIR / f"bm25_{name}.pkl")

    # ---- 기본 검색 방식 ----
    def _rows(self, docs):
        return [self.by_id[d.metadata["chunk_id"]] for d in docs]

    def similarity(self, query, k, domain=None):
        return self._rows(self.store.similarity_search(query, k=k, filter={"domain": domain} if domain else None))

    def mmr(self, query, k, domain=None):
        return self._rows(self.store.max_marginal_relevance_search(
            query, k=k, fetch_k=self.fetch_k, filter={"domain": domain} if domain else None))

    def bm25(self, query, k, domain=None):
        return self.bm25_index.search(query, k, domain)

    def hybrid(self, query, k, domain=None):
        return rrf(self.similarity(query, self.fetch_k, domain), self.bm25(query, self.fetch_k, domain), top=k)

    # ---- 에이전트 검색 ----
    def with_neighbors(self, hits, n):
        """찾은 청크마다 같은 쪽 앞뒤 n개를 붙인다. 이어지는 구간은 한 덩어리로 합치고,
        덩어리 순서·chunk_id·출처는 그 안에서 순위가 가장 높은 청크를 따른다 (chunk_ids에 실제로 본 청크 전부)"""
        spans, best = defaultdict(set), {}
        for rank, hit in enumerate(hits):
            prefix, idx = hit["chunk_id"].rsplit("/c", 1)
            idx = int(idx)
            best.setdefault((prefix, idx), rank)
            spans[prefix].update(j for j in range(idx - n, idx + n + 1) if f"{prefix}/c{j:02d}" in self.by_id)
        blocks = []
        for prefix, nums in spans.items():
            nums = sorted(nums)
            runs = [[nums[0]]]
            for j in nums[1:]:
                if j == runs[-1][-1] + 1:
                    runs[-1].append(j)
                else:
                    runs.append([j])
            for run in runs:
                rank, top = min((best[(prefix, x)], x) for x in run if (prefix, x) in best)
                ids = [f"{prefix}/c{x:02d}" for x in run]
                text = self.by_id[ids[0]]["text"]
                for cid in ids[1:]:
                    text = join_overlap(text, self.by_id[cid]["text"])
                blocks.append((rank, {**self.by_id[f"{prefix}/c{top:02d}"], "text": text, "chunk_ids": ids}))
        return [b for _, b in sorted(blocks, key=lambda x: x[0])]

    def search(self, query, domain=None, k=None):
        k = k or self.k
        domain = domain if domain in self.domains else None
        hits = self.hybrid(query, k, domain)
        if domain and self.domain_fallback:
            hits = rrf(hits, self.hybrid(query, k), top=k)
        return self.with_neighbors(hits, self.neighbors) if self.neighbors else hits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--domain")
    parser.add_argument("--strategy", choices=("agent",) + STRATEGIES, default="agent")
    parser.add_argument("--k", type=int, default=config.TOP_K)
    args = parser.parse_args()
    r = Retriever(k=args.k)
    hits = (r.search(args.query, args.domain) if args.strategy == "agent"
            else getattr(r, args.strategy)(args.query, args.k, args.domain))
    for i, c in enumerate(hits, start=1):
        print(f"[{i}] {c['file_name']} p.{c['page_no']} ({c['content_type']}) {c['chunk_id']}")
        print("    ", c["text"][:150].replace("\n", " "))


if __name__ == "__main__":
    main()
