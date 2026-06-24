from paddleocr import PaddleOCR

ocr = PaddleOCR(
    use_angle_cls=True,
    lang="ar"
)

print("Engine initialized successfully.")
print(hasattr(ocr, "ocr"))
