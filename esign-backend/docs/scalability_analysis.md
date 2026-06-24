# Scalability & Containerization Analysis

This document evaluates the `esign-backend` system's runtime performance, memory usage, external service requirements, and Docker packaging feasibility.

---

## 1. Statelessness & Horizontal Scaling
* **HTTP Layer**: The API views do not store any session state in memory. Authentication relies on DRF database tokens (`rest_framework.authtoken`).
* **File Storage**: Uploaded files and signed PDFs are managed via Django's standard storage engine (`django.core.files.storage`). In a production setting, this is configured to use cloud-native object storage (e.g. AWS S3, Azure Blob, or Google Cloud Storage) instead of local directory volumes.
* **Horizontal Scalability**: Because the application servers are completely stateless, you can scale the backend horizontally by running multiple backend containers behind a load balancer (e.g. NGINX or AWS ALB).

---

## 2. Resource Utilization & Performance

### Memory Footprint
* **Standard Web Layer**: Standard Django/DRF requests (database queries, JSON formatting) consume minimal memory, typically **70 MB – 100 MB** RAM per Gunicorn worker.
* **PDF Signing (PyMuPDF)**: Drawing signatures and generating signing certificates is CPU-bound but highly optimized. PyMuPDF handles page-level operations efficiently, requiring low overhead.
* **OCR Layer Comparison**:
  * **Azure OCR Mode**: Azure Document Intelligence operates as an external SaaS API. The local backend only performs HTTP requests. Memory overhead is **zero**, and CPU utilization is minimal.
  * **PaddleOCR Mode**: Loading the PaddlePaddle engine and deep learning models (detection, recognition, classifier) inside a python worker consumes **500 MB – 1 GB** of memory per worker. This restricts the number of concurrent processes that can run on a single virtual machine.

### Task Concurrency
* The Celery distributed worker queue manages long-running processes (email dispatch, daily reminders). Since tasks are run out-of-band, the HTTP response time of the main API is unaffected.

---

## 3. External Dependencies

To run in a highly scalable production cluster, the system requires:
1. **Relational Database**: PostgreSQL (configured via `dj-database-url`).
2. **Message Broker / Cache**: Redis or RabbitMQ (for Celery and standard key-value storage).
3. **Object Storage**: S3-compatible cloud storage for PDFs.
4. **OCR Engine**: Microsoft Azure Document Intelligence endpoint (REST API).

---

## 4. Docker Friendliness

### Option A: Azure-Only Lightweight Container (Recommended)
By omitting the PaddleOCR dependency, the Docker container can be built on a standard Python slim image:
* **Base Image**: `python:3.11-slim`
* **Build Time**: `< 1 minute` (no compilation of complex libraries needed).
* **Final Image Size**: **~250 MB**.
* **Startup Time**: Instant.

### Option B: Local-OCR Heavy Container
If offline PaddleOCR capability is required:
* **Base Image**: Requires compiling binary packages and installing native packages:
  ```dockerfile
  RUN apt-get update && apt-get install -y \
      build-essential \
      libgl1-mesa-glx \
      libglib2.0-0 \
      && rm -rf /var/lib/apt/lists/*
  ```
* **Build Time**: `5 – 10 minutes` (compiling `pyclipper`, `shapely`, downloading model files).
* **Final Image Size**: **~2.2 GB** (due to paddlepaddle, model weights, and OpenCV).
