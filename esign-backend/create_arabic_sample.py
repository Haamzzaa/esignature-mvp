from PIL import Image, ImageDraw, ImageFont

# Create a white image
img = Image.new("RGB", (600, 200), color="white")
draw = ImageDraw.Draw(img)

# Draw Arabic text
try:
    # On Windows, Arial has good Arabic glyphs
    font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 40)
except Exception:
    font = ImageFont.load_default()

# We render the text on the image
draw.text((50, 40), "ياسر عثمان رمضان", fill="black", font=font)
draw.text((50, 110), "المدير العام", fill="black", font=font)

img.save("arabic_sample.png")
print("Image arabic_sample.png created successfully.")
