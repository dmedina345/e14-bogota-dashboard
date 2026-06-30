from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter, ImageOps
from pypdf import PdfReader
from torch.nn import functional as F


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from e14_train_digit_cnn import DigitCNN, IMAGE_SIZE, remove_form_lines, trim_content  # noqa: E402


DATA_DIR = ROOT / "data" / "e14_first_round_bogota"
MANIFEST = DATA_DIR / "manifest_dep_16_corp_001.csv"
PDF_ROOT = DATA_DIR / "pdf"
DEFAULT_MODEL = ROOT / "data" / "e14_bogota" / "models" / "digit_cnn_2026-06-25_merged_failurecases" / "digit_cnn.pt"
DEFAULT_OUT = DATA_DIR / "predictions" / "first_round_pair_digit_cnn"

BASE_SIZE = (934, 2619)
FIELDS = {
    "label_e11_total": (610, 650, 850, 730),
    "label_urn_total": (610, 725, 850, 800),
    "label_incinerated_total": (610, 810, 830, 890),
    "label_candidate_1_ic": (635, 1015, 860, 1105),
    "label_candidate_4_ad": (635, 1680, 860, 1770),
}

TOTAL_VARIANTS = {
    "label_e11_total": [
        ("wide", (610, 650, 850, 730)),
        ("wide2", (625, 650, 850, 730)),
        ("mid", (635, 650, 850, 730)),
        ("interior", (650, 650, 850, 730)),
    ],
    "label_urn_total": [
        ("wide", (610, 725, 850, 800)),
        ("wide2", (625, 725, 850, 800)),
        ("mid", (635, 725, 850, 800)),
        ("interior", (650, 725, 850, 800)),
    ],
    "label_incinerated_total": [
        ("wide", (610, 810, 830, 890)),
        ("wide2", (625, 810, 830, 890)),
        ("mid", (635, 810, 830, 890)),
        ("interior", (650, 810, 850, 890)),
    ],
}

FIELD_TO_OUTPUT = {
    "label_e11_total": "e11_total",
    "label_urn_total": "urn_total",
    "label_incinerated_total": "incinerated_total",
    "label_candidate_1_ic": "candidate_1_ic",
    "label_candidate_4_ad": "candidate_4_ad",
}


def load_manifest(manifest: Path, pdf_root: Path) -> list[dict[str, str]]:
    rows = []
    with manifest.open(newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            pdf_path = pdf_root / row["pdf_relative_path"]
            if pdf_path.exists():
                row["_pdf_path"] = str(pdf_path)
                rows.append(row)

    def sort_part(value: str) -> tuple[int, int | str]:
        return (0, int(value)) if value.isdigit() else (1, value)

    return sorted(
        rows,
        key=lambda r: (
            sort_part(r["municipality_code"]),
            sort_part(r["zone_code"]),
            sort_part(r["stand_code"]),
            sort_part(r["table_number"]),
            r["pdf_name"],
        ),
    )


def pdf_to_first_page_image(pdf: Path) -> Image.Image:
    reader = PdfReader(str(pdf))
    image = reader.pages[0].images[0]
    page = Image.open(io.BytesIO(image.data)).convert("L")
    if page.size != BASE_SIZE:
        page = page.resize(BASE_SIZE, Image.Resampling.BILINEAR)
    return page


def prepare_first_round_crop(page: Image.Image, box: tuple[int, int, int, int]) -> torch.Tensor:
    crop = page.crop(box)
    crop = remove_form_lines(crop)
    crop = trim_content(crop)
    crop = ImageOps.autocontrast(crop)
    crop = crop.filter(ImageFilter.SHARPEN)
    crop.thumbnail((IMAGE_SIZE[0] - 16, IMAGE_SIZE[1] - 12), Image.Resampling.LANCZOS)

    canvas = Image.new("L", IMAGE_SIZE, 255)
    canvas.paste(crop, ((IMAGE_SIZE[0] - crop.width) // 2, (IMAGE_SIZE[1] - crop.height) // 2))
    arr = np.asarray(canvas, dtype=np.float32)
    arr = (255.0 - arr) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


def confidence_stats(probs: torch.Tensor, pred: torch.Tensor) -> tuple[float, float]:
    chosen = probs.gather(1, pred.view(3, 1)).squeeze(1)
    return float(chosen.min().item()), float(chosen.prod().item())


def predict_boxes(
    model: DigitCNN,
    page: Image.Image,
    named_boxes: list[tuple[str, tuple[int, int, int, int]]],
    device: torch.device,
) -> dict[str, dict[str, object]]:
    images = torch.stack([prepare_first_round_crop(page, box) for _, box in named_boxes]).to(device)
    with torch.inference_mode():
        logits = model(images)
        probs = F.softmax(logits, dim=-1).cpu()
        preds = probs.argmax(dim=-1).cpu()

    results: dict[str, dict[str, object]] = {}
    for idx, (name, _box) in enumerate(named_boxes):
        digit_text = "".join(str(int(v)) for v in preds[idx].tolist())
        min_conf, prod_conf = confidence_stats(probs[idx], preds[idx])
        results[name] = {
            "value": int(digit_text),
            "digits": digit_text,
            "min_digit_confidence": round(min_conf, 6),
            "sequence_confidence": round(prod_conf, 6),
        }
    return results


def choose_total_pair(
    e11_options: list[tuple[str, dict[str, object]]],
    urn_options: list[tuple[str, dict[str, object]]],
    candidate_pair_total: int,
) -> tuple[str, dict[str, object], str, dict[str, object]]:
    def score(option: tuple[str, dict[str, object]], urn_option: tuple[str, dict[str, object]]) -> tuple[float, float]:
        _e11_name, e11 = option
        _urn_name, urn = urn_option
        e11_value = int(e11["value"])
        urn_value = int(urn["value"])
        larger_total = max(e11_value, urn_value)
        penalty = 0.0
        if not (0 < e11_value < 450):
            penalty += 1000.0
        if not (0 < urn_value < 450):
            penalty += 1000.0
        penalty += min(abs(e11_value - urn_value), 60) * 3.0
        leeway = max(5, round(larger_total * 0.05))
        if candidate_pair_total > larger_total + leeway:
            penalty += 500.0 + candidate_pair_total - larger_total
        confidence = float(e11["sequence_confidence"]) + float(urn["sequence_confidence"])
        return (penalty, -confidence)

    best = min(
        ((e11_name, e11, urn_name, urn) for e11_name, e11 in e11_options for urn_name, urn in urn_options),
        key=lambda item: score((item[0], item[1]), (item[2], item[3])),
    )
    return best


def choose_incinerated(incinerated_options: list[tuple[str, dict[str, object]]]) -> tuple[str, dict[str, object]]:
    plausible = [item for item in incinerated_options if 0 <= int(item[1]["value"]) < 20]
    options = plausible or incinerated_options
    return max(options, key=lambda item: float(item[1]["sequence_confidence"]))


def predict_page(model: DigitCNN, page: Image.Image, device: torch.device) -> tuple[dict[str, int], dict[str, str], dict[str, float]]:
    candidate_fields = ["label_candidate_1_ic", "label_candidate_4_ad"]
    candidate_results = predict_boxes(model, page, [(field, FIELDS[field]) for field in candidate_fields], device)
    candidate_pair_total = int(candidate_results["label_candidate_1_ic"]["value"]) + int(candidate_results["label_candidate_4_ad"]["value"])

    total_boxes = [
        (f"{field}:{variant}", box)
        for field, variants in TOTAL_VARIANTS.items()
        for variant, box in variants
    ]
    total_results = predict_boxes(model, page, total_boxes, device)
    chosen = choose_total_pair(
        [(variant, total_results[f"label_e11_total:{variant}"]) for variant, _box in TOTAL_VARIANTS["label_e11_total"]],
        [(variant, total_results[f"label_urn_total:{variant}"]) for variant, _box in TOTAL_VARIANTS["label_urn_total"]],
        candidate_pair_total,
    )
    e11_name, e11, urn_name, urn = chosen
    incinerated_name, incinerated = choose_incinerated(
        [(variant, total_results[f"label_incinerated_total:{variant}"]) for variant, _box in TOTAL_VARIANTS["label_incinerated_total"]]
    )

    selected_results = {
        "label_e11_total": e11,
        "label_urn_total": urn,
        "label_incinerated_total": incinerated,
        **candidate_results,
    }
    selected_variants = {
        "label_e11_total": e11_name,
        "label_urn_total": urn_name,
        "label_incinerated_total": incinerated_name,
    }

    values: dict[str, int] = {}
    digits: dict[str, str] = {}
    confidences: dict[str, float] = {}
    for field, result in selected_results.items():
        out_field = FIELD_TO_OUTPUT[field]
        values[out_field] = int(result["value"])
        digits[f"{out_field}_digits"] = str(result["digits"])
        confidences[f"{out_field}_min_digit_confidence"] = float(result["min_digit_confidence"])
        confidences[f"{out_field}_sequence_confidence"] = float(result["sequence_confidence"])
        if field in selected_variants:
            digits[f"{out_field}_crop_variant"] = selected_variants[field]
    return values, digits, confidences


def validation(row: dict[str, object]) -> dict[str, object]:
    e11 = int(row["e11_total"])
    urn = int(row["urn_total"])
    incinerated = int(row["incinerated_total"])
    ic = int(row["candidate_1_ic"])
    ad = int(row["candidate_4_ad"])
    larger_total = max(e11, urn)
    pair_total = ic + ad

    plausible_e11 = 0 < e11 < 450
    plausible_urn = 0 < urn < 450
    plausible_incinerated = 0 <= incinerated < 450
    totals_close = abs(e11 - urn) <= 5
    pair_within_total = pair_total <= larger_total + max(5, round(larger_total * 0.05))
    pair_plausible = 0 <= ic < 450 and 0 <= ad < 450 and pair_total > 0 and pair_within_total
    likely_valid = bool(plausible_e11 and plausible_urn and plausible_incinerated and totals_close and pair_plausible)

    return {
        "candidate_pair_total": pair_total,
        "totals_close": totals_close,
        "candidate_pair_within_total_5pct": pair_within_total,
        "plausible_totals": bool(plausible_e11 and plausible_urn and plausible_incinerated),
        "likely_valid": likely_valid,
        "ic_pct_pair": round(ic / pair_total * 100, 4) if pair_total else "",
        "ad_pct_pair": round(ad / pair_total * 100, 4) if pair_total else "",
        "pair_share_of_urn": round(pair_total / urn * 100, 4) if urn else "",
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--pdf-root", type=Path, default=PDF_ROOT)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    torch.set_num_threads(args.threads)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(args.model, map_location=device)
    model = DigitCNN().to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows = load_manifest(args.manifest, args.pdf_root)
    total_downloaded = len(manifest_rows)
    if args.offset:
        manifest_rows = manifest_rows[args.offset :]
    if args.limit:
        manifest_rows = manifest_rows[: args.limit]

    rows: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    start = time.time()
    for idx, meta in enumerate(manifest_rows, 1):
        pdf_path = Path(meta["_pdf_path"])
        try:
            page = pdf_to_first_page_image(pdf_path)
            values, digit_texts, confidences = predict_page(model, page, device)
            row: dict[str, object] = {
                "sequence": args.offset + idx,
                "pdf_name": meta["pdf_name"],
                "department_code": meta["department_code"],
                "municipality_code": meta["municipality_code"],
                "municipality_name": meta["municipality_name"],
                "zone_code": meta["zone_code"],
                "zone_name": meta["zone_name"],
                "stand_code": meta["stand_code"],
                "stand_name": meta["stand_name"],
                "mesa": meta["table_number"],
                "pdf_relative_path": meta["pdf_relative_path"],
                "pdf_url": meta["pdf_url"],
            }
            row.update(values)
            row.update(digit_texts)
            row.update(confidences)
            row.update(validation(row))
            rows.append(row)
        except Exception as exc:
            failures.append({"pdf_name": meta.get("pdf_name", ""), "error": repr(exc)})

        if idx == 1 or idx % 100 == 0 or idx == len(manifest_rows):
            elapsed = time.time() - start
            print(f"processed {idx}/{len(manifest_rows)} rows in {elapsed:.1f}s")

    all_csv = args.out_dir / "predictions_all_downloaded.csv"
    likely_csv = args.out_dir / "predictions_likely_valid.csv"
    write_csv(all_csv, rows)
    write_csv(likely_csv, [row for row in rows if row["likely_valid"]])

    summary = {
        "model": str(args.model),
        "device": str(device),
        "base_size": BASE_SIZE,
        "fields": FIELDS,
        "total_variants": TOTAL_VARIANTS,
        "manifest_downloaded_pdfs": total_downloaded,
        "rows_requested": len(manifest_rows),
        "rows_predicted": len(rows),
        "failures": len(failures),
        "likely_valid": sum(1 for row in rows if row["likely_valid"]),
        "plausible_totals": sum(1 for row in rows if row["plausible_totals"]),
        "candidate_pair_within_total_5pct": sum(1 for row in rows if row["candidate_pair_within_total_5pct"]),
        "all_predictions_csv": str(all_csv),
        "likely_valid_csv": str(likely_csv),
        "failure_json": str(args.out_dir / "failures.json"),
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (args.out_dir / "failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
