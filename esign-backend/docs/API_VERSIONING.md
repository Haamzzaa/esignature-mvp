# API Versioning Documentation

This document describes the API versioning policy, philosophy, and deprecation roadmap for the E-Signature platform.

---

## 1. Current API Version
* **Primary Version**: `v1` (Active path: `/api/v1/`)
* **Deprecated Version**: Unversioned (Legacy path: `/api/`)

---

## 2. Versioning Philosophy
We follow URL-path versioning (`/api/v{N}/`) for the API gateway to ensure clean routing separation, easy integration, and immediate client adaptability.

1. **Path-Based Isolation**: Each API version is isolated under its own URL namespace prefix (e.g. `/api/v1/`).
2. **Immutable Contracts**: Once a version is officially released, its endpoint paths, request payloads, response payloads, and status codes are considered immutable. Any breaking changes will occur under a new major version namespace (e.g. `/api/v2/`).

---

## 3. Backward Compatibility Guarantees
We guarantee that:
* The legacy, unversioned path namespace (`/api/*`) will continue to operate and return identical schemas during the deprecation period.
* Adding new, optional fields to existing response payloads or request body serializations will not trigger a new API version.
* Bug fixes that do not alter the expected status codes or request shapes will be applied in-place.

---

## 4. Deprecation and Decommissioning Policy
* **Deprecation Notice**: Unversioned `/api/` endpoints are formally deprecated as of `v1` release.
* **Deprecation Period**: The deprecated unversioned routes will remain operational for **180 days** or until the next major release, whichever comes first.
* **Alerting**: Schema outputs under `/api/` are omitted from documentation and contain deprecation warnings in their Swagger schema notes.

---

## 5. Future Versioning Strategy
When transitioning to `/api/v2/`:
1. **Serialization Versioning**: Django serializers will inherit versions (e.g. `EnvelopeSerializerV2`) rather than duplicating the underlying database tables.
2. **Accept Headers**: Integrating products can optionally pass version headers (`Accept: application/vnd.esign.v2+json`) to route requests dynamically inside middleware if URL namespaces are not desired.
