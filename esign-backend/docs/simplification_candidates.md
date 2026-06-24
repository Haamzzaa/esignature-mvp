# Production Simplification Candidates

This document outlines components, libraries, and files that are suitable for removal, simplification, or isolation in a clean production environment.

---

## 1. Local OCR Infrastructure (The Major Target)
If Microsoft Azure Document Intelligence is selected as the default production OCR engine, the entire local OCR infrastructure is redundant and can be removed:

* **Packages**: Banish `paddleocr` and `paddlepaddle` from `requirements.txt`.
* **Sub-dependencies**: Remove `opencv-python`, `opencv-python-headless`, `albumentations`, `scikit-image`, `shapely`, `pyclipper`, `lmdb`.
* **Model Weights Directory**: Eliminate `.paddleocr/` model weights directory from deployment targets.
* **Code Simplification**:
  * In [ocr_service.py](file:///c:/Users/Mohammed%20Hamza/esign_Module/esign-backend/services/ocr_service.py), remove `get_ocr_engine()` and `extract_text_with_paddleocr()`.
  * Simplify `extract_text_from_pdf` to raise a clean exception if Azure fails (or handle exceptions via alerts) instead of falling back to PaddleOCR.

---

## 2. Debug Logging & Local Disk Storage
The runtime code contains logging mechanisms that write directly to the local disk during HTTP requests. These should be removed to ensure compatibility with stateless container runtimes:

* **Debug Folder**: Delete `./analysis/debug_responses/` and remove writing functions from `views.py`.
* **Environment Variable**: Deprecate `ENABLE_EXTRACTION_DEBUG` and `EXTRACTION_DEBUG_DIR`.
* **Consolidation**: Convert local file writes into standard Django application logs:
  ```python
  logger.debug(f"Extraction details: {details}")
  ```

---

## 3. Development & Script Artifacts
Multiple utility, benchmark, and validation scripts are present in the project root and subdirectories. These should not be packaged into the production container or library build:

### Root Directory Scripts
* `run_azure_validation.py` (Azure API test script)
* `create_arabic_sample.py` (Helper to draw text onto image)
* `run_on_real_pdf.py` (Pipeline test script)
* `run_pipeline.py` (Pipeline debug run)
* `test_arabic_image.py` (Image OCR testing)
* `test_engine.py` (OCR sanity check)
* `arabic_sample.png` (Sample image assets)
* `debug_full_page.png` / `debug_left_half.png` / `debug_right_half.png` (OCR split-image outputs)
* `ocr_output.txt` (Text file output of OCR runs)

### Tools Directory
* `tools/run_ocr_comparison.py` (Comparison script)
* `tools/comparison_results.csv` (CSV outputs)
* `tools/ocr_comparison_summary.json` (Summary results)
* `tools/contract_*.pdf` (Test PDFs)

**Recommendation**: Move all root-level test scripts and the entire `tools/` folder into a single isolated directory named `dev_tools/` or exclude them via `.dockerignore` / `setup.py` scripts.
