# Minimal Biometric Test Dataset

This directory holds the lightweight folder structure for testing the standalone face verification pipeline.

## Directory Structure

- `genuine/` — National ID image and multiple selfies of the same person. Used to verify successful matches.
- `impostor/` — Selfies of different people. Used to verify rejection accuracy.
- `poor_quality/` — Blurry, dark, side-profile, or multiple-face images. Used to test quality validation and retry mechanisms.
- `outputs/` — Generated debug images and JSON verification reports from test runs.
