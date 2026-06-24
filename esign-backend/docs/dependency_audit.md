# Dependency Audit

This document classifies and analyzes the current python dependencies of the `esign-backend` platform. It distinguishes between core production requirements, optional/experimental packages, and heavy packages that impact container sizes and deployment complexity.

---

## 1. Core Production Dependencies
These packages are strictly required for the core business logic of the application (e-signing, workflow management, PDF manipulation, databases, and APIs).

* **Django (`==5.2.14`)**: Web framework and ORM backbone.
* **djangorestframework (`==3.17.1`)**: API framework for stateless CRUD operations on Envelopes, Signers, and Fields.
* **django-cors-headers (`==4.9.0`)**: Handles cross-origin requests for the frontend spa.
* **PyMuPDF / fitz (`==1.27.2.3`)**: Crucial for digital text layer extraction, PDF pages inspection, and workflow validations.
* **pillow (`==12.2.0`)**: Image generation and formatting (e.g. signing certificate generation and signatures).
* **psycopg2-binary (`==2.9.12`)**: PostgreSQL client connector for production storage.
* **python-dotenv (`==1.2.2`)**: Configuration management using environment variables.
* **celery[redis] (`==5.4.0`) / redis (`==5.0.4`)**: Distributed task queue for executing out-of-band operations (reminders, email dispatches, and status advance updates).
* **whitenoise (`==6.12.0`) / gunicorn (`==26.0.0`)**: WSGI server and static file management.
* **rapidfuzz (`==3.14.5`)**: High-performance string matching library used for fuzzy title extraction.

---

## 2. Optional & Development Dependencies
These packages are useful for testing, documentation, and tooling, but could be removed or isolated in strict production distributions.

* **drf-yasg (`==1.21.15`)**: Swagger/OpenAPI documentation generator. While useful, it is not required for executing backend operations and could be bypassed or compiled out in minimal production builds.
* **fitz (Mock dependencies during tests)**: Fitz mock components are used exclusively inside unit tests and are not needed outside execution environments.

---

## 3. Heavy Dependencies (Deployment Bottlenecks)
These packages significantly increase image sizes, build times, CPU/Memory footprints, and runtime dependencies.

* **paddleocr (`==2.10.0`)**: Local optical character recognition library.
* **paddlepaddle (`==2.6.2`)**: Deep learning framework required to run local PaddleOCR models.
* **Secondary transit dependencies**:
  * **opencv-python / opencv-python-headless (`==4.13.0.92`)**: Image preprocessing.
  * **numpy (`==2.3.5`) / scipy (`==1.17.1`)**: Numerical analysis.
  * **albumentations / scikit-image**: Image augmentation pipelines.
  * **shapely / pyclipper**: Geometric calculations for word bounds.
  * **lmdb**: Database files for model loading.

### Impact Analysis
1. **Container Size**: Installing PaddlePaddle and PaddleOCR adds over **1.5 GB** of dependencies, ballooning a standard Docker image from ~300 MB to ~2.0 GB.
2. **Build Complexity**: Compiling binary extensions (e.g., PyClipper, Shapely) requires a build toolchain (`gcc`, `g++`, `make`) in the Docker base image, slowing down CI/CD pipelines.
3. **Memory Footprint**: Loading PaddleOCR model weights inside a Gunicorn worker consumes **~500 MB – 1 GB** of RAM per process, requiring substantial production server capacity.

---

## Recommendation Summary
* Keep `paddleocr` and `paddlepaddle` completely **isolated** from production images when running Azure OCR as the sole provider.
* Treat PaddleOCR as an optional "plugin" that is only installed in images intended for air-gapped/on-prem deployments requiring offline OCR processing.
