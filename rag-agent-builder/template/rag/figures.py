"""3. (선택) 그림 -> 마크다운: 차트·다이어그램·깨진 이미지 표·OCR 실패 영역을 Gemini로 변환한다.

차트·도식에 답이 있는 문서에서만 실행한다. ocr.py를 먼저 돌리면 OCR 실패 영역도 함께 처리한다.

단계 (기본은 셋 다 순서대로)
- find   : 페이지를 렌더링해 레이아웃 모델로 영역 분류 -> 대상 고르기 -> PNG + targets.jsonl
           chart는 모두 / image는 글자 상자 4개 이상이면 diagram(아니면 사진·로고라 제외)
           table은 PDF 글자로 읽히지 않았고 OCR 표 복원도 실패한 것만 / OCR 실패 블록은 통째로
- convert: 종류별 프롬프트 + PNG -> Gemini -> results.jsonl (끊겨도 이어서)
- merge  : OCR 실패 블록은 text 교체, 나머지는 figure 블록으로 읽기 순서 위치에 삽입 (여러 번 해도 결과 같음)

실행
    python -m rag.figures                    # find -> convert -> merge
    python -m rag.figures --limit 5          # 5개만 변환해서 품질 확인
    python -m rag.figures --steps merge      # 저장된 결과로 반영만
"""

import argparse
import base64
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

import numpy as np

from rag import config
from rag.common import append_jsonl, chat_model, jsonl_files, load_pages, read_jsonl, write_jsonl
from rag.extract import write_previews
from rag.extract.pdf import body_box, inside
from rag.ocr import get_layout, get_ocr, open_pages, render

TARGETS = config.FIG_DIR / "targets.jsonl"
RESULTS = config.FIG_DIR / "results.jsonl"
LAYOUT_DPI, CROP_DPI = 150, 200
MIN_SCORE = 0.5
MIN_AREA = 0.02          # 페이지 면적 2% 미만(아이콘 등) 제외
MIN_DIAGRAM_TEXT = 4     # image 영역 안 글자 상자가 이보다 적으면 사진·로고

COMMON = """첨부한 이미지는 한국어 문서(PDF)의 한 영역입니다. RAG 검색용 마크다운으로 변환하세요.
- 이미지에 적힌 글자는 그대로 옮기고, 요약하거나 생략하지 마세요.
- 이미지에 없는 내용을 추측해서 덧붙이지 마세요. 읽을 수 없는 부분은 [확인 불가]로 표시하세요.
- 결과 전체를 코드 블록으로 감싸지 마세요.
"""
CHART = ("`### [차트] 제목` 첫 줄, 단위·축·범례를 적고 값은 마크다운 표(가로축 항목=행, 계열=열). "
         "데이터 라벨 값은 그대로, 눈금으로 어림한 값은 (추정). 마지막 줄 `요약:` 추세·핵심 비교 1~2문장.")
DIAGRAM = ("`### [다이어그램] 제목` 첫 줄, 박스 글자를 빠짐없이. 화살표 관계는 `A → B`, 계층은 들여쓰기 목록, "
           "순서가 있으면 그 순서대로. 마지막 줄 `요약:` 구조를 한 문장으로.")
TABLE = "`### [표] 제목` 첫 줄, 마크다운 표. 병합 셀은 해당 칸마다 값 반복. 수치·단위·각주(*, ※, 주:, 자료:) 보존."
PROMPTS = {
    "chart": COMMON + "- 차트입니다. " + CHART,
    "diagram": COMMON + "- 다이어그램입니다. " + DIAGRAM,
    "table": COMMON + "- 표입니다. " + TABLE,
    "ocr_failed": COMMON + "- 먼저 종류를 판단하세요. 사진·로고·장식이면 `[이미지] 한 줄 설명`만.\n"
                  f"- 차트: {CHART}\n- 다이어그램: {DIAGRAM}\n- 표: {TABLE}\n"
                  "- 글(문단)이면 제목과 본문을 읽기 순서대로 그대로. 여러 종류가 섞이면 위에서 아래로 각각.",
}
PROMPTS = {k: v + "\n- 제목이 없으면 내용을 보고 짧게 붙이고 끝에 (제목 없음)을 표시하세요." for k, v in PROMPTS.items()}


# ---------------- find ----------------

def overlap_ratio(a, b, mode="iou"):
    """iou: 교집합/합집합, inner: 교집합/a 면적"""
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = lambda r: max(0, r[2] - r[0]) * max(0, r[3] - r[1])
    return inter / ((area(a) + area(b) - inter) if mode == "iou" else area(a)) if inter else 0.0


def table_is_broken(t):
    """OCR로 복원한 표인데 데이터 행에서 통째로 빈 열이 있으면 구조가 깨진 것"""
    return not t["rows"] or any(all(not row[c] for row in t["rows"]) for c in range(len(t["headers"])))


def classify(region, name, img_crop, chars, image_blocks):
    """레이아웃 영역 하나 -> chart / diagram / table / None(제외)"""
    if name == "chart":
        return "chart"
    n_chars = sum(1 for c in chars if inside(c, region))
    if name == "table":
        if n_chars > 20:
            return None  # PDF 글자로 읽힌 표 (extract.py가 처리)
        match = [t for b in image_blocks for t in b.get("ocr_tables", []) if overlap_ratio(region, t["bbox"]) > 0.5]
        return "table" if not match or any(table_is_broken(t) for t in match) else None
    res = get_ocr()(img_crop, use_rec=False) if img_crop.size else None
    n_text = len(res.boxes) if res is not None and res.boxes is not None else 0
    return "diagram" if max(n_text, n_chars // 5) >= MIN_DIAGRAM_TEXT else None


def find_in_file(jsonl_file):
    """jsonl 하나의 모든 페이지에서 Gemini 대상을 찾는다"""
    pages = load_pages(jsonl_file)
    targets = []
    if not pages[0].get("render_path"):
        return pages[0]["file_name"], targets
    with open_pages(pages[0]) as doc_pages:
        for r in pages:
            if r["page_type"] in ("empty", "error"):
                continue
            page = doc_pages[r["page_no"] - 1]
            chars = [c for c in page.chars if not c["text"].startswith("(cid:")]
            image_blocks = [b for b in r["blocks"] if b["content_type"] == "image"]
            # OCR 실패 블록은 통째로 (PNG는 ocr.py가 저장)
            found = [{"kind": "ocr_failed", "bbox": b["bbox"], "image_path": b["image_path"], "block_id": b["block_id"]}
                     for b in image_blocks if b.get("needs_vision") and b.get("image_path")]

            box = body_box(page)
            img = np.array(render(page, box, LAYOUT_DPI))
            scale = 72 / LAYOUT_DPI
            lay = get_layout()(img)
            for px, name, score in zip(lay.boxes or [], lay.class_names or [], lay.scores or []):
                if name not in ("chart", "image", "table") or score < MIN_SCORE:
                    continue
                region = [round(box[0] + px[0] * scale, 1), round(box[1] + px[1] * scale, 1),
                          round(box[0] + px[2] * scale, 1), round(box[1] + px[3] * scale, 1)]
                if (region[2] - region[0]) * (region[3] - region[1]) / (page.width * page.height) < MIN_AREA:
                    continue
                if any(overlap_ratio(region, t["bbox"]) > 0.5 or (t["kind"] == "ocr_failed" and
                       overlap_ratio(region, t["bbox"], "inner") >= 0.7) for t in found):
                    continue  # 이미 잡힌 대상과 겹치거나 통째로 보낼 OCR 실패 블록 안
                crop = img[int(px[1]):int(px[3]), int(px[0]):int(px[2])]
                kind = classify(region, name, crop, chars, image_blocks)
                if kind:
                    found.append({"kind": kind, "bbox": region})

            for i, t in enumerate(found, start=1):
                t["figure_id"] = f"page-{r['page_no']}-fig-{i}"
                if "image_path" not in t:
                    png = config.FIG_DIR / r["domain"] / jsonl_file.stem / f"{t['figure_id']}.png"
                    png.parent.mkdir(parents=True, exist_ok=True)
                    clip = (max(t["bbox"][0], page.bbox[0]), max(t["bbox"][1], page.bbox[1]),
                            min(t["bbox"][2], page.bbox[2]), min(t["bbox"][3], page.bbox[3]))
                    render(page, clip, CROP_DPI).save(png)
                    t["image_path"] = png.relative_to(config.EXTRACT_DIR).as_posix()
                targets.append({"jsonl": jsonl_file.relative_to(config.JSONL_DIR).as_posix(),
                                "page_no": r["page_no"], **t})
    return pages[0]["file_name"], targets


def find(only, workers):
    targets = []
    files = jsonl_files(only)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(find_in_file, f) for f in files]
        for i, fut in enumerate(as_completed(futures), start=1):
            name, found = fut.result()
            targets += found
            print(f"[{i}/{len(files)}] {name} - 대상 {len(found)}개", flush=True)
    write_jsonl(TARGETS, sorted(targets, key=lambda t: (t["jsonl"], t["page_no"], t["figure_id"])))


# ---------------- convert ----------------

def target_key(t):
    return f"{t['jsonl']}#{t['figure_id']}"


def convert(limit, workers):
    """안 끝난 대상을 동시에 변환해 results.jsonl에 쌓는다"""
    from langchain_core.messages import HumanMessage
    done = {r["key"] for r in read_jsonl(RESULTS)}
    todo = [t for t in read_jsonl(TARGETS) if target_key(t) not in done][:limit or None]
    print(f"변환 대상 {len(todo)}개 (완료 {len(done)}개, 모델 {config.VISION_MODEL})", flush=True)
    llm = chat_model(config.VISION_MODEL, max_retries=6)

    def one(t):
        png = (config.EXTRACT_DIR / t["image_path"]).read_bytes()
        msg = HumanMessage(content=[{"type": "text", "text": PROMPTS[t["kind"]]},
                                    {"type": "image", "base64": base64.b64encode(png).decode(), "mime_type": "image/png"}])
        return llm.invoke([msg]).text.strip()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, t): t for t in todo}
        for i, fut in enumerate(as_completed(futures), start=1):
            t = futures[fut]
            try:  # 결과는 메인 스레드에서만 쓴다
                append_jsonl(RESULTS, {"key": target_key(t), "text": fut.result(), "model": config.VISION_MODEL})
            except Exception as e:
                print(f"  실패 {target_key(t)}: {repr(e)[:150]}", flush=True)
            if i % 20 == 0:
                print(f"  {i}/{len(todo)}", flush=True)


# ---------------- merge ----------------

def merge():
    results = {r["key"]: r for r in read_jsonl(RESULTS)}
    by_file = {}
    for t in read_jsonl(TARGETS):
        if target_key(t) in results:
            by_file.setdefault(t["jsonl"], []).append(t)
    for rel, items in by_file.items():
        path = config.JSONL_DIR / rel
        pages = load_pages(path)
        by_no = {r["page_no"]: r for r in pages}
        for r in pages:  # 다시 실행해도 같은 결과가 되게 기존 figure 블록부터 지운다
            r["blocks"] = [b for b in r["blocks"] if b["content_type"] != "figure"]
        for t in items:
            res, r = results[target_key(t)], by_no[t["page_no"]]
            if t["kind"] == "ocr_failed":
                for b in r["blocks"]:
                    if b["block_id"] == t["block_id"]:
                        b.update(text=res["text"], needs_vision=False, vision_method=res["model"])
                continue
            pos = sum(1 for b in r["blocks"] if b["bbox"][1] <= t["bbox"][1])  # 그림 위쪽에서 시작한 블록 뒤
            r["blocks"].insert(pos, {"content_type": "figure", "figure_kind": t["kind"], "figure_id": t["figure_id"],
                                     "bbox": t["bbox"], "image_path": t["image_path"], "text": res["text"],
                                     "vision_method": res["model"], "block_id": f"page-{t['page_no']}-{t['figure_id']}"})
        write_jsonl(path, pages)
    write_previews()
    print(f"반영: {len(by_file)}개 파일")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", default="find,convert,merge")
    parser.add_argument("--only", help="find 단계에서 파일명 일부로 거르기")
    parser.add_argument("--limit", type=int, default=0, help="convert 단계에서 N개만")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    steps = args.steps.split(",")
    if "find" in steps:
        find(args.only, args.workers)
    if "convert" in steps:
        convert(args.limit, args.workers)
    if "merge" in steps:
        merge()


if __name__ == "__main__":
    main()
