"""
ocr_adapter.py — Cross-platform OCR abstraction.

Uses platform-native OCR engines:
- Windows: Windows.Media.Ocr via PowerShell
- macOS: VNRecognizeTextRequest via osascript (JavaScript for Automation)
- Linux: pytesseract (Tesseract OCR)
"""

import os
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional
from core.platform_utils import IS_WINDOWS, IS_MAC, IS_LINUX

logger = logging.getLogger(__name__)


# ── Windows OCR (PowerShell + WinRT) ──────────────────────────────

WINDOWS_OCR_SCRIPT = r"""
param([string]$ImagePath)

Add-Type -As System.Windows.Runtime -ErrorAction Stop

$asyncOp = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$engine = $asyncOp

$stream = [System.IO.File]::OpenRead($ImagePath)
$decoder = [System.Windows.Media.Imaging.BitmapDecoder]::Create($stream, [System.Windows.Media.Imaging.BitmapCreateOptions]::None, [System.Windows.Media.Imaging.BitmapCacheOption]::OnLoad)
$frame = $decoder.Frames[0]

$result = $engine.RecognizeAsync($frame).GetResults()

$output = @()
foreach ($line in $result.Lines) {
    $lineText = @()
    $lineWords = @()
    foreach ($word in $line.Words) {
        $lineText += $word.Text
        $lineWords += @{
            Text = $word.Text
            X = [int]$word.BoundingRect.X
            Y = [int]$word.BoundingRect.Y
            Width = [int]$word.BoundingRect.Width
            Height = [int]$word.BoundingRect.Height
        }
    }
    $output += @{
        Line = $lineText -join ' '
        Words = $lineWords
    }
}
if (-not $output) { return '[]' }
return ($output | ConvertTo-Json)
"""


def _ocr_windows(image_path: str) -> Optional[List[Dict]]:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", f"$ImagePath = '{image_path}'; {WINDOWS_OCR_SCRIPT}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            logger.warning(f"Windows OCR failed: {result.stderr[:200]}")
            return None
        if result.stdout.strip() in ("", "[]"):
            return []
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logger.error(f"Windows OCR JSON parse error: {e}")
        return None
    except Exception as e:
        logger.warning(f"Windows OCR error: {e}")
        return None


# ── macOS OCR (Vision Framework via osascript) ────────────────────

MACOS_OCR_SCRIPT = r"""
on run argv
    set imagePath to item 1 of argv
    set imageData to (read file imagePath as picture)
    set theResult to do shell script "echo 'ocr not available via osascript'"
    return theResult
end run
"""


def _ocr_macos(image_path: str) -> Optional[List[Dict]]:
    try:
        swift_code = """
import Foundation
import Vision

guard CommandLine.arguments.count > 1 else { print("[]"); exit(0) }
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let image = NSImage(contentsOf: url) else { print("[]"); exit(1) }
guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { print("[]"); exit(1) }

let request = VNRecognizeTextRequest { request, error in
    guard let observations = request.results as? [VNRecognizedTextObservation] else { print("[]"); exit(0) }
    let results = observations.compactMap { obs -> [String: Any]? in
        guard let top = obs.topCandidates(1).first else { return nil }
        return ["text": top.string]
    }
    if let data = try? JSONSerialization.data(withJSONObject: results) {
        FileHandle.standardOutput.write(data)
    }
}
request.recognitionLevel = .accurate
try? VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
"""
        swift_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".swift", delete=False
        )
        swift_file.write(swift_code)
        swift_file.close()

        result = subprocess.run(
            ["swift", swift_file.name, image_path],
            capture_output=True, text=True, timeout=30,
        )
        os.unlink(swift_file.name)

        if result.returncode != 0:
            logger.warning(f"macOS OCR failed: {result.stderr[:200]}")
            return None
        if result.stdout.strip() in ("", "[]"):
            return []
        return json.loads(result.stdout)
    except FileNotFoundError:
        logger.warning("Swift not available on this macOS system")
        return None
    except Exception as e:
        logger.warning(f"macOS OCR error: {e}")
        return None


# ── Linux OCR (pytesseract) ───────────────────────────────────────

def _ocr_linux(image_path: str) -> Optional[List[Dict]]:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(image_path)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        results = []
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            if text:
                results.append({
                    "Text": text,
                    "X": data["left"][i],
                    "Y": data["top"][i],
                    "Width": data["width"][i],
                    "Height": data["height"][i],
                })
        return results
    except ImportError:
        logger.warning("pytesseract not installed. Install with: pip install pytesseract Pillow")
        return None
    except Exception as e:
        logger.warning(f"Linux OCR error: {e}")
        return None


# ── OCR Adapter ───────────────────────────────────────────────────

def ocr_image(image_path: str) -> List[Dict]:
    """
    Extract text from an image using the best available OCR engine.
    Returns list of dicts with Text, X, Y, Width, Height.
    Returns empty list on failure.
    """
    if not os.path.exists(image_path):
        logger.error(f"Image not found: {image_path}")
        return []

    result = None
    if IS_WINDOWS:
        result = _ocr_windows(image_path)
        if result is not None:
            return result
        logger.info("Windows OCR failed, falling back to pytesseract...")
        result = _ocr_linux(image_path)
        return result if result is not None else []

    elif IS_MAC:
        result = _ocr_macos(image_path)
        if result is not None:
            return result
        logger.info("macOS Vision OCR failed, falling back to pytesseract...")
        result = _ocr_linux(image_path)
        return result if result is not None else []

    elif IS_LINUX:
        result = _ocr_linux(image_path)
        return result if result is not None else []

    return []


def ocr_text(image_path: str) -> str:
    """Extract plain text from an image."""
    words = ocr_image(image_path)
    return " ".join(item.get("Text", "") for item in words)


# ── Text-on-Screen Search ──────────────────────────────────────────

def find_text_on_screen(text_query: str, image_path: Optional[str] = None) -> Optional[dict]:
    """
    Find text on screen and return its center coordinates (x, y).
    Takes a screenshot if no image_path provided.
    Returns dict with x, y, width, height, text if found, None otherwise.
    """
    if not image_path:
        from core.platform_utils import capture_screenshot
        image_path = "data/find_text_screenshot.png"
        os.makedirs("data", exist_ok=True)
        if not capture_screenshot(image_path):
            return None

    results = ocr_image(image_path)
    if not results:
        return None

    query_lower = text_query.lower().strip()
    for r in results:
        text = r.get("Text", "").lower().strip()
        if query_lower in text:
            x = r.get("X", 0)
            y = r.get("Y", 0)
            w = r.get("Width", 0)
            h = r.get("Height", 0)
            return {
                "x": x + w // 2,
                "y": y + h // 2,
                "width": w,
                "height": h,
                "text": r.get("Text", ""),
            }

    for r in results:
        text = r.get("Text", "").lower().strip()
        from rapidfuzz import fuzz
        if fuzz.partial_ratio(query_lower, text) > 80:
            x = r.get("X", 0)
            y = r.get("Y", 0)
            w = r.get("Width", 0)
            h = r.get("Height", 0)
            return {
                "x": x + w // 2,
                "y": y + h // 2,
                "width": w,
                "height": h,
                "text": r.get("Text", ""),
            }

    return None


# ── Keep backward compat with ocr_engine.py interface ─────────────

_OCR_ENGINE = None


def get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        _OCR_ENGINE = OCRAdapter()
    return _OCR_ENGINE


class OCRAdapter:
    def recognize(self, image_path: str) -> List[Dict]:
        return ocr_image(image_path)

    def text(self, image_path: str) -> str:
        return ocr_text(image_path)

    def find_text(self, text_query: str, image_path: Optional[str] = None) -> Optional[dict]:
        return find_text_on_screen(text_query, image_path)
