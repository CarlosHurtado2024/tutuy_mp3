"""Generate the native Windows icon from Tutuy's existing geometric mark.

Only needed when changing the icon. Requires Pillow at development time.
"""
from pathlib import Path
from PIL import Image, ImageDraw

image = Image.new('RGBA',(256,256))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((0,0,255,255),radius=64,fill='#a78bfa')
draw.arc((50,40,206,196),180,360,fill='#15111f',width=20)
draw.rounded_rectangle((38,124,82,206),radius=17,fill='#15111f')
draw.rounded_rectangle((174,124,218,206),radius=17,fill='#15111f')
image.save(Path(__file__).resolve().parent.parent/'web'/'icon.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
