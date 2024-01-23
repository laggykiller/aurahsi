# aurahsi
Reports up-to-date HSI by Frieren & Aura GIF

https://hsi.auraria.org/hsi.gif?window=1D

## Start server
To use: `docker compose up`

To view the gif, visit `localhost:8080/hsi.gif`

You may also pass `window` query to view HSI in other time period: `localhost:8080/hsi.gif?window=1D`

Valid `window` values are: `MAX`, `5Y`, `1Y`, `YTD`, `6M`, `1M`, `5D`, `1D`

## Generate gif directly without starting server
``` python
from app import ImageOperation

im_op = ImageOperation()
im = im_op.get_img(window="1Y")
with open("hsi.gif", "wb+") as f:
    f.write(im)
im_op.cleanup()
```

## Credits
Original GIF creator: https://lih.kg/BohkeBX