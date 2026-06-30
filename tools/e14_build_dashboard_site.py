from __future__ import annotations

import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECOND_ROUND_DIR = ROOT / "data" / "e14_bogota" / "predictions" / "digit_cnn_2026-06-25_merged_failurecases"
FIRST_ROUND_DIR = ROOT / "data" / "e14_first_round_bogota" / "predictions" / "first_round_pair_cropmap_ensemble_full"
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
        return "Mesa unica"
    if relative_position <= 0.10:
        return "0-10% mesas mas adultas"
    if relative_position <= 0.25:
        return "10-25% mesas adultas"
    if relative_position <= 0.50:
        return "25-50% intermedio adulto"
    if relative_position <= 0.75:
        return "50-75% intermedio joven"
    if relative_position <= 0.90:
        return "75-90% mesas jovenes"
    return "90-100% mesas mas jovenes"


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
        "adOver35Rows": sum(1 for row in rows if row["adPct"] is not None and float(row["adPct"]) > 35),
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


def compact_rows(
    all_rows: list[dict[str, str]],
    ad_field: str,
    validation_builder,
) -> list[dict[str, object]]:
    max_mesa_by_stand: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in all_rows:
        stand_key = (row["zone_code"], row["stand_code"], row["stand_name"])
        max_mesa_by_stand[stand_key] = max(max_mesa_by_stand[stand_key], int_value(row["mesa"]))

    rows: list[dict[str, object]] = []
    for row in all_rows:
        stand_key = (row["zone_code"], row["stand_code"], row["stand_name"])
        mesa = int_value(row["mesa"])
        max_mesa = max_mesa_by_stand[stand_key]
        rel_pos = None if max_mesa <= 1 else round((mesa - 1) / (max_mesa - 1), 5)
        ic = int_value(row["candidate_1_ic"])
        ad = int_value(row[ad_field])
        candidate_votes = ic + ad
        item = {
            "sequence": int_value(row["sequence"]),
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
        }
        item.update(validation_builder(row))
        rows.append(item)
    return rows


def build_round(
    *,
    key: str,
    title: str,
    source_dir: Path,
    all_rows: list[dict[str, str]],
    ad_field: str,
    validation_modes: dict[str, str],
    recommended_mode: str,
    validation_builder,
    downloads: dict[str, Path],
) -> dict[str, object]:
    rows = compact_rows(all_rows, ad_field, validation_builder)
    mode_rows = {
        mode: [row for row in rows if row[mode]]
        for mode in validation_modes
    }
    mode_summaries = {
        mode: {
            **summarize(filtered),
            "coveragePct": pct(len(filtered), len(rows)),
        }
        for mode, filtered in mode_rows.items()
    }
    recommended_rows = mode_rows[recommended_mode]

    return {
        "key": key,
        "title": title,
        "generatedFrom": str(source_dir.relative_to(ROOT)),
        "allRows": len(rows),
        "recommendedMode": recommended_mode,
        "validationModes": validation_modes,
        "modeSummaries": mode_summaries,
        "rows": rows,
        "zones": aggregate(recommended_rows, ["zoneCode", "zoneName"]),
        "stands": aggregate(recommended_rows, ["zoneCode", "zoneName", "standCode", "standName"]),
        "downloads": downloads,
    }


def build_second_round() -> dict[str, object]:
    all_rows = read_csv(SECOND_ROUND_DIR / "predictions_all_downloaded.csv")
    fallback_dir = SECOND_ROUND_DIR / "fallback_validation"
    fallback_exact = sequence_set(fallback_dir / "predictions_candidate_distribution_fallback_valid_exact.csv")
    fallback_5pct = sequence_set(fallback_dir / "predictions_candidate_distribution_fallback_valid_5pct.csv")
    fallback_10pct = sequence_set(fallback_dir / "predictions_candidate_distribution_fallback_valid_10pct.csv")

    def validations(row: dict[str, str]) -> dict[str, object]:
        sequence = row["sequence"]
        return {
            "strict": bool_value(row["strict_valid"]),
            "candidate": bool_value(row["candidate_distribution_valid"]),
            "fallbackExact": sequence in fallback_exact,
            "fallback5": sequence in fallback_5pct,
            "fallback10": sequence in fallback_10pct,
        }

    return build_round(
        key="segunda",
        title="Segunda vuelta",
        source_dir=SECOND_ROUND_DIR,
        all_rows=all_rows,
        ad_field="candidate_2_ad",
        validation_modes={
            "fallback5": "Fallback 5% recomendado",
            "fallbackExact": "Fallback exacto",
            "fallback10": "Fallback 10%",
            "candidate": "Distribucion candidatos",
            "strict": "Estricta",
        },
        recommended_mode="fallback5",
        validation_builder=validations,
        downloads={
            "recommended": "predicciones_fallback_5pct.csv",
            "all": "predicciones_todas.csv",
        },
    )


def build_first_round() -> dict[str, object]:
    all_rows = read_csv(FIRST_ROUND_DIR / "predictions_all_downloaded.csv")

    def validations(row: dict[str, str]) -> dict[str, object]:
        return {
            "likely": bool_value(row["likely_valid"]),
            "pairWithin5": bool_value(row["candidate_pair_within_total_5pct"]),
            "plausibleTotals": bool_value(row["plausible_totals"]),
            "all": True,
        }

    return build_round(
        key="primera",
        title="Primera vuelta",
        source_dir=FIRST_ROUND_DIR,
        all_rows=all_rows,
        ad_field="candidate_4_ad",
        validation_modes={
            "likely": "Validacion recomendada",
            "pairWithin5": "IC+AD dentro del total 5%",
            "plausibleTotals": "Totales plausibles",
            "all": "Todos los formularios",
        },
        recommended_mode="likely",
        validation_builder=validations,
        downloads={
            "recommended": "primera_predicciones_likely_valid.csv",
            "all": "primera_predicciones_todas.csv",
        },
    )


def copy_downloads() -> None:
    downloads = {
        "primera_predicciones_todas.csv": FIRST_ROUND_DIR / "predictions_all_downloaded.csv",
        "primera_predicciones_likely_valid.csv": FIRST_ROUND_DIR / "predictions_likely_valid.csv",
        # Backward-compatible names used by the original dashboard.
        "predicciones_todas.csv": SECOND_ROUND_DIR / "predictions_all_downloaded.csv",
        "predicciones_fallback_5pct.csv": SECOND_ROUND_DIR
        / "fallback_validation"
        / "predictions_candidate_distribution_fallback_valid_5pct.csv",
        "tendencia_mesa_relativa.csv": SECOND_ROUND_DIR / "analysis" / "strict_failure_by_relative_mesa_bucket.csv",
        "resumen_puesto.csv": SECOND_ROUND_DIR / "analysis" / "zone_stand_summary_candidate_distribution_valid.csv",
    }
    for name, source in downloads.items():
        shutil.copy2(source, DOWNLOAD_DIR / name)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    rounds = {
        "segunda": build_second_round(),
        "primera": build_first_round(),
    }

    dashboard_data = {
        "metadata": {
            "title": "Elecciones Colombia E14 Bogota",
            "defaultRound": "segunda",
            "roundOrder": ["segunda", "primera"],
            "notes": [
                "La posicion relativa de mesa es un proxy ordinal de edad dentro de cada puesto, no una edad exacta.",
                "La primera vuelta extrae solo Ivan Cepeda (candidato 1) y Abelardo de la Espriella (candidato 4).",
                "La segunda vuelta usa IC y AD como los dos candidatos del formulario.",
                "Zona y puesto vienen de la Registraduria; el tablero no incluye coordenadas reales todavia.",
            ],
        },
        "rounds": rounds,
    }

    (DATA_DIR / "dashboard-data.json").write_text(
        json.dumps(dashboard_data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    copy_downloads()

    print(
        json.dumps(
            {
                "site": str(SITE_DIR),
                "dashboardData": str(DATA_DIR / "dashboard-data.json"),
                "dashboardDataMB": round((DATA_DIR / "dashboard-data.json").stat().st_size / 1024 / 1024, 2),
                "rounds": {
                    key: {
                        "rows": value["allRows"],
                        "recommendedMode": value["recommendedMode"],
                        "recommendedRows": value["modeSummaries"][value["recommendedMode"]]["rows"],
                        "adOver35Rows": value["modeSummaries"][value["recommendedMode"]]["adOver35Rows"],
                    }
                    for key, value in rounds.items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
