"""
doctor.py — Cross-platform diagnostics for JARVIS runtime health.

Run:
  python -m core.doctor
"""

from __future__ import annotations

import os
import sys
import time
import importlib.util
import subprocess
from dataclasses import dataclass

from core.platform_utils import IS_WINDOWS, IS_MAC, IS_LINUX


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _status(check: Check) -> str:
    marker = "OK" if check.ok else "FAIL"
    return f"[{marker}] {check.name}: {check.detail}"


def check_imports() -> Check:
    missing = []
    for module in ("sounddevice", "faster_whisper", "pyperclip", "rapidfuzz", "pynput"):
        if importlib.util.find_spec(module) is None:
            missing.append(module)
    if missing:
        return Check("Python dependencies", False, "missing: " + ", ".join(missing))
    return Check("Python dependencies", True, "all modules import successfully")


def check_audio_devices() -> Check:
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        configured = os.getenv("MICROPHONE_INDEX", "").strip()
        inputs = []
        for index, device in enumerate(devices):
            if device.get("max_input_channels", 0) <= 0:
                continue
            host = ""
            try:
                host = sd.query_hostapis(device["hostapi"])["name"]
            except Exception:
                pass
            inputs.append((index, device["name"], host))

        if not inputs:
            return Check("Microphone", False, "no input devices found")

        if configured:
            try:
                idx = int(configured)
                match = next((item for item in inputs if item[0] == idx), None)
                if match:
                    return Check("Microphone", True, f"MICROPHONE_INDEX={idx} -> {match[1]} ({match[2]})")
                return Check("Microphone", False, f"MICROPHONE_INDEX={idx} is not an input device")
            except ValueError:
                return Check("Microphone", False, f"MICROPHONE_INDEX is not a number: {configured}")

        avoid = ("hands-free", "ag audio", "stereo mix", "virtual", "loopback")
        clean = [item for item in inputs if not any(bad in item[1].lower() for bad in avoid)]
        recommended = clean[0] if clean else inputs[0]
        detail = f"{len(inputs)} found; recommended MICROPHONE_INDEX={recommended[0]} ({recommended[1]}, {recommended[2]})"
        return Check("Microphone", True, detail)
    except Exception as e:
        return Check("Microphone", False, str(e)[:160])


def check_stt_config() -> Check:
    short = os.getenv("STT_MODEL_SHORT", "tiny.en")
    long_m = os.getenv("STT_MODEL_LONG", "medium.en")
    lang = os.getenv("WHISPER_LANGUAGE", "en")
    threads = os.getenv("STT_THREADS", str(os.cpu_count() or 4))
    return Check("STT config", True, f"short={short}, long={long_m}, lang={lang}, threads={threads}")


def check_ollama() -> Check:
    try:
        import requests
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        start = time.time()
        resp = requests.get(f"{base_url}/api/tags", timeout=2)
        elapsed = time.time() - start
        resp.raise_for_status()
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        configured = os.getenv("OLLAMA_MODEL", "")
        if configured and configured not in models and f"{configured}:latest" not in models:
            return Check("Ollama", False, f"running, but '{configured}' not installed. Available: {models[:6]}")
        return Check("Ollama", True, f"reachable in {elapsed:.2f}s; {len(models)} model(s): {models[:6]}")
    except Exception as e:
        return Check("Ollama", False, str(e)[:180])


def check_gpu() -> Check:
    """Detect GPU availability for STT acceleration."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            return Check("GPU", True, f"CUDA: {name}")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return Check("GPU", True, "MPS (Apple Silicon)")
        return Check("GPU", False, "CPU only (no CUDA/MPS) — Int8 quantization active")
    except ImportError:
        return Check("GPU", False, "torch not installed — CPU only")


def check_api_keys() -> Check:
    providers = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "").strip(),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", "").strip(),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", "").strip(),
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY", "").strip(),
    }
    present = [key for key, value in providers.items() if value and not value.endswith("...")]
    if present:
        return Check("API keys", True, "configured: " + ", ".join(present))
    return Check("API keys", False, "no cloud provider keys configured")


def check_system() -> Check:
    """Cross-platform OS and hardware summary."""
    bits = "64bit" if sys.maxsize > 2 ** 32 else "32bit"
    python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    try:
        ram = None
        if IS_WINDOWS:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)"],
                capture_output=True, text=True, timeout=5,
            )
            if r.stdout.strip():
                ram = r.stdout.strip() + " GB"
        elif IS_MAC:
            r = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
            if r.stdout.strip().isdigit():
                ram = f"{int(r.stdout.strip()) / (1024**3):.1f} GB"
        elif IS_LINUX:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        ram = f"{kb / (1024 * 1024):.1f} GB"
                        break
    except Exception:
        pass

    detail = f"Python {python_ver} ({bits})"
    if ram:
        detail += f", RAM: {ram}"
    return Check("System", True, detail)


def run_checks() -> list[Check]:
    return [
        check_system(),
        check_imports(),
        check_audio_devices(),
        check_stt_config(),
        check_gpu(),
        check_ollama(),
        check_api_keys(),
    ]


def main() -> int:
    checks = run_checks()
    print("JARVIS Doctor")
    print("=" * 40)
    for check in checks:
        print(_status(check))
    print()
    failed = [c for c in checks if not c.ok]
    if failed:
        print(f"{len(failed)} check(s) need attention")
        return 1
    print("All systems nominal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
