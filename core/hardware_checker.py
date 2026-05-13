"""
hardware_checker.py — Cross-platform system hardware detection.

Supports Windows (WMI), macOS (sysctl/system_profiler), and Linux (/proc, nvidia-smi).
"""

import os
import json
import logging
import subprocess
from typing import Dict, Tuple
from core.platform_utils import IS_WINDOWS, IS_MAC, IS_LINUX

logger = logging.getLogger(__name__)


def get_system_specs() -> Dict[str, any]:
    specs = {"ram_gb": 0.0, "gpus": [], "max_vram_gb": 0.0}

    if IS_WINDOWS:
        specs = _specs_windows(specs)
    elif IS_MAC:
        specs = _specs_macos(specs)
    elif IS_LINUX:
        specs = _specs_linux(specs)

    return specs


def _specs_windows(specs: Dict) -> Dict:
    """Windows: WMI via PowerShell."""
    try:
        ram = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum"],
            capture_output=True, text=True, timeout=10,
        )
        if ram.stdout.strip().isdigit():
            specs["ram_gb"] = round(int(ram.stdout.strip()) / (1024 ** 3), 2)
    except Exception as e:
        logger.debug(f"Windows RAM detection failed: {e}")

    try:
        gpu = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object AdapterRAM, Name | ConvertTo-Json"],
            capture_output=True, text=True, timeout=10,
        )
        if gpu.stdout.strip():
            gpus = json.loads(gpu.stdout)
            if isinstance(gpus, dict):
                gpus = [gpus]
            for gpu_info in gpus:
                ram_bytes = gpu_info.get("AdapterRAM")
                name = gpu_info.get("Name", "Unknown GPU")
                vram = round(int(ram_bytes) / (1024 ** 3), 2) if ram_bytes else 0.0
                specs["gpus"].append({"name": name, "vram_gb": vram})
                if vram > specs["max_vram_gb"]:
                    specs["max_vram_gb"] = vram
    except Exception as e:
        logger.debug(f"Windows GPU detection failed: {e}")

    return specs


def _specs_macos(specs: Dict) -> Dict:
    """macOS: sysctl for RAM, system_profiler for GPU."""
    try:
        ram = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True, text=True, timeout=5,
        )
        if ram.stdout.strip().isdigit():
            specs["ram_gb"] = round(int(ram.stdout.strip()) / (1024 ** 3), 2)
    except Exception as e:
        logger.debug(f"macOS RAM detection failed: {e}")

    try:
        gpu = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True, text=True, timeout=10,
        )
        if gpu.stdout.strip():
            data = json.loads(gpu.stdout)
            for item in data.get("SPDisplaysDataType", []):
                name = item.get("sppci_model", item.get("_name", "Unknown GPU"))
                vram_str = item.get("spdisplays_vram", "0").split()[0]
                try:
                    vram = float(vram_str) if vram_str else 0.0
                except ValueError:
                    vram = 0.0
                specs["gpus"].append({"name": name, "vram_gb": vram})
                if vram > specs["max_vram_gb"]:
                    specs["max_vram_gb"] = vram
    except Exception as e:
        logger.debug(f"macOS GPU detection failed: {e}")

    return specs


def _specs_linux(specs: Dict) -> Dict:
    """Linux: /proc/meminfo for RAM, nvidia-smi for GPU."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    specs["ram_gb"] = round(kb / (1024 * 1024), 2)
                    break
    except Exception as e:
        logger.debug(f"Linux RAM detection failed: {e}")

    try:
        nvidia = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if nvidia.returncode == 0:
            for line in nvidia.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    name = parts[0]
                    try:
                        vram = round(float(parts[1]) / 1024, 2)
                    except ValueError:
                        vram = 0.0
                    specs["gpus"].append({"name": name, "vram_gb": vram})
                    if vram > specs["max_vram_gb"]:
                        specs["max_vram_gb"] = vram
    except Exception as e:
        logger.debug(f"Linux GPU detection failed: {e}")

    return specs


def check_model_hardware_compatibility(model_name: str, is_image_gen: bool = False) -> Tuple[bool, str]:
    specs = get_system_specs()
    ram = specs.get("ram_gb", 0)
    vram = specs.get("max_vram_gb", 0)

    if ram == 0:
        return True, ""

    m = model_name.lower()

    if is_image_gen:
        if vram < 4.0 and ram < 32.0:
            return False, (
                f"Hardware Warning: Local Image Generation requires at least 4GB VRAM "
                f"or 32GB RAM. Your system has {vram}GB VRAM and {ram}GB RAM."
            )
        return True, ""

    if "70b" in m or "72b" in m:
        if ram < 32.0:
            return False, f"Model '{model_name}' (70B+) requires 32GB+ RAM. Your system has {ram}GB RAM."
    elif "32b" in m or "34b" in m or "mixtral" in m:
        if ram < 24.0:
            return False, f"Model '{model_name}' (30B+) requires 24GB+ RAM. Your system has {ram}GB RAM."
    elif "14b" in m or "coder" in m or "13b" in m:
        if ram < 16.0:
            return False, f"Model '{model_name}' (14B+) recommended 16GB+ RAM. Your system has {ram}GB RAM."
    elif "7b" in m or "8b" in m:
        if ram < 8.0:
            return False, f"Model '{model_name}' (7B+) requires 8GB+ RAM. Your system has {ram}GB RAM."

    return True, ""
