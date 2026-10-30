"""Read the GPS position a camera stored in a photo's EXIF data."""
import math

from PIL import ExifTags, Image, UnidentifiedImageError

# Tags inside the GPS block of the EXIF data
LAT_REF, LAT, LNG_REF, LNG = 1, 2, 3, 4


def _degrees(dms, ref):
    """(degrees, minutes, seconds) plus N/S/E/W to signed decimal degrees."""
    d, m, s = (float(x) for x in dms)
    value = d + m / 60 + s / 3600
    return -value if ref in ("S", "W") else value


def photo_gps(file):
    """Return (latitude, longitude) from the photo, or None if it has no usable GPS."""
    try:
        with Image.open(file) as img:
            gps = img.getexif().get_ifd(ExifTags.IFD.GPSInfo)
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    finally:
        file.seek(0)    # leave the upload readable for saving

    if LAT not in gps or LNG not in gps:
        return None
    try:
        lat = _degrees(gps[LAT], gps.get(LAT_REF, "N"))
        lng = _degrees(gps[LNG], gps.get(LNG_REF, "E"))
    except (TypeError, ValueError, ZeroDivisionError):
        return None

    if not (math.isfinite(lat) and math.isfinite(lng)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    if lat == 0 and lng == 0:   # cameras write 0,0 when they had no fix
        return None
    return round(lat, 6), round(lng, 6)
