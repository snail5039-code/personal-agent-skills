"""2. (선택) 이미지 OCR: 추출 단계가 표시한 이미지 영역(needs_vision)을 글자로 바꾼다.

스캔 PDF·이미지 파일·이미지 속 글자가 있는 문서에서만 실행한다 (INDEX.md의 스캔형·이미지 대기 수로 판단).
대상은 PDF(변환된 PDF 포함)와 이미지 파일 (render_path가 있는 문서).

- 엔진: RapidOCR + PP-OCRv5 한국어 모델 (CPU, onnxruntime, 모델은 처음 실행 때 자동 다운로드)
- 이미지 속 표: 레이아웃 모델(PP-DocLayoutV3)로 표 영역 -> 표 구조 모델(SLANet+)로 행·열 -> 마크다운 표
  (1행/1열이거나 데이터 칸이 절반 넘게 비면 구조 인식 실패로 보고 일반 OCR 텍스트로 둔다)
- 이미 PDF 글자로 읽힌 영역과 겹치는 글상자는 버린다 (배경 이미지 위 텍스트 중복 방지)
- 글자를 못 찾았거나 평균 신뢰도가 낮으면 needs_vision=True로 남긴다 -> figures.py에서 Gemini로

실행
    python -m rag.ocr                 # 이미 OCR한 블록은 건너뛴다
    python -m rag.ocr --only 파일명일부
"""

import argparse
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager

import numpy as np
import pdfplumber
from bs4 import BeautifulSoup

from rag import config
from rag.common import is_real_table, jsonl_files, load_pages, markdown_table, write_jsonl
from rag.extract import render_path, write_previews
from rag.extract.pdf import inside, layout_from_words, reading_key

DPI = 200
MIN_BOX_SCORE = 0.5     # 이보다 낮은 글상자는 버린다
LOW_QUALITY = 0.8       # 평균 신뢰도가 이보다 낮으면 Gemini 대상으로 남긴다
MIN_TABLE_SCORE = 0.5   # 레이아웃 모델의 표 신뢰도 하한
MIN_TABLE_FILL = 0.5    # 데이터 칸 중 채워진 비율 하한

_models = {}


# ---------------- 모델 (figures.py도 사용, 프로세스마다 한 번만 만든다) ----------------

def get_ocr():
    if "ocr" not in _models:
        from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
        logging.getLogger("RapidOCR").setLevel(logging.WARNING)
        _models["ocr"] = RapidOCR(params={
            "Rec.lang_type": LangRec.KOREAN, "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_type": ModelType.MOBILE,
            "Global.use_cls": False,  # 방향 분류기가 정방향 문단을 뒤집어 글자가 깨진다
            "Global.log_level": "warning",
        })
    return _models["ocr"]


def get_layout():
    if "layout" not in _models:
        from rapid_layout import RapidLayout
        from rapid_layout.utils.typings import ModelType, RapidLayoutInput
        _models["layout"] = RapidLayout(cfg=RapidLayoutInput(model_type=ModelType.PP_DOC_LAYOUTV3))
    return _models["layout"]


def get_table_model():
    if "table" not in _models:
        from rapid_table import RapidTable
        from rapid_table.utils.typings import ModelType, RapidTableInput
        _models["table"] = RapidTable(RapidTableInput(model_type=ModelType.SLANETPLUS, use_ocr=True))
    return _models["table"]


class ImagePage:
    """이미지 파일을 PDF 페이지처럼 다룬다 (좌표 = 픽셀, 72dpi로 본다. PDF 글자는 없다)"""

    def __init__(self, path):
        from PIL import Image
        self.image = Image.open(path).convert("RGB")
        self.width, self.height = self.image.size
        self.bbox, self.chars = (0, 0, self.width, self.height), []


@contextmanager
def open_pages(page_record):
    """추출 페이지 dict -> 렌더링할 페이지 목록 (PDF 페이지들 또는 이미지 한 장)"""
    path = render_path(page_record)
    if path.suffix.lower() == ".pdf":
        with pdfplumber.open(path) as pdf:
            yield pdf.pages
    else:
        yield [ImagePage(path)]


def render(page, bbox, dpi):
    """페이지 영역 -> RGB PIL 이미지 (dpi 기준 크기)"""
    if isinstance(page, ImagePage):
        crop = page.image.crop(tuple(int(v) for v in bbox))
        return crop.resize((max(1, round(crop.width * dpi / 72)), max(1, round(crop.height * dpi / 72))))
    return page.crop(bbox).to_image(resolution=dpi).original.convert("RGB")


# ---------------- 이미지 속 표 ----------------

def html_to_rows(html):
    """HTML 표 -> 2차원 리스트. rowspan/colspan 병합 칸은 같은 값으로 채운다"""
    grid = {}
    for r, tr in enumerate(BeautifulSoup(html, "html.parser").find_all("tr")):
        c = 0
        for cell in tr.find_all(["td", "th"]):
            while (r, c) in grid:
                c += 1
            text = " ".join(cell.get_text(" ").split())
            rs, cs = int(cell.get("rowspan", 1)), int(cell.get("colspan", 1))
            grid.update({(r + dr, c + dc): text for dr in range(rs) for dc in range(cs)})
            c += cs
    if not grid:
        return []
    n_rows, n_cols = max(r for r, _ in grid) + 1, max(c for _, c in grid) + 1
    return [[grid.get((r, c), "") for c in range(n_cols)] for r in range(n_rows)]


def find_image_tables(img, bbox, page_chars):
    """이미지 속 표를 행·열로 복원. 쓸 만한 표만 [{px_box, bbox, headers, rows, text}]"""
    scale = 72 / DPI
    lay = get_layout()(img)
    tables = []
    for box, name, score in zip(lay.boxes or [], lay.class_names or [], lay.scores or []):
        if name != "table" or score < MIN_TABLE_SCORE:
            continue
        x0, y0, x1, y1 = [max(0, int(v)) for v in box]
        pdf_box = (bbox[0] + x0 * scale, bbox[1] + y0 * scale, bbox[0] + x1 * scale, bbox[1] + y1 * scale)
        if sum(1 for c in page_chars if inside(c, pdf_box)) > 20:
            continue  # PDF 글자로 이미 읽힌 표
        crop = img[y0:y1, x0:x1]
        res = get_ocr()(crop) if crop.size else None
        if res is None or res.boxes is None or not res.txts:
            continue
        out = get_table_model()(crop, ocr_results=[(res.boxes, res.txts, res.scores)])
        rows = html_to_rows(out.pred_htmls[0]) if out.pred_htmls else []
        if not is_real_table(rows):
            continue
        cells = [c for row in rows[1:] for c in row]
        if sum(1 for c in cells if c) / len(cells) < MIN_TABLE_FILL:
            continue
        tables.append({"px_box": (x0, y0, x1, y1), "bbox": [round(v, 1) for v in pdf_box],
                       "headers": rows[0], "rows": rows[1:], "text": markdown_table(rows[0], rows[1:])})
    return tables


# ---------------- OCR ----------------

def ocr_region(page, bbox, png_path, page_chars):
    """영역 렌더링·저장 -> 표 복원 + OCR -> (읽기 순서 텍스트, 통계, 표 목록)"""
    image = render(page, bbox, DPI)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(png_path)
    img = np.array(image)

    tables = find_image_tables(img, bbox, page_chars)
    res = get_ocr()(img)
    scale = 72 / DPI
    words, dup = [], 0
    for box, txt, score in zip(res.boxes if res.boxes is not None else [], res.txts or [], res.scores or []):
        if score < MIN_BOX_SCORE or not txt.strip():
            continue
        xs, ys = box[:, 0], box[:, 1]
        cx, cy = xs.mean(), ys.mean()
        if any(t["px_box"][0] <= cx <= t["px_box"][2] and t["px_box"][1] <= cy <= t["px_box"][3] for t in tables):
            continue  # 표 셀로 이미 들어감
        wb = (bbox[0] + xs.min() * scale, bbox[1] + ys.min() * scale, bbox[0] + xs.max() * scale, bbox[1] + ys.max() * scale)
        if sum(1 for c in page_chars if inside(c, wb)) >= max(2, 0.5 * len(txt.replace(" ", ""))):
            dup += 1  # 이미 PDF 글자로 읽힌 영역
            continue
        words.append({"x0": wb[0], "top": wb[1], "x1": wb[2], "bottom": wb[3], "text": txt.strip(), "score": float(score)})

    # 2단 감지 -> 읽기 순서 정렬 -> 같은 줄 글상자 잇기
    layout = layout_from_words(words, bbox, min_words=10)
    key = lambda w: reading_key((w["x0"], w["top"], w["x1"], w["bottom"]), layout)
    lines = []
    for w in sorted(words, key=key):
        if lines:
            prev = lines[-1]
            overlap = min(prev["bottom"], w["bottom"]) - max(prev["top"], w["top"])
            height = min(prev["bottom"] - prev["top"], w["bottom"] - w["top"])
            if key(prev)[:2] == key(w)[:2] and height > 0 and overlap > 0.5 * height:
                prev["text"] += " " + w["text"]
                continue
        lines.append(dict(w))
    # 표를 원래 위치에 끼워 넣는다
    lines += [{"x0": t["bbox"][0], "top": t["bbox"][1], "x1": t["bbox"][2], "bottom": t["bbox"][3],
               "text": f"\n{t['text']}\n"} for t in tables]
    text = "\n".join(l["text"] for l in sorted(lines, key=key)).strip()

    stats = {"kept": len(words), "dup": dup, "tables": len(tables),
             "score": round(sum(w["score"] for w in words) / len(words), 3) if words else 0.0}
    for t in tables:
        del t["px_box"]
    return text, stats, tables


def process_file(jsonl_file):
    """jsonl 하나의 OCR 안 한 이미지 블록을 처리하고 파일을 다시 쓴다. (파일명, 처리 수)"""
    pages = load_pages(jsonl_file)
    done = 0
    if not pages[0].get("render_path"):
        return pages[0]["file_name"], 0
    with open_pages(pages[0]) as doc_pages:
        for r in pages:
            targets = [b for b in r["blocks"] if b["content_type"] == "image" and b.get("needs_vision")
                       and "ocr_method" not in b]
            if not targets:
                continue
            page = doc_pages[r["page_no"] - 1]
            page_chars = [c for c in page.chars if not c["text"].startswith("(cid:")]
            for b in targets:
                broken = b.get("full_page_reason") == "broken_font"
                png = config.IMAGES_DIR / r["domain"] / jsonl_file.stem / f"{b['image_id']}.png"
                text, stats, tables = ocr_region(page, tuple(b["bbox"]), png, [] if broken else page_chars)
                b.update(text=text, image_path=png.relative_to(config.EXTRACT_DIR).as_posix(),
                         ocr_method="rapidocr-ppocrv5-korean", ocr_stats=stats, ocr_tables=tables)
                # 표가 있거나 전부 기존 글자와 중복 -> 완료 / 글자 없음·신뢰도 낮음 -> Gemini 대상
                b["needs_vision"] = not (tables or (stats["kept"] == 0 and stats["dup"] > 0)) and (
                    stats["kept"] == 0 or stats["score"] < LOW_QUALITY)
                if broken:  # 깨진 글자로 만든 본문·표는 버리고 OCR 결과만 남긴다
                    r["blocks"] = [x for x in r["blocks"] if x["content_type"] == "image"]
                r["char_count"] = sum(len(x.get("text", "")) for x in r["blocks"])
                done += 1
    write_jsonl(jsonl_file, pages)
    return pages[0]["file_name"], done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    files = jsonl_files(args.only)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(process_file, f) for f in files]
        for i, fut in enumerate(as_completed(futures), start=1):
            name, done = fut.result()
            print(f"[{i}/{len(files)}] {name} - OCR {done}곳", flush=True)
    write_previews()


if __name__ == "__main__":
    main()
