from itertools import product
from typing import TypedDict

import pandas as pd


# --- TYPE DEFINITIONS ---
class HardwareSpecs(TypedDict):
    gpu_tdp: int
    gpu_idle: int
    bus_gbps: int
    sys_base: int


class ModelConfig(TypedDict):
    name: str
    gb: int


class SystemConfig(TypedDict):
    id: str
    type: str
    n: int


class TestConfig(TypedDict):
    model: ModelConfig
    system: SystemConfig
    config_id: str
    full_power: float
    startup_overhead: float


# --- DATA-BACKED CONSTANTS ---
HW_LIB: dict[str, HardwareSpecs] = {
    "V100_PCIE": {"gpu_tdp": 250, "gpu_idle": 35, "bus_gbps": 12, "sys_base": 150},
    "A100_SXM4": {"gpu_tdp": 400, "gpu_idle": 55, "bus_gbps": 25, "sys_base": 230},
}

FAN_SURGE_COEFF: float = 2.5
CONTAINER_LOAD_W: int = 100
TRANSFER_EFFICIENCY: float = 0.45

# =============================================================================
# CALCULATION ENGINE
# =============================================================================

ROUNDING_PRECISION: int = 6


def get_full_power_kw(gpu_type: str, count: int) -> float:
    """Calculates peak training power (P_full)"""
    h: HardwareSpecs = HW_LIB[gpu_type]
    return ((count * h["gpu_tdp"]) + h["sys_base"]) / 1000.0


def get_startup_energy_kwh(gpu_type: str, count: int) -> float:
    """
    Calculates E_base: BIOS POST (2m) + OS/Driver Init (2m)
    """
    h: HardwareSpecs = HW_LIB[gpu_type]

    # 1. BIOS/POST Phase
    p_bios: float = (
        (h["sys_base"] * 0.8)
        + (h["sys_base"] * 0.2 * FAN_SURGE_COEFF)
        + (count * h["gpu_idle"])
    )
    e_bios: float = (p_bios / 1000.0) * (2.0 / 60.0)

    # 2. OS/Driver Phase
    p_os: float = h["sys_base"] + CONTAINER_LOAD_W + (count * h["gpu_idle"])
    e_os: float = (p_os / 1000.0) * (2.0 / 60.0)

    return round(e_bios + e_os, ROUNDING_PRECISION)


def get_load_energy_kwh(model_gb: float, gpu_type: str, p_full_kw: float) -> float:
    """Calculates E_load: Energy to move weights into VRAM"""
    h: HardwareSpecs = HW_LIB[gpu_type]
    p_load: float = p_full_kw * TRANSFER_EFFICIENCY
    transfer_time_hr: float = (model_gb / h["bus_gbps"]) / 3600.0
    return round(p_load * transfer_time_hr, ROUNDING_PRECISION)


# =============================================================================
# SCENARIO GENERATION
# =============================================================================

models: list[ModelConfig] = [
    {"name": "Llama7B", "gb": 14},
    {"name": "Llama-3-70B", "gb": 140},
]

configs: list[SystemConfig] = [
    {"id": "V100-5x", "type": "V100_PCIE", "n": 5},
    {"id": "A100-10x", "type": "A100_SXM4", "n": 10},
    {"id": "A100-15x", "type": "A100_SXM4", "n": 15},
    {"id": "A100-20x", "type": "A100_SXM4", "n": 20},
    {"id": "V100-30x", "type": "V100_PCIE", "n": 30},
    {"id": "V100-40x", "type": "V100_PCIE", "n": 40},
    {"id": "V100-50x", "type": "V100_PCIE", "n": 50},
]


def get_test_configs() -> list[TestConfig]:
    results: list[TestConfig] = []

    # Typed unpacking for the product iterator
    m: ModelConfig
    c: SystemConfig

    for m, c in product(models, configs):
        p_full: float = get_full_power_kw(c["type"], c["n"])
        e_base: float = get_startup_energy_kwh(c["type"], c["n"])
        e_load: float = get_load_energy_kwh(m["gb"], c["type"], p_full)

        results.append(
            {
                "config_id": f"{m['name']}_{c['id']}",
                "model": m,
                "system": c,
                "full_power": p_full,
                "startup_overhead": round(e_base + e_load, ROUNDING_PRECISION),
            }
        )
    return results


if __name__ == "__main__":
    df = get_test_configs()
    pd.set_option("display.max_columns", None)  # Show all columns
    pd.set_option("display.width", 1000)  # Increase terminal width
    print(df)
