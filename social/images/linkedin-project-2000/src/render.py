import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image
with sync_playwright() as p:
    b=p.chromium.launch()
    pg=b.new_page(viewport={"width":1200,"height":630},device_scale_factor=2)
    for name in sys.argv[1:]:
        pg.goto(Path(name+".html").resolve().as_uri()); pg.wait_for_timeout(300)
        pg.screenshot(path=name+"@2x.png")
        im=Image.open(name+"@2x.png").convert("RGB")
        im.resize((1200,630),Image.Resampling.LANCZOS).save(name+".png")
    b.close()
