"""4. 청킹: 추출 JSONL -> chunks.jsonl (청크는 페이지를 넘지 않는다 -> 출처 쪽이 정확)

콘텐츠 종류별 규칙
- text      : 일반 문서는 RecursiveCharacterTextSplitter(size, overlap)
              문단 문서(2단 논문 등)는 문단 단위 (긴 문단은 소제목을 반복하며 자름) -> is_paragraph_doc()
- markdown  : md·txt 원문. 표는 행 단위, 나머지는 길이 기준 (content_type은 text로 저장)
- table     : 행 단위로 자르고 조각마다 헤더·각주 반복
- image_text: OCR/Gemini 텍스트. 안의 마크다운 표는 행 단위, 나머지는 길이 기준
- figure    : 그림 하나 = 한 청크, 길면 제목 줄을 반복하며 나눔
- 사진·로고("[이미지] ...")와 20자 미만 조각은 버린다

chunk_id = <분야>/<파일>/p<쪽 3자리>/c<순서 2자리>  (retriever가 앞뒤 청크를 찾을 때 이 형식을 쓴다)

실행
    python -m rag.chunk                          # 기본 500/60 -> output/chunks/base_500_60/
    python -m rag.chunk --size 300 --overlap 50  # 비교용 설정
"""

import argparse
import re
import statistics
from collections import Counter

from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag import config
from rag.common import jsonl_files, load_pages, markdown_row, markdown_table, write_jsonl

PAPER_MAX, PAPER_OVERLAP = 800, 100   # 문단이 이보다 길면 자른다
FIGURE_MAX = 1000                     # 그림 하나가 이보다 길면 나눈다

SENT_END = re.compile(r"[.?!。」”’)\]다요음함됨임]$")
HEADING = re.compile(r"^(\d{1,2}[.)]\s|\(\d{1,2}\)\s?|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.\s?|[가-하][.)]\s|[A-Z][.)]\s|[①-⑳]|Table \d|Fig\. ?\d)")
PAGE_NUM = re.compile(r"^[\d\s\-–|]+$")
HANGUL = re.compile(r"[가-힣]")


def splitter(size, overlap, **kw):
    return RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap, **kw)


# ---------------- 문단 (PARAGRAPH_FILES) ----------------

def join_lines(lines):
    """줄바꿈으로 끊긴 단어 잇기: 한글-한글은 붙이고, 영어 하이픈은 지우고, 나머지는 공백"""
    out = ""
    for line in (l.strip() for l in lines):
        if out and HANGUL.match(out[-1]) and HANGUL.match(line[:1] or " "):
            out += line
        elif out.endswith("-") and line[:1].isalpha():
            out = out[:-1] + line
        else:
            out = f"{out} {line}" if out else line
    return out


def split_paragraphs(text, drop_lines=frozenset()):
    """PDF 줄에는 들여쓰기 정보가 없어서 줄 길이로 문단 끝을 찾는다.
    - 그 페이지의 보통 줄 길이(상위 80%)보다 확연히 짧은 줄 = 문단 끝 / 번호·Table·Fig로 시작 = 새 문단
    - 쪽번호·러닝 타이틀(drop_lines)은 지운다 / 짧은 소제목은 다음 문단 앞에 붙인다
    """
    lines = [l for l in text.split("\n") if l.strip() and not PAGE_NUM.match(l.strip()) and l.strip() not in drop_lines]
    if not lines:
        return []
    lengths = sorted(len(l) for l in lines)
    typical = lengths[int(len(lengths) * 0.8) - 1] if len(lengths) >= 5 else lengths[-1]
    paras, cur = [], []
    for line in lines:
        if cur and HEADING.match(line.strip()):
            paras.append(cur)
            cur = []
        cur.append(line)
        if len(line) < typical * 0.75:
            paras.append(cur)
            cur = []
    paras += [cur] if cur else []

    merged, carry = [], ""
    for p in paras:
        t = join_lines(p)
        if len(p) == 1 and len(t) < 40 and not SENT_END.search(t):
            carry = f"{carry}\n{t}" if carry else t
        else:
            merged.append(f"{carry}\n{t}" if carry else t)
            carry = ""
    return merged + ([carry] if carry else [])


def running_lines(pages):
    """같은 파일에서 3쪽 이상 반복되는 짧은 줄 = 러닝 타이틀(학술지명·논문 제목 등)"""
    seen = Counter()
    for r in pages:
        seen.update({l.strip() for b in r["blocks"] if b["content_type"] == "text"
                     for l in b["text"].split("\n") if 0 < len(l.strip()) <= 80})
    return frozenset(l for l, n in seen.items() if n >= 3)


# ---------------- 표·마크다운·그림 ----------------

def split_table_rows(header_lines, row_lines, suffix, size):
    """행 사이에서만 자르고 조각마다 헤더(+각주)를 반복한다.
    헤더가 청크의 절반을 넘으면 그냥 길이로 자르고, 한 행이 청크보다 길면 그 행만 길이로 자른다."""
    render = lambda rows: "\n".join(header_lines + rows) + (f"\n\n{suffix}" if suffix else "")
    if len(render([])) > size // 2:
        return splitter(size, 0).split_text(render(row_lines))
    parts, cur = [], []
    for row in row_lines:
        if len(render([row])) > size:
            parts += [render(cur)] if cur else []
            cur = []
            parts += [render([p]) for p in splitter(size - len(render([])), 0).split_text(row)]
        elif cur and len(render(cur + [row])) > size:
            parts.append(render(cur))
            cur = [row]
        else:
            cur.append(row)
    return parts + [render(cur)] if cur or not parts else parts


def split_markdown(text, size, overlap):
    """OCR·Gemini 마크다운: 표 구간(| 로 시작하는 줄)은 행 단위, 나머지는 길이 기준"""
    pieces, buf, lines, i = [], [], text.split("\n"), 0
    flush = lambda: pieces.extend(splitter(size, overlap).split_text("\n".join(buf))) if buf else None
    while i < len(lines):
        if not lines[i].lstrip().startswith("|"):
            buf.append(lines[i])
            i += 1
            continue
        flush()
        buf = []
        table = []
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            table.append(lines[i])
            i += 1
        if len(table) >= 3 and set(table[1].replace("|", "").strip()) <= set("-: "):
            pieces += split_table_rows(table[:2], table[2:], "", size)
        else:
            pieces += splitter(size, overlap).split_text("\n".join(table))
    flush()
    return pieces


def split_figure(text, overlap):
    """짧으면 통째로, 길면 첫 줄(### [차트] 제목)을 조각마다 붙인다"""
    if len(text) <= FIGURE_MAX:
        return [text]
    title, _, body = text.partition("\n")
    if not title.startswith("#"):
        return split_markdown(text, FIGURE_MAX, overlap)
    return [f"{title}\n{p}" for p in split_markdown(body, FIGURE_MAX - len(title), overlap)]


# ---------------- 페이지 -> 청크 ----------------

def is_paragraph_doc(pages):
    """문단 단위로 자를 문서인가: config.PARAGRAPH_FILES에 있거나, auto면 PDF 쪽의 절반 이상이 2단이고
    쪽당 글자가 많은 문서(학술 논문 형태). 2단 논문은 길이로 자르면 문단 중간이 잘려 답이 흩어진다"""
    name = pages[0]["file_name"]
    if name in config.PARAGRAPH_FILES or config.PARAGRAPH_MODE == "all":
        return True
    if config.PARAGRAPH_MODE != "auto":
        return False
    text_pages = [p for p in pages if p["page_type"] in ("text", "mixed")]
    two_col = sum(p.get("columns") == 2 for p in text_pages)
    avg = sum(p["char_count"] for p in text_pages) / max(len(text_pages), 1)
    return bool(text_pages) and two_col >= len(text_pages) / 2 and avg >= config.PARAGRAPH_MIN_CHARS


def chunk_page(r, by_paragraph, size, overlap, drop_lines):
    """한 페이지 -> [(텍스트, content_type, 메타데이터)] (읽기 순서)"""
    out, text_buf = [], []
    para_splitter = splitter(PAPER_MAX, PAPER_OVERLAP, separators=["다. ", ". ", " ", ""], keep_separator="end")

    def flush_text():
        if not text_buf:
            return
        text = "\n".join(text_buf)
        text_buf.clear()
        if not by_paragraph:
            out.extend((p, "text", {"method": f"recursive_{size}_{overlap}"}) for p in splitter(size, overlap).split_text(text))
            return
        for para in split_paragraphs(text, drop_lines):
            if len(para) <= PAPER_MAX:
                out.append((para, "text", {"method": "paragraph"}))
                continue
            heading, _, body = para.rpartition("\n")  # 앞에 붙은 소제목은 조각마다 반복
            out.extend(((f"{heading}\n{p}" if heading else p), "text", {"method": "paragraph_split"})
                       for p in para_splitter.split_text(body))

    for b in r["blocks"]:
        ct = b["content_type"]
        if ct == "text":
            text_buf.append(b["text"])
            continue
        flush_text()  # 본문이 아닌 블록을 만나면 그 전까지의 본문을 먼저 자른다
        if ct == "markdown":
            out.extend((p, "text", {"method": "markdown"}) for p in split_markdown(b["text"], size, overlap))
        elif ct == "table":
            header = markdown_table(b["headers"], []).split("\n")
            out.extend((p, "table", {"table_id": b["table_id"], "method": "table_rows"})
                       for p in split_table_rows(header, [markdown_row(x) for x in b["rows"]], b.get("footnotes", ""), size))
        elif ct == "figure":
            out.extend((p, "figure", {"figure_kind": b["figure_kind"], "image_path": b["image_path"], "method": "figure"})
                       for p in split_figure(b["text"], overlap))
        elif ct == "image":
            text = b.get("text", "").strip()
            if not text or text.startswith("[이미지]"):
                continue  # 사진·로고·변환 안 된 이미지
            if by_paragraph and r["page_type"] == "scan":
                text_buf.append(text)  # 스캔 논문도 문단 단위로
                flush_text()
                continue
            out.extend((p, "image_text", {"image_path": b.get("image_path"), "method": "markdown",
                                          "source": "gemini" if b.get("vision_method") else "ocr"})
                       for p in split_markdown(text, size, overlap))
    flush_text()
    return [(t.strip(), ct, m) for t, ct, m in out if len(t.strip()) >= config.MIN_CHUNK]


def build(size, overlap):
    name = config.config_name(size, overlap)
    out_dir = config.CHUNK_DIR / name
    chunks = []
    for f in jsonl_files():
        pages = load_pages(f)
        p0 = pages[0]
        by_paragraph = is_paragraph_doc(pages)
        drop = running_lines(pages) if by_paragraph else frozenset()
        for r in pages:
            for i, (text, ct, meta) in enumerate(chunk_page(r, by_paragraph, size, overlap, drop)):
                chunks.append({
                    "chunk_id": f"{p0['domain']}/{f.stem}/p{r['page_no']:03d}/c{i:02d}",
                    "text": text,
                    "metadata": {"file_name": p0["file_name"], "domain": p0["domain"], "page_no": r["page_no"],
                                 "unit": r.get("unit", "page"), "page_type": r["page_type"], "content_type": ct,
                                 "doc_type": "paragraph" if by_paragraph else "general", **meta},
                })
    write_jsonl(out_dir / "chunks.jsonl", chunks)
    write_stats(out_dir, name, chunks)
    return out_dir, chunks


def write_stats(out_dir, name, chunks):
    """콘텐츠 종류·분야별 청크 수와 길이 + 파일별 청크 미리보기"""
    def row(label, items):
        ls = [len(c["text"]) for c in items]
        return (f"| {label} | {len(ls)} | {int(statistics.mean(ls))} | {int(statistics.median(ls))} | {min(ls)} | {max(ls)} |"
                if ls else f"| {label} | 0 | - | - | - | - |")

    header = ["| 구분 | 청크 수 | 평균 | 중앙값 | 최소 | 최대 |", "|---|---|---|---|---|---|"]
    md = [f"# 청킹 결과 - {name}", "", *header, row("전체", chunks), ""]
    for key, label in (("content_type", "콘텐츠 종류별"), ("domain", "분야별")):
        md += [f"## {label}", "", *header]
        md += [row(v, [c for c in chunks if c["metadata"][key] == v]) for v in sorted({c["metadata"][key] for c in chunks})]
        md.append("")
    (out_dir / "STATS.md").write_text("\n".join(md), encoding="utf-8")

    by_file = {}
    for c in chunks:
        by_file.setdefault(c["chunk_id"].rsplit("/", 2)[0], []).append(c)
    for key, items in by_file.items():
        path = out_dir / "preview" / f"{key}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n\n".join([f"# {items[0]['metadata']['file_name']} ({len(items)}개)"] + [
            f"---\n\n### `{c['chunk_id']}` {c['metadata']['content_type']} · {len(c['text'])}자\n\n{c['text']}"
            for c in items]), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=config.CHUNK_SIZE)
    parser.add_argument("--overlap", type=int, default=config.CHUNK_OVERLAP)
    args = parser.parse_args()
    out_dir, chunks = build(args.size, args.overlap)
    print(f"청크 {len(chunks)}개 -> {out_dir} (STATS.md, preview/)")


if __name__ == "__main__":
    main()
