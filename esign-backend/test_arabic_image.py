import sys
# Configure console stdout to use UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from paddleocr import PaddleOCR

ocr = PaddleOCR(
    use_angle_cls=True,
    lang="ar"
)

result = ocr.ocr("arabic_sample.png", cls=True)

with open("ocr_output.txt", "w", encoding="utf-8") as f:
    for line in result[0]:
        text = line[1][0]
        conf = line[1][1]
        print(f"Recognized: {repr(text)} with confidence {conf}")
        f.write(f"{text}\n")
        
print("Output written to ocr_output.txt successfully.")
