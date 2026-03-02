"""Crop favicon to just inside the black border (inner white + B only)."""
import os
from PIL import Image

static_dir = os.path.join(os.path.dirname(__file__), "SS", "static")
src = os.path.join(static_dir, "favicon.png")
dest = os.path.join(static_dir, "favicon-nav.png")

img = Image.open(src).convert("RGBA")
w, h = img.size

# Find bounding box of black/dark pixels (the logo + black border)
pixels = img.load()
min_x, min_y = w, h
max_x, max_y = 0, 0
for y in range(h):
    for x in range(w):
        r, g, b, a = pixels[x, y]
        if r < 250 or g < 250 or b < 250:  # not pure white
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)

# Inset by border width so crop is just inside the black line
border_width = 3
min_x = min(min_x + border_width, w - 1)
min_y = min(min_y + border_width, h - 1)
max_x = max(max_x - border_width, min_x + 1)
max_y = max(max_y - border_width, min_y + 1)

cropped = img.crop((min_x, min_y, max_x, max_y))
cropped.save(dest, "PNG")
print(f"Saved cropped favicon to {dest}")
