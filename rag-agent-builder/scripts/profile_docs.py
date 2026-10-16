"""입력 문서 폴더를 훑어보고 RAG 파이프라인 계획에 필요한 특징을 보고한다 (파이프라인을 만들기 전 1단계).

보는 것
- 형식별 파일 수, 분야 폴더 구조, 골든셋 후보(csv)
- PDF: 쪽 수, 쪽당 글자 수, 스캔(글자 없는) 쪽, (cid) 깨진 글자, 2단 편집 쪽, 표, 큰 이미지, 벡터 그림이 많은 쪽
- 그 밖의 형식: 변환이 필요한지(LibreOffice), 이미지 파일 수
- 한글 비율 (BM25 형태소 분석기·임베딩 선택 참고)
결과: 터미널 + <out>/PROFILE.md (권장 단계·설정 포함)

실행 (pdfplumber만 있으면 된다)
    python profile_docs.py <문서 폴더> [--out <폴더>] [--max-pages 30]
"""

import argparse
import re
import shutil
import statistics
import sys
from collections import Counter
from pathlib import Path

IMAGE = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
NATIVE = {".pdf", ".docx", ".pptx", ".xlsx", ".xlsm", ".csv", ".html", ".htm", ".md", ".txt"} | IMAGE
CONVERT = {".hwp", ".hwpx", ".doc", ".ppt", ".xls", ".rtf", ".odt", ".odp", ".ods"}
HANGUL = re.compile(r"[가-힣]")
LETTER = re.compile(r"[가-힣A-Za-z]")


def two_columns(words, x0, x1):
    """가운데 30~70%에 걸치는 단어가 거의 없는 세로선이 있으면 2단"""
    if len(words) < 40:
        return False
    width = x1 - x0
    for i in range(int(width * 0.4 / 2) + 1):
        x = x0 + width * 0.3 + 2 * i
        if sum(1 for w in words if w["x0"] < x < w["x1"]) <= len(words) * 0.03:
            left = sum(1 for w in words if w["x1"] <= x)
            return min(left, len(words) - left) >= len(words) * 0.2
    return False


def profile_pdf(path, max_pages):
    import pdfplumber
    st = Counter()
    chars, text = [], []
    with pdfplumber.open(path) as pdf:
        st["pages"] = len(pdf.pages)
        step = max(1, len(pdf.pages) // max_pages)  # 큰 문서는 고르게 표본
        for page in pdf.pages[::step][:max_pages]:
            st["sampled"] += 1
            body = page.within_bbox((page.bbox[0], page.bbox[1] + page.height * 0.06,
                                     page.bbox[2], page.bbox[3] - page.height * 0.07))
            cs = [c for c in body.chars if c["text"].strip()]
            cid = sum(c["text"].startswith("(cid:") for c in cs)
            n = len(cs) - cid
            chars.append(n)
            area = page.width * page.height
            big = [im for im in page.images if (im["x1"] - im["x0"]) * (im["bottom"] - im["top"]) / area > 0.1]
            st["big_images"] += len(big)
            st["scan"] += n < 20 and (bool(big) or len(page.curves) + len(page.rects) > 100)
            st["broken_font"] += bool(cs) and cid / len(cs) > 0.3
            st["vector_heavy"] += n >= 20 and len(page.curves) > 200  # 선으로 그린 차트·도식 가능성
            st["tables"] += sum(1 for t in body.find_tables() if len(t.rows) >= 2 and len((t.extract() or [[]])[0]) >= 2)
            st["two_col"] += two_columns(body.extract_words(), body.bbox[0], body.bbox[2])
            text.append("".join(c["text"] for c in cs if not c["text"].startswith("(cid:")))
    st["avg_chars"] = int(statistics.mean(chars)) if chars else 0
    return st, "".join(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--out", help="PROFILE.md를 저장할 폴더 (기본: 문서 폴더)")
    parser.add_argument("--max-pages", type=int, default=30, help="PDF마다 표본으로 볼 최대 쪽 수")
    args = parser.parse_args()
    root = Path(args.folder).resolve()
    files = [p for p in sorted(root.rglob("*")) if p.is_file() and not p.name.startswith(".")]
    if not files:
        sys.exit(f"{root}에 파일이 없습니다.")

    by_suffix = Counter(p.suffix.lower() for p in files)
    domains = sorted({p.relative_to(root).parts[0] for p in files if len(p.relative_to(root).parts) > 1})
    golden = [p for p in files if p.suffix.lower() == ".csv" and p.parent == root]
    rows, all_text, totals = [], [], Counter()
    for p in files:
        if p.suffix.lower() != ".pdf":
            continue
        try:
            st, text = profile_pdf(p, args.max_pages)
        except Exception as e:
            rows.append(f"| {p.relative_to(root)} | 읽기 실패: {type(e).__name__} |||||||||")
            continue
        totals.update(st)
        all_text.append(text)
        paper = st["two_col"] >= st["sampled"] / 2 and st["avg_chars"] >= 1500
        rows.append(f"| {p.relative_to(root)} | {st['pages']} | {st['avg_chars']} | {st['scan']} | {st['broken_font']} "
                    f"| {st['two_col']} | {st['tables']} | {st['big_images']} | {st['vector_heavy']} | {'논문형' if paper else ''} |")
        totals["paper_docs"] += paper
    for p in files:
        if p.suffix.lower() in {".md", ".txt", ".html", ".htm"}:
            all_text.append(p.read_text(encoding="utf-8", errors="ignore")[:20000])
    joined = "".join(all_text)
    hangul = len(HANGUL.findall(joined)) / max(len(LETTER.findall(joined)), 1)

    # ---- 권장 사항 ----
    need_convert = sorted(s for s in by_suffix if s in CONVERT)
    unsupported = sorted(s for s in by_suffix if s and s not in NATIVE | CONVERT)
    n_image_files = sum(by_suffix[s] for s in IMAGE)
    recs = []
    if need_convert:
        ok = shutil.which("soffice") or Path("C:/Program Files/LibreOffice/program/soffice.exe").exists()
        recs.append(f"- {need_convert} 파일은 LibreOffice로 PDF 변환 후 추출 (설치 {'확인됨' if ok else '안 됨 -> 설치하거나 PDF로 저장 요청'})")
    if totals["scan"] or totals["broken_font"] or n_image_files or totals["big_images"]:
        recs.append(f"- OCR 단계 필요 (스캔 쪽 {totals['scan']}, 깨진 글자 쪽 {totals['broken_font']}, "
                    f"큰 이미지 {totals['big_images']}, 이미지 파일 {n_image_files}) -> rag.ocr")
    if totals["big_images"] or totals["vector_heavy"] or n_image_files:
        recs.append(f"- 그림 단계 권장 (큰 이미지 {totals['big_images']}, 벡터 그림 많은 쪽 {totals['vector_heavy']}) "
                    "-> 차트·도식에 답이 있으면 rag.figures (Vision 모델 비용 발생)")
    if not (totals["scan"] or totals["broken_font"] or n_image_files or totals["big_images"] or totals["vector_heavy"]):
        recs.append("- 글자·표만으로 충분: OCR·그림 단계는 빼고 requirements의 OCR 패키지도 설치하지 않는다")
    if totals["paper_docs"]:
        recs.append(f"- 2단·글자 많은 논문형 PDF {totals['paper_docs']}개 -> PARAGRAPH_MODE='auto'가 문단 단위로 자른다")
    if not domains:
        recs.append("- 분야 폴더가 없다: 분야가 섞여 있으면 data/<분야>/로 나누면 검색 domain 필터를 쓸 수 있다 (선택)")
    recs.append(f"- 한글 비율 {hangul:.0%}: " + ("Kiwi BM25 + 다국어 임베딩(기본) 그대로" if hangul >= 0.3
                                              else "영어 위주 -> BM25 토크나이저를 공백·소문자 기반으로 바꾸는 것 검토"))
    recs.append("- 골든셋: " + (f"후보 {[g.name for g in golden]} -> 열 형식 확인" if golden
                              else "없음 -> rag.make_golden으로 초안 생성 후 사람이 검수"))
    if unsupported:
        recs.append(f"- 지원하지 않는 형식(건너뜀): {unsupported}")

    md = ["# 입력 문서 프로파일", "", f"- 폴더: {root}", f"- 파일 {len(files)}개: " + ", ".join(f"{s or '(없음)'} {n}" for s, n in by_suffix.most_common()),
          f"- 분야 폴더: {domains or '없음'}", "", "## 권장 사항", "", *recs, ""]
    if rows:
        md += ["## PDF (표본 쪽 기준)", "", "| 파일 | 쪽 | 쪽당 글자 | 스캔 쪽 | 깨진 글자 쪽 | 2단 쪽 | 표 | 큰 이미지 | 벡터 그림 쪽 | 유형 |",
               "|---|---|---|---|---|---|---|---|---|---|", *rows, ""]
    out = Path(args.out or root) / "PROFILE.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:md.index("## 권장 사항") + len(recs) + 2]))
    print(f"\n상세: {out}")


if __name__ == "__main__":
    main()
