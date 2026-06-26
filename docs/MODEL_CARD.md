# Model Card: E14 Digit CNN v0.1

## Model

Small custom CNN trained to read three-digit numeric fields from fixed E14 form crops.

Current weights:

- `digit_cnn.pt`
- Source labels: `labels_2026-06-25_merged_failurecases.csv`
- Training output: `data/e14_bogota/models/digit_cnn_2026-06-25_merged_failurecases`

## Fields

The model was trained on these numeric fields:

- `e11_total`
- `urn_total`
- `candidate_1_ic`
- `candidate_2_ad`
- `blank_votes`
- `null_votes`
- `unmarked_votes`
- `summary_total`

## Training Data

- Labeled rows: `563`
- Training samples: `3,597`
- Validation samples: `904`
- Training sequences: `450`
- Validation sequences: `113`

## Validation Metrics

Held-out validation split:

- Exact field accuracy: `91.26%`
- Digit accuracy: `96.72%`
- Key-field exact accuracy: `89.97%`
- `candidate_1_ic` exact: `92.92%`
- `candidate_2_ad` exact: `87.61%`
- `summary_total` exact: `89.38%`

## Bulk Run Metrics

Across `17,150` locally available Bogotá PDFs:

- Processing failures: `0`
- Strict valid forms: `11,206`, `65.3%`
- Candidate-distribution valid forms: `14,034`, `81.8%`
- Exact fallback candidate-distribution valid: `14,953`, `87.2%`
- 5% fallback candidate-distribution valid: `16,001`, `93.3%`
- 10% fallback candidate-distribution valid: `16,165`, `94.3%`

## Intended Use

This model is intended for exploratory aggregation of Bogotá E14 vote distributions, especially IC vs AD trends by mesa, puesto, and zona.

It is not intended to replace official election results or produce certified legal counts.

## Caveats

- It relies on fixed crop positions for this E14 layout.
- It should be retrained or revalidated before applying to other departments, elections, or form designs.
- Summary totals on some forms are visibly incorrect; those visible values remain valid OCR labels but should not always be used as arithmetic truth.
