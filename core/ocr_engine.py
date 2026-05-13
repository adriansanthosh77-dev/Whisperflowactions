"""
ocr_engine.py — Backward-compatible wrapper around ocr_adapter.py
"""
from core.ocr_adapter import OCRAdapter, get_ocr_engine, ocr_image, ocr_text

WindowsOCREngine = OCRAdapter

__all__ = ["WindowsOCREngine", "get_ocr_engine", "ocr_image", "ocr_text"]
