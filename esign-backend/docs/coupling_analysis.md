# Module Coupling Analysis

This document evaluates the architectural relationships and coupling levels among different layers of the `esign-backend` platform. It identifies areas of high coupling, runtime leaks, and architectural isolation.

---

## 1. Architectural Layers & Flow
The target architecture follows a decoupled, layered approach:
```text
Views (API Controllers)
       ↓
Services (Business Logic / Orchestrators)
       ↓
Domain Logic (Pure Business Rules)
       ↓
Storage / Database Models (ORM / State Persistence)
```

---

## 2. Strengths (Successful Decoupling)

### 1. Pure Domain Logic Isolation (`authority_extraction_service.py`)
* The core authority extraction engine is **completely decoupled** from:
  * Django and django models / ORM.
  * DRF and HTTP views.
  * OCR libraries (PaddleOCR, Azure SDK).
  * PDF rendering engines (PyMuPDF).
* It takes simple Python strings (`raw_text`, `english_text`, `arabic_text`) and returns plain dictionary objects. It has zero external dependencies other than `rapidfuzz` and python standard libraries.
* **Benefit**: It can be copied directly or packaged as a standalone Python library (e.g. for CLI parsing or background queue integration) without pulling in web servers or databases.

### 2. Standardized OCR Contract
* Regardless of whether the system uses Azure OCR, PaddleOCR, or extracts directly from digital PDFs, the routing interface `extract_text_from_pdf()` standardizes the result output format:
  ```python
  {
      "raw_text": str,
      "english_text": str,
      "arabic_text": str,
      "ocr_provider": str,
      "ocr_confidence": float,
      "fallback_used": bool,
      "page_count": int,
      ...
  }
  ```
* This prevents OCR engine specifics (like Azure's JSON response structures or Paddle's nested bounding box arrays) from leaking into the database, views, or authority extraction logic.

---

## 3. Weaknesses (Tight Coupling & Leaks)

### 1. Orchestration Leakage in Views
* In [views.py](file:///c:/Users/Mohammed%20Hamza/esign_Module/esign-backend/esign/views.py), the `ContractAnalyzeView` handles several tasks that belong in a dedicated orchestrator service:
  * Checking file extensions and size limitations.
  * Reading raw bytes and opening the PDF with `fitz` directly in the view to validate page counts.
  * Deciding whether to process the file as a PDF or an image, and calling the corresponding service functions.
  * Merging timing statistics from OCR operations and authority extraction.
* **Refactoring Strategy**: Introduce a `ContractAnalysisService` inside the services folder. The view should simply accept the file, pass it to the service, and return the output.

### 2. Debug & Storage Leakage in Views
* The view contains file system write calls to output JSON debug responses to `./analysis/debug_responses/` when `ENABLE_EXTRACTION_DEBUG` is active.
* Views should be focused on request parsing, authentication, and HTTP responses, and should **never** write directly to the local disk or perform low-level text slicing for debugging.
* **Refactoring Strategy**: Move all debug output operations into the `ocr_service` or a logging middleware.

### 3. Model Dependencies in Envelope Services
* The `envelope_service.py` directly imports Django serializers and models:
  ```python
  from esign.models import Envelope, Document, DocumentField, Participant ...
  from esign.serializers import EnvelopeCreateSerializer
  ```
* While common in Django projects, this couples business orchestration tightly with serializing schemas. To write lightweight library wrappers, state changes should be abstracted.

---

## 4. Leakage of Tooling & Benchmarks
* **Isolation**: Fortunately, the benchmark tools, comparison utilities, and ground-truth documents are located entirely in the `tools/` folder.
* **Runtime Verification**: The core backend never imports anything from the `tools/` folder, ensuring development utilities remain outside production runtimes.
