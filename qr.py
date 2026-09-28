"""qr.py - QR codes from macOS itself (Core Image's CIQRCodeGenerator), as SVG.

No library to install: AppKit (already here for the menu icon) loads Core
Image, whose QR generator gives a tiny bitmap - one pixel per module - that
this turns into crisp SVG squares. decode() reads a QR back with Core Image's
detector, so tests can prove each code scans to the right link.
"""
import objc
import AppKit
import Foundation


def matrix(text, level="M"):
    """Rows of booleans (True = dark module), including the generator's quiet margin."""
    f = objc.lookUpClass("CIFilter").filterWithName_("CIQRCodeGenerator")
    raw = text.encode("utf-8")
    f.setValue_forKey_(Foundation.NSData.dataWithBytes_length_(raw, len(raw)), "inputMessage")
    f.setValue_forKey_(level, "inputCorrectionLevel")
    img = f.valueForKey_("outputImage")
    ci_rep = AppKit.NSCIImageRep.imageRepWithCIImage_(img)
    w, h = int(ci_rep.pixelsWide()), int(ci_rep.pixelsHigh())
    bmp = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, w, h, 8, 4, True, False, AppKit.NSDeviceRGBColorSpace, 0, 0)
    ctx = AppKit.NSGraphicsContext.graphicsContextWithBitmapImageRep_(bmp)
    ctx.setImageInterpolation_(AppKit.NSImageInterpolationNone)
    AppKit.NSGraphicsContext.saveGraphicsState()
    AppKit.NSGraphicsContext.setCurrentContext_(ctx)
    ci_rep.drawInRect_(AppKit.NSMakeRect(0, 0, w, h))
    AppKit.NSGraphicsContext.restoreGraphicsState()
    return [[bmp.colorAtX_y_(x, y).brightnessComponent() < 0.5 for x in range(w)] for y in range(h)]


def svg(text, size=240, margin=3):
    """A QR as an SVG string: black squares on white, with a quiet zone that phones need."""
    m = matrix(text)
    n = len(m) + 2 * margin
    cells = "".join(f'<rect x="{x + margin}" y="{y + margin}" width="1" height="1"/>'
                    for y, row in enumerate(m) for x, dark in enumerate(row) if dark)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{size}" height="{size}" '
            f'shape-rendering="crispEdges"><rect width="{n}" height="{n}" fill="#fff"/><g fill="#000">{cells}</g></svg>')


def decode_matrix(m, scale=10, margin=4):
    """Read a matrix back with Core Image's QR detector (for tests)."""
    n = (len(m) + 2 * margin) * scale
    bmp = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, n, n, 8, 4, True, False, AppKit.NSDeviceRGBColorSpace, 0, 0)
    ctx = AppKit.NSGraphicsContext.graphicsContextWithBitmapImageRep_(bmp)
    AppKit.NSGraphicsContext.saveGraphicsState()
    AppKit.NSGraphicsContext.setCurrentContext_(ctx)
    AppKit.NSColor.whiteColor().set()
    AppKit.NSBezierPath.fillRect_(AppKit.NSMakeRect(0, 0, n, n))
    AppKit.NSColor.blackColor().set()
    for y, row in enumerate(m):
        for x, dark in enumerate(row):
            if dark:
                AppKit.NSBezierPath.fillRect_(AppKit.NSMakeRect((x + margin) * scale, n - (y + margin + 1) * scale, scale, scale))
    AppKit.NSGraphicsContext.restoreGraphicsState()
    ci = objc.lookUpClass("CIImage").alloc().initWithBitmapImageRep_(bmp)
    det = objc.lookUpClass("CIDetector").detectorOfType_context_options_("CIDetectorTypeQRCode", None,
                                                                       {"CIDetectorAccuracy": "CIDetectorAccuracyHigh"})
    feats = det.featuresInImage_(ci)
    return str(feats[0].messageString()) if feats and len(feats) else None
