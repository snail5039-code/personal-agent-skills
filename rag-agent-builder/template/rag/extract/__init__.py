"""1. 추출: data/ 아래 문서 -> 페이지(위치)별 JSONL + 미리보기 md

형식마다 추출기를 고르고(pdf.py / formats.py) 결과는 모두 같은 페이지 dict로 저장한다.
    {file_name, domain, source_path, render_path, total_pages, page_no, page_type, char_count, blocks:[...]}
    blocks: text / table(headers, rows, footnotes) / markdown / image(needs_vision) / figure
- 분야(domain) = data/<분야>/ 폴더 이름 (바로 아래 파일은 "all")
- render_path: 이미지 OCR·그림 찾기 때 렌더링할 원본 (PDF·변환된 PDF·이미지 파일). 없으면 그 단계 대상이 아니다
- 페이지마다 바로 저장 -> 끊겨도 다시 실행하면 이어서 / 한 페이지 실패는 page_type="error"로 남기고 계속

실행
    python -m rag.extract                # data/ 아래 지원 형식 전부
    python -m rag.extract --only 파일명일부
    python -m rag.extract --preview-only # 미리보기만 다시 만들기
"""

import argparse
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

from rag import config
from rag.common import append_jsonl, jsonl_files, load_pages, read_jsonl
from rag.extract import formats, pdf

SUPPORTED = {".pdf"} | set(formats.EXTRACTORS) | formats.CONVERT_SUFFIXES


def domain_of(path):
    parts = path.relative_to(config.DATA_DIR).parts
    return parts[0] if len(parts) > 1 else "all"


def jsonl_path_for(path):
    # Windows 경로 길이 제한 때문에 파일명은 80자로 자른다 (원래 이름은 file_name에 보관). 확장자가 달라도 겹치지 않게 붙인다
    return config.JSONL_DIR / domain_of(path) / f"{path.stem[:80]}{path.suffix.lower()}.jsonl"


def render_path(page):
    """OCR·그림 찾기 때 렌더링할 파일 (PDF 또는 이미지)"""
    return config.BASE_DIR / page["render_path"]


def pages_of(path, skip):
    """파일 하나 -> (전체 쪽수, 페이지 dict) 반복, render_path"""
    suffix = path.suffix.lower()
    if suffix in formats.CONVERT_SUFFIXES:
        converted = formats.convert_to_pdf(path)
        if converted:
            return pdf.extract_file(converted, skip), converted
        if suffix == ".hwpx":
            print(f"  [안내] LibreOffice가 없어 {path.name}은 본문 글자만 읽습니다 (표·이미지 제외)")
            pages = formats.hwpx_text_pages(path)
            return ((len(pages), p) for p in pages if p["page_no"] not in skip), None
        raise RuntimeError(f"{path.name}: LibreOffice(soffice)가 없어 변환할 수 없습니다. 설치하거나 PDF로 저장해 넣으세요.")
    if suffix == ".pdf":
        return pdf.extract_file(path, skip), path
    pages = formats.EXTRACTORS[suffix](path)
    return ((len(pages), p) for p in pages if p["page_no"] not in skip), path if suffix in formats.IMAGE_SUFFIXES else None


def extract_one(path):
    """(전체 쪽수, 새로 추출한 쪽수)"""
    out = jsonl_path_for(path)
    done = {r["page_no"] for r in read_jsonl(out)}
    pages, render = pages_of(path, done)
    meta = {"file_name": path.name, "domain": domain_of(path),
            "source_path": path.relative_to(config.BASE_DIR).as_posix(),
            "render_path": render.relative_to(config.BASE_DIR).as_posix() if render else None}
    total = new = 0
    for total, record in pages:
        append_jsonl(out, {**meta, "total_pages": total, **record})
        new += 1
    return total or len(done), new


def safe_extract(path):
    try:
        return extract_one(path), None
    except Exception as e:  # 파일 하나 실패로 전체가 멈추지 않게
        return (0, 0), f"{type(e).__name__}: {e}"


# ---------------- 미리보기 (ocr.py·figures.py도 끝나면 호출) ----------------

def render_block(b):
    ct = b["content_type"]
    if ct in ("text", "markdown"):
        return b["text"]
    if ct == "table":
        return f"**[표 {b['table_id']}]**\n\n{b['text']}"
    if ct == "figure":
        return f"> [그림 {b['figure_kind']} {b['figure_id']}] Gemini 변환\n\n{b['text']}"
    status = ("Vision" if b.get("vision_method") else "OCR 대기" if "ocr_method" not in b
              else "Vision 대기" if b.get("needs_vision") else "OCR")
    return f"> [이미지 {b['image_id']}] {status}\n\n{b['text']}".rstrip()


def write_previews():
    """파일별 미리보기 md + INDEX.md (사람이 추출 결과를 눈으로 확인하는 용도)"""
    index = ["# 추출 결과", "", "| 분야 | 파일 | 위치 | 텍스트형 | 혼합형 | 스캔형 | 표 | 이미지 대기 | 오류 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for f in jsonl_files():
        pages = load_pages(f)
        if not pages:
            continue
        p0 = pages[0]
        out = config.EXTRACT_DIR / "preview" / f.relative_to(config.JSONL_DIR).with_suffix(".md")
        out.parent.mkdir(parents=True, exist_ok=True)
        md = [f"# {p0['file_name']}", ""]
        for p in pages:
            md += ["---", "", f"## {p.get('unit', 'page')} {p['page_no']} `{p['page_type']}` ({p['char_count']}자)", ""]
            md += [f"> 추출 오류: {p['error']}", ""] if p.get("error") else []
            md += [x for b in p["blocks"] for x in (render_block(b), "")]
        out.write_text("\n".join(md), encoding="utf-8")

        count = lambda t: sum(p["page_type"] == t for p in pages)
        blocks = [b for p in pages for b in p["blocks"]]
        link = out.relative_to(config.EXTRACT_DIR).as_posix()
        index.append(f"| {p0['domain']} | [{p0['file_name']}](<{link}>) | {len(pages)} | {count('text')} | {count('mixed')} "
                     f"| {count('scan')} | {sum(b['content_type'] == 'table' for b in blocks)} "
                     f"| {sum(bool(b.get('needs_vision')) for b in blocks)} | {count('error')} |")
    (config.EXTRACT_DIR / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="파일명에 이 문자열이 들어간 것만")
    parser.add_argument("--preview-only", action="store_true")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = parser.parse_args()

    if not args.preview_only:
        # 골든셋 csv는 문서가 아니다 -> data/ 바로 아래 csv는 빼고, 분야 폴더 안 csv만 문서로 읽는다
        files = [p for p in sorted(config.DATA_DIR.rglob("*")) if p.is_file() and p.suffix.lower() in SUPPORTED
                 and not (p.parent == config.DATA_DIR and p.suffix.lower() == ".csv")
                 and (not args.only or args.only in p.name)]
        skipped = sorted({p.suffix for p in config.DATA_DIR.rglob("*") if p.is_file()} - SUPPORTED - {".csv", ""})
        if skipped:
            print(f"[안내] 지원하지 않는 형식은 건너뜀: {skipped}")
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(safe_extract, p): p for p in files}
            for i, fut in enumerate(as_completed(futures), start=1):
                (total, new), err = fut.result()
                status = f"실패 - {err}" if err else f"{total}개 위치 (새로 추출 {new})"
                print(f"[{i}/{len(files)}] {futures[fut].name} - {status}", flush=True)
    write_previews()
    print(f"미리보기: {config.EXTRACT_DIR / 'INDEX.md'}")
