# Data Card: E14 Bogotá OCR Artifact v0.1

## Scope

This artifact covers Bogotá D.C. only.

- Department code: `16`
- Municipality: `BOGOTA. D.C.`
- Election source: Registraduría E14 presidential second-round forms
- Manifest rows: `17,164`
- Local PDFs processed in current run: `17,150`

## Included Data

- `manifest_dep_16_corp_001.csv`: Bogotá manifest with E14 PDF metadata and source URLs.
- `labels_2026-06-25_merged_failurecases.csv`: manually labeled OCR training/evaluation labels.
- `predictions_all_downloaded.csv`: model predictions for all locally available Bogotá PDFs.
- `fallback_validation_summary.json`: validation counts and vote totals under exact, 5%, and 10% fallback rules.
- `validation_predictions.csv`: model predictions on the held-out validation split.

## Labeling Notes

Labels represent the numbers visibly written on the E14 form, even when the form arithmetic appears wrong. This is intentional: the OCR model is trained to read what is written, not to correct the form.

Known form-total issues are handled downstream through fallback validation against candidate totals, E11 totals, and urn totals.

## Age Proxy Note

Mesa number is used only as an ordinal proxy within each puesto. Lower mesa numbers generally correspond to older voters and higher mesa numbers to younger voters. The artifact does not contain exact voter age ranges.

## Recommended Analysis Filter

For IC vs AD distribution analysis, the recommended validation mode is candidate-distribution fallback with 5% tolerance. In the current run this validates `16,001 / 17,150` local PDFs, or `93.3%`.

## Limitations

- Bogotá D.C. only.
- OCR labels are partial, manually curated training data, not a complete human transcription of every E14 form.
- The original PDFs are not bundled because they are about 0.88 GB locally. Use the manifest URLs and downloader scripts if you need to reproduce the PDF set.
