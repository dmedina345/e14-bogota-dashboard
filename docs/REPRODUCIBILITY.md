# Reproducibility Notes

## Recommended Artifact

Download the `e14-bogota-ocr-artifact-v0.1.zip` GitHub Release asset.

The original E14 PDFs are not bundled. Use `manifest_dep_16_corp_001.csv` and the downloader script to reproduce the local PDF set.

## Expected Local Layout

The scripts were developed with this layout:

```text
data/e14_bogota/
  manifest_dep_16_corp_001.csv
  pdf/
  labeling/user_labels/labels_2026-06-25_merged_failurecases.csv
  models/digit_cnn_2026-06-25_merged_failurecases/digit_cnn.pt
```

## Core Commands

Download PDFs from the manifest:

```powershell
node .\tools\e14_download_manifest.mjs --manifest .\data\e14_bogota\manifest_dep_16_corp_001.csv --out .\data\e14_bogota --concurrency 1 --delay-ms 2000 --retries 1 --timeout-ms 30000 --max-failures 20
```

Train the current model family:

```powershell
py -3.10 .\tools\e14_train_digit_cnn.py --labels .\data\e14_bogota\labeling\user_labels\labels_2026-06-25_merged_failurecases.csv --out-dir .\data\e14_bogota\models\digit_cnn_2026-06-25_merged_failurecases
```

Predict all downloaded PDFs:

```powershell
py -3.10 .\tools\e14_predict_digit_cnn.py --model .\data\e14_bogota\models\digit_cnn_2026-06-25_merged_failurecases\digit_cnn.pt --out-dir .\data\e14_bogota\predictions\digit_cnn_2026-06-25_merged_failurecases
```

Run fallback validation:

```powershell
py -3.10 .\tools\e14_revalidate_predictions.py --pred-dir .\data\e14_bogota\predictions\digit_cnn_2026-06-25_merged_failurecases
```

Run analysis aggregation:

```powershell
py -3.10 .\tools\e14_analyze_predictions.py --pred-dir .\data\e14_bogota\predictions\digit_cnn_2026-06-25_merged_failurecases
```

Build the static dashboard data:

```powershell
py -3.10 .\tools\e14_build_dashboard_site.py
```

## Python Dependencies

The OCR model path uses Python 3.10 and PyTorch. The local environment also used common data tooling such as `numpy`, `pandas`-style CSV processing through the standard library, and PDF/image tooling installed during experimentation.

If recreating from scratch, start with:

```powershell
py -3.10 -m venv .venv-e14
.\.venv-e14\Scripts\python.exe -m pip install torch torchvision pillow opencv-python numpy
```

Then adjust if a script reports a missing package.
