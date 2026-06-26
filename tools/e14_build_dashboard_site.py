from __future__ import annotations

import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRED_DIR = ROOT / "data" / "e14_bogota" / "predictions" / "digit_cnn_2026-06-25_merged_failurecases"
SITE_DIR = ROOT / "site" / "e14-dashboard"
DATA_DIR = SITE_DIR / "data"
DOWNLOAD_DIR = SITE_DIR / "downloads"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def bool_value(value: object) -> bool:
    return str(value).strip().lower() == "true"


def int_value(value: object) -> int:
    try:
        return int(str(value).strip())
    except ValueError:
        return 0


def pct(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator * 100, 4)


def relative_bucket(relative_position: float | None) -> str:
    if relative_position is None:
        return "Mesa única"
    if relative_position <= 0.10:
        return "0-10% mesas más adultas"
    if relative_position <= 0.25:
        return "10-25% mesas adultas"
    if relative_position <= 0.50:
        return "25-50% intermedio adulto"
    if relative_position <= 0.75:
        return "50-75% intermedio joven"
    if relative_position <= 0.90:
        return "75-90% mesas jóvenes"
    return "90-100% mesas más jóvenes"


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    ic = sum(int(row["ic"]) for row in rows)
    ad = sum(int(row["ad"]) for row in rows)
    candidate_votes = ic + ad
    return {
        "rows": len(rows),
        "ic": ic,
        "ad": ad,
        "candidateVotes": candidate_votes,
        "icPct": pct(ic, candidate_votes),
        "adPct": pct(ad, candidate_votes),
        "marginIc": pct(ic - ad, candidate_votes),
    }


def aggregate(rows: list[dict[str, object]], keys: list[str]) -> list[dict[str, object]]:
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[key] for key in keys)].append(row)

    output = []
    for values, group in grouped.items():
        item = {key: value for key, value in zip(keys, values)}
        item.update(summarize(group))
        output.append(item)

    def sort_part(value: object) -> tuple[int, int | str]:
        text = str(value)
        return (0, int(text)) if text.isdigit() else (1, text)

    return sorted(output, key=lambda row: tuple(sort_part(row[key]) for key in keys))


def sequence_set(path: Path) -> set[str]:
    return {row["sequence"] for row in read_csv(path)}


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    all_rows = read_csv(PRED_DIR / "predictions_all_downloaded.csv")
    fallback_dir = PRED_DIR / "fallback_validation"
    fallback_exact = sequence_set(fallback_dir / "predictions_candidate_distribution_fallback_valid_exact.csv")
    fallback_5pct = sequence_set(fallback_dir / "predictions_candidate_distribution_fallback_valid_5pct.csv")
    fallback_10pct = sequence_set(fallback_dir / "predictions_candidate_distribution_fallback_valid_10pct.csv")

    max_mesa_by_stand: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in all_rows:
        stand_key = (row["zone_code"], row["stand_code"], row["stand_name"])
        max_mesa_by_stand[stand_key] = max(max_mesa_by_stand[stand_key], int_value(row["mesa"]))

    compact_rows: list[dict[str, object]] = []
    for row in all_rows:
        stand_key = (row["zone_code"], row["stand_code"], row["stand_name"])
        mesa = int_value(row["mesa"])
        max_mesa = max_mesa_by_stand[stand_key]
        rel_pos = None if max_mesa <= 1 else round((mesa - 1) / (max_mesa - 1), 5)
        sequence = row["sequence"]
        ic = int_value(row["candidate_1_ic"])
        ad = int_value(row["candidate_2_ad"])
        candidate_votes = ic + ad
        compact_rows.append(
            {
                "sequence": int_value(sequence),
                "pdf": row["pdf_name"],
                "zoneCode": row["zone_code"],
                "zoneName": row["zone_name"],
                "standCode": row["stand_code"],
                "standName": row["stand_name"],
                "mesa": mesa,
                "maxMesa": max_mesa,
                "relativePosition": rel_pos,
                "relativeBucket": relative_bucket(rel_pos),
                "ic": ic,
                "ad": ad,
                "candidateVotes": candidate_votes,
                "icPct": pct(ic, candidate_votes),
                "adPct": pct(ad, candidate_votes),
                "strictValid": bool_value(row["strict_valid"]),
                "candidateValid": bool_value(row["candidate_distribution_valid"]),
                "fallbackExact": sequence in fallback_exact,
                "fallback5": sequence in fallback_5pct,
                "fallback10": sequence in fallback_10pct,
                "candidateArithmeticValid": bool_value(row["candidate_arithmetic_valid"]),
                "summaryMatchesUrn": bool_value(row["summary_matches_urn"]),
                "summaryMatchesE11": bool_value(row["summary_matches_e11"]),
                "plausibleSummary": bool_value(row["plausible_summary"]),
            }
        )

    validation_modes = {
        "strict": [row for row in compact_rows if row["strictValid"]],
        "candidate": [row for row in compact_rows if row["candidateValid"]],
        "fallbackExact": [row for row in compact_rows if row["fallbackExact"]],
        "fallback5": [row for row in compact_rows if row["fallback5"]],
        "fallback10": [row for row in compact_rows if row["fallback10"]],
    }

    mode_summaries = {
        mode: {
            **summarize(rows),
            "coveragePct": pct(len(rows), len(compact_rows)),
        }
        for mode, rows in validation_modes.items()
    }

    zones = aggregate(validation_modes["fallback5"], ["zoneCode", "zoneName"])
    stands = aggregate(validation_modes["fallback5"], ["zoneCode", "zoneName", "standCode", "standName"])

    dashboard_data = {
        "metadata": {
            "title": "Elecciones Colombia E14 Bogota",
            "generatedFrom": str(PRED_DIR.relative_to(ROOT)),
            "allRows": len(compact_rows),
            "notes": [
                "La posición relativa de mesa es un proxy ordinal de edad dentro de cada puesto, no una edad exacta.",
                "La validación recomendada para explorar distribución de candidatos es fallback 5%.",
                "Zona y puesto vienen de la Registraduría; el tablero no incluye coordenadas reales todavía.",
            ],
        },
        "validationModes": {
            "strict": "Validacion estricta",
            "candidate": "Distribucion de candidatos",
            "fallbackExact": "Fallback exacto",
            "fallback5": "Fallback 5%",
            "fallback10": "Fallback 10%",
        },
        "modeSummaries": mode_summaries,
        "rows": compact_rows,
        "zones": zones,
        "stands": stands,
    }

    (DATA_DIR / "dashboard-data.json").write_text(
        json.dumps(dashboard_data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    downloads = {
        "predicciones_todas.csv": PRED_DIR / "predictions_all_downloaded.csv",
        "predicciones_fallback_5pct.csv": fallback_dir / "predictions_candidate_distribution_fallback_valid_5pct.csv",
        "tendencia_mesa_relativa.csv": PRED_DIR / "analysis" / "strict_failure_by_relative_mesa_bucket.csv",
        "resumen_puesto.csv": PRED_DIR / "analysis" / "zone_stand_summary_candidate_distribution_valid.csv",
    }
    for name, source in downloads.items():
        shutil.copy2(source, DOWNLOAD_DIR / name)

    print(
        json.dumps(
            {
                "site": str(SITE_DIR),
                "dashboardData": str(DATA_DIR / "dashboard-data.json"),
                "rows": len(compact_rows),
                "dashboardDataMB": round((DATA_DIR / "dashboard-data.json").stat().st_size / 1024 / 1024, 2),
                "downloads": list(downloads),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
