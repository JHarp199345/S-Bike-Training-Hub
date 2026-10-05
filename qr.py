"""Portable pairing QR codes. Rendering requires no graphics driver or desktop UI."""

def matrix(text, level="M"):
    """Rows of dark-module booleans, with no quiet zone (SVG adds one)."""
    import qrcode
    levels={"L":qrcode.constants.ERROR_CORRECT_L,"M":qrcode.constants.ERROR_CORRECT_M,
            "Q":qrcode.constants.ERROR_CORRECT_Q,"H":qrcode.constants.ERROR_CORRECT_H}
    if level not in levels: raise ValueError("Unknown QR correction level")
    code=qrcode.QRCode(error_correction=levels[level],box_size=1,border=0)
    code.add_data(text);code.make(fit=True)
    return code.get_matrix()


def svg(text, size=240, margin=4):
    """Crisp SVG with a four-module quiet zone for phone cameras."""
    m=matrix(text);n=len(m)+2*margin
    cells="".join(f'<rect x="{x+margin}" y="{y+margin}" width="1" height="1"/>'
                  for y,row in enumerate(m) for x,dark in enumerate(row) if dark)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{size}" height="{size}" '
            f'shape-rendering="crispEdges"><rect width="{n}" height="{n}" fill="#fff"/><g fill="#000">{cells}</g></svg>')


def decode_matrix(m, scale=10, margin=4):
    """Independent OpenCV decoder for verification; never used while pairing."""
    import cv2
    import numpy as np
    image=np.where(np.array(m,dtype=bool),0,255).astype(np.uint8)
    image=np.pad(image,margin,constant_values=255).repeat(scale,axis=0).repeat(scale,axis=1)
    text,_,_=cv2.QRCodeDetector().detectAndDecode(image)
    return text or None
