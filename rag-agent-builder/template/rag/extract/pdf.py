"""PDF 추출 (pdfplumber): 글·표·이미지 후보 -> 페이지 dict

규칙
- 여백(config.MARGIN) 밖 글자는 버린다 -> 머리말·꼬리말·쪽번호 제거
- 표: find_tables() -> 마크다운 표 + 바로 아래 각주
    - 1행/1열은 가짜 표(안내 박스 등), 셀 글자가 표 영역 글자의 70% 미만이면 깨진 표 -> 둘 다 본문으로 읽는다
- 본문: 2단 편집을 감지해 구간마다 왼쪽 단 -> 오른쪽 단 순서로 읽는다
- 이미지: 페이지 면적 10% 초과만 OCR/Gemini 대상(needs_vision)으로 표시 (변환은 ocr.py·figures.py)
- 글자가 없거나 (cid)로 깨진 페이지는 페이지 전체를 이미지 대상으로 표시

extract_page() 흐름
  [1] 여백 자르기 + 중복 글자·(cid) 깨진 글자 제거
  [2] 표 (extract_tables)  [3] 표 밖 본문 (2단 감지)  [4] 큰 이미지
  [5] 읽기 순서 정렬, 이어진 본문 줄 합치기  [6] 글자 없는 페이지는 전체를 이미지 대상으로
"""

import logging

import pdfplumber

from rag import config
from rag.common import is_real_table, markdown_table

logging.getLogger("pdfminer").setLevel(logging.ERROR)  # 폰트 경고가 너무 많다

FOOTNOTE_PREFIXES = ("*", "※", "주:", "주)", "자료:", "출처:", "(주)")
FOOTNOTE_GAP = 25  # 표 하단에서 이 거리(pt) 안에서 시작하는 각주만 표에 붙인다


# ---------------- 위치·읽기 순서 (ocr.py도 사용) ----------------

def inside(obj, bbox):
    """글자(또는 박스)의 중심점이 bbox 안에 있는지"""
    cx, cy = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
    return bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]


def body_box(page):
    """여백을 뺀 본문 영역 (x0, top, x1, bottom)"""
    w, h, m = page.width, page.height, config.MARGIN
    return (page.bbox[0] + w * m["left"], page.bbox[1] + h * m["top"],
            page.bbox[2] - w * m["right"], page.bbox[3] - h * m["bottom"])


def layout_from_words(words, bbox, min_words=40):
    """2단 편집이면 {gutter: 단 경계 x, segments: [(top, bottom, "cols"|"full")]}, 1단이면 None.

    가운데 30~70% 구간에서 단어가 가장 적게 걸치는 세로선을 찾고, 걸치는 단어가 거의 없으면서
    양쪽에 글이 충분하면 2단으로 본다. 경계를 가로지르는 줄(제목 등)은 전체 폭 구간으로 따로 읽는다.
    words: x0, x1, top, bottom 키를 가진 dict 목록 (OCR 글상자에도 그대로 쓴다)
    """
    if len(words) < min_words:
        return None
    x_min, width = bbox[0], bbox[2] - bbox[0]
    candidates = [x_min + width * 0.30 + 2 * i for i in range(int(width * 0.40 / 2) + 1)]  # 2pt 간격
    gutter = min(candidates, key=lambda x: sum(1 for w in words if w["x0"] < x < w["x1"]))
    cross = sum(1 for w in words if w["x0"] < gutter < w["x1"])
    left = sum(1 for w in words if w["x1"] <= gutter)
    right = sum(1 for w in words if w["x0"] >= gutter)
    if cross > len(words) * 0.03 or min(left, right) < len(words) * 0.2:
        return None

    bands = []
    for w in sorted((w for w in words if w["x0"] < gutter < w["x1"]), key=lambda w: w["top"]):
        if bands and w["top"] <= bands[-1][1] + 2:
            bands[-1][1] = max(bands[-1][1], w["bottom"])
        else:
            bands.append([w["top"], w["bottom"]])
    segments, cursor = [], bbox[1]
    for top, bottom in bands:
        if top > cursor:
            segments.append((cursor, top, "cols"))
        segments.append((top, bottom, "full"))
        cursor = bottom
    segments.append((cursor, bbox[3], "cols"))
    return {"gutter": gutter, "segments": segments}


def reading_key(bbox, layout):
    """블록 정렬 키. 1단은 (위->아래, 왼->오), 2단은 (구간, 왼쪽 단 먼저, 위->아래)"""
    x0, top, x1, bottom = bbox
    if not layout:
        return (0, 0, round(top), x0)
    cy = (top + bottom) / 2
    segs = layout["segments"]
    idx = next((i for i, (s0, s1, _) in enumerate(segs) if s0 <= cy <= s1), len(segs) - 1)
    g = layout["gutter"]
    col = 0 if segs[idx][2] == "full" or x0 < g < x1 else int((x0 + x1) / 2 >= g)
    return (idx, col, round(top), x0)


def read_lines(page, layout):
    """1단은 그대로, 2단은 구간별로 왼쪽/오른쪽 단을 잘라서 줄 단위로 읽는다"""
    parts = [page]
    if layout:
        x_min, x_max, g = page.bbox[0], page.bbox[2], layout["gutter"]
        boxes = []
        for s0, s1, kind in layout["segments"]:
            boxes += [(x_min, s0, x_max, s1)] if kind == "full" else [(x_min, s0, g, s1), (g, s0, x_max, s1)]
        # 글자 중심점 기준으로 나눠서 경계에 걸친 글자가 두 번 읽히지 않게 한다
        parts = [page.filter(lambda o, b=b: o.get("object_type") != "char" or inside(o, b)) for b in boxes]
    return [l for p in parts for l in p.extract_text_lines(return_chars=False) if l["text"].strip()]


# ---------------- 표 ----------------

def clean_rows(raw_rows):
    """셀 정리(줄바꿈·연속 공백) + 빈 행·빈 열 제거"""
    rows = [[" ".join((c or "").split()) for c in row] for row in raw_rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    keep = [i for i in range(width) if any(r[i] for r in rows)]
    return [[r[i] for i in keep] for r in rows]


def fill_merged_first_col(rows):
    """병합된 첫 열(구분) 빈칸을 직전 값으로 채운다 -> 행 단위로 잘라도 구분이 남는다"""
    current = ""
    for r in rows:
        if r[0]:
            current = r[0]
        elif any(r[1:]):
            r[0] = current
    return rows


def find_footnotes(lines, table_bbox):
    """표 바로 아래에 이어지는 각주 줄"""
    notes, last_bottom = [], table_bbox[3]
    for line in sorted(lines, key=lambda l: l["top"]):
        if line["top"] < table_bbox[3] - 1:
            continue
        if line["top"] - last_bottom > FOOTNOTE_GAP or not line["text"].strip().startswith(FOOTNOTE_PREFIXES):
            break
        notes.append(line)
        last_bottom = line["bottom"]
    return notes


def extract_tables(body, page_no, all_lines):
    """진짜 표만 블록으로. 가짜·깨진 표는 영역으로 잡지 않아 글자가 본문으로 읽힌다"""
    blocks = []
    for t_idx, table in enumerate(body.find_tables(), start=1):
        rows = clean_rows(table.extract())
        if not is_real_table(rows):
            continue
        got = sum(len(c.replace(" ", "")) for r in rows for c in r)
        real = sum(1 for c in body.chars if inside(c, table.bbox) and c["text"].strip())
        if real and got / real < config.MIN_TABLE_TEXT_RATIO:
            continue
        headers, body_rows = rows[0], fill_merged_first_col(rows[1:])
        notes = find_footnotes(all_lines, table.bbox)
        footnotes = "\n".join(l["text"] for l in notes)
        blocks.append({
            "content_type": "table", "table_id": f"page-{page_no}-table-{t_idx}",
            "bbox": (*table.bbox[:3], max([table.bbox[3]] + [l["bottom"] for l in notes])),
            "headers": headers, "rows": body_rows, "footnotes": footnotes,
            "text": markdown_table(headers, body_rows) + (f"\n\n{footnotes}" if footnotes else ""),
        })
    return blocks


# ---------------- 페이지 ----------------

def image_block(image_id, bbox, area_ratio, **extra):
    return {"content_type": "image", "image_id": image_id, "bbox": bbox, "area_ratio": round(area_ratio, 3),
            "text": "", "needs_vision": True, **extra}


def extract_page(page, page_no):
    """한 페이지 -> {page_no, page_type, char_count, blocks}"""
    # [1] 여백 자르기 + 굵은 글씨 중복 글자 제거 + (cid:N) 깨진 글자 제거
    crop = body_box(page)
    body = page.within_bbox(crop).dedupe_chars()
    n_chars = len(body.chars)
    n_cid = sum(1 for c in body.chars if c["text"].startswith("(cid:"))
    body = body.filter(lambda o: o.get("object_type") != "char" or not o["text"].startswith("(cid:"))
    broken_font = n_chars > 0 and n_cid / n_chars > 0.3

    # [2] 표
    tables = extract_tables(body, page_no, body.extract_text_lines(return_chars=False))

    # [3] 표 밖 본문 (2단 감지)
    text_page = body.filter(lambda o: o.get("object_type") != "char"
                            or not any(inside(o, t["bbox"]) for t in tables))
    layout = layout_from_words(text_page.extract_words(), text_page.bbox)
    lines = [{"content_type": "text", "text": l["text"], "bbox": (l["x0"], l["top"], l["x1"], l["bottom"])}
             for l in read_lines(text_page, layout)]

    # [4] 큰 이미지 (스캔 이미지는 여백까지 걸쳐 있어 원본 페이지에서 찾고 여백 안쪽으로 자른다)
    page_area = page.width * page.height
    images = []
    for i, img in enumerate(page.images, start=1):
        bbox = (max(img["x0"], crop[0]), max(img["top"], crop[1]), min(img["x1"], crop[2]), min(img["bottom"], crop[3]))
        ratio = max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1]) / page_area
        if ratio > config.MIN_IMAGE_AREA_RATIO:
            images.append(image_block(f"page-{page_no}-image-{i}", bbox, ratio))

    # [5] 읽기 순서 정렬, 이어진 본문 줄은 한 블록으로
    blocks = []
    for b in sorted(lines + tables + images, key=lambda b: reading_key(b["bbox"], layout)):
        if blocks and b["content_type"] == blocks[-1]["content_type"] == "text":
            prev = blocks[-1]
            prev["text"] += "\n" + b["text"]
            prev["bbox"] = (min(prev["bbox"][0], b["bbox"][0]), min(prev["bbox"][1], b["bbox"][1]),
                            max(prev["bbox"][2], b["bbox"][2]), max(prev["bbox"][3], b["bbox"][3]))
        else:
            blocks.append(b)

    # [6] 글자가 없는데 큰 이미지도 없는 페이지 -> 페이지 전체를 이미지 대상으로
    #     (글자를 벡터 곡선으로 그림 / 작은 이미지 조각으로 쪼개짐 / 폰트가 깨짐)
    char_count = len(text_page.chars) + sum(len(t["text"]) for t in tables)
    vector_count = len(body.curves) + len(body.rects)
    tiles_ratio = sum(max(0, min(im["x1"], crop[2]) - max(im["x0"], crop[0]))
                      * max(0, min(im["bottom"], crop[3]) - max(im["top"], crop[1])) for im in page.images) / page_area
    if broken_font or (char_count < 20 and not images and (vector_count > 100 or tiles_ratio > 0.3)):
        reason = "broken_font" if broken_font else "vector_text" if vector_count > 100 else "image_tiles"
        blocks.append(image_block(f"page-{page_no}-image-full", crop, 1.0, full_page_reason=reason))
        images.append(blocks[-1])

    for i, b in enumerate(blocks):
        b["block_id"] = f"page-{page_no}-block-{i}"
        b["bbox"] = [round(v, 1) for v in b["bbox"]]
    page_type = ("scan" if images else "empty") if char_count < 20 else "mixed" if images else "text"
    return {"page_no": page_no, "page_type": page_type, "columns": 2 if layout else 1,
            "char_count": char_count, "blocks": blocks}


# ---------------- 파일 ----------------

def extract_file(path, skip):
    """PDF 하나 -> 페이지 dict (skip에 있는 쪽은 건너뛴다 -> 이어서 실행)"""
    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages)
        for page_no, page in enumerate(pdf.pages, start=1):
            if page_no not in skip:
                yield total, extract_page(page, page_no)
