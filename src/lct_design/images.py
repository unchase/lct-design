"""Inline image contract: no network fetches or arbitrary local paths."""
import base64,io,re
from PIL import Image

def decode_image(uri):
    if len(uri)>12*1024**2:raise ValueError('Image must be at most 8 MB')
    match=re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=\r\n]+)',uri)
    if not match:raise ValueError('Image must be a PNG/JPEG data URI; URLs and paths are not accepted')
    try:
        data=base64.b64decode(match[2],validate=True)
        if len(data)>8*1024**2:raise ValueError('Image must be at most 8 MB')
        with Image.open(io.BytesIO(data)) as im:
            width,height=im.size
            if im.format not in ('PNG','JPEG') or width*height>25_000_000:raise ValueError('Unsupported image or too many pixels')
            im.verify()
    except Exception as exc:raise ValueError('Invalid or oversized PNG/JPEG image') from exc
    return data,match[1],width,height
