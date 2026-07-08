import time
import sys
import os

print("Starting InsightFace diagnostic script...")

# Record environment info
import platform
print(f"Python version: {platform.python_version()}")

try:
    import insightface
    print(f"insightface version: {insightface.__version__}")
except ImportError as e:
    print(f"insightface import failed: {e}")

try:
    import onnx
    print(f"onnx version: {onnx.__version__}")
except ImportError as e:
    print(f"onnx import failed: {e}")

try:
    import onnxruntime
    print(f"onnxruntime version: {onnxruntime.__version__}")
except ImportError as e:
    print(f"onnxruntime import failed: {e}")

try:
    import google.protobuf
    print(f"protobuf version: {google.protobuf.__version__}")
except ImportError as e:
    print(f"protobuf import failed: {e}")

print("-" * 40)

t0 = time.time()
print("Creating FaceAnalysis with allowed_modules=['detection', 'recognition']...")
try:
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(name="buffalo_l", allowed_modules=["detection", "recognition"], providers=["CPUExecutionProvider"])
    print(f"FaceAnalysis created successfully. Elapsed: {time.time() - t0:.4f} seconds")
except Exception as e:
    print(f"Error creating FaceAnalysis: {e}")
    sys.exit(1)

t1 = time.time()
print("Preparing FaceAnalysis with ctx_id=-1 (CPU)...")
try:
    app.prepare(ctx_id=-1)
    print(f"FaceAnalysis prepared successfully. Elapsed: {time.time() - t1:.4f} seconds")
except Exception as e:
    print(f"Error preparing FaceAnalysis: {e}")
    sys.exit(1)

print("Success")
print(f"Total time elapsed: {time.time() - t0:.4f} seconds")
