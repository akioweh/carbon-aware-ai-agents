from itertools import product

import pandas as pd

# --- DATA-BACKED CONSTANTS ---
HW_LIB = {
    "V100_PCIE": {"gpu_tdp": 250, "gpu_idle": 35, "bus_gbps": 12, "sys_base": 150},
    "A100_SXM4": {"gpu_tdp": 400, "gpu_idle": 55, "bus_gbps": 25, "sys_base": 230},
}

# Physical Phase Modifiers (Ref: SPECpower server benchmarks)
FAN_SURGE_COEFF = 2.5  # Fans draw ~250% power during BIOS/POST
CONTAINER_LOAD_W = 100  # Extra CPU wattage for decompressing/loading weights
TRANSFER_EFFICIENCY = 0.45  # System draws ~45% of max power during DMA transfers

# =============================================================================
# CALCULATION ENGINE
# =============================================================================


def get_full_power_kw(gpu_type, count):
    """Calculates peak training power (P_full)"""
    h = HW_LIB[gpu_type]
    return ((count * h["gpu_tdp"]) + h["sys_base"]) / 1000.0


def get_startup_energy_kwh(gpu_type, count):
    """
    Calculates E_base: BIOS POST (2m) + OS/Driver Init (2m)
    Includes GPU idle draw during enumeration as requested.
    """
    h = HW_LIB[gpu_type]

    # 1. BIOS/POST Phase: High Fan draw, CPU/GPU at Idle
    p_bios = (
        (h["sys_base"] * 0.8)
        + (h["sys_base"] * 0.2 * FAN_SURGE_COEFF)
        + (count * h["gpu_idle"])
    )
    e_bios = (p_bios / 1000.0) * (2.0 / 60.0)

    # 2. OS/Driver Phase: CPU working + GPU enumerated
    p_os = h["sys_base"] + CONTAINER_LOAD_W + (count * h["gpu_idle"])
    e_os = (p_os / 1000.0) * (2.0 / 60.0)

    return round(e_bios + e_os, 4)


def get_load_energy_kwh(model_gb, gpu_type, p_full_kw):
    """Calculates E_load: Energy to move weights into VRAM"""
    h = HW_LIB[gpu_type]
    p_load = p_full_kw * TRANSFER_EFFICIENCY
    transfer_time_hr = (model_gb / h["bus_gbps"]) / 3600
    return round(p_load * transfer_time_hr, 4)


# =============================================================================
# SCENARIO GENERATION
# =============================================================================

models = [
    {"name": "BERT-L", "gb": 3},
    {"name": "Llama7B", "gb": 14},
    {"name": "Llama13B", "gb": 26},
]
configs = [
    {"id": "V100-1x", "type": "V100_PCIE", "n": 1},
    {"id": "A100-1x", "type": "A100_SXM4", "n": 1},
    {"id": "A100-2x", "type": "A100_SXM4", "n": 2},
]


def get_test_scenarios():
    results = []
    for m, c in product(models, configs):
        p_full = get_full_power_kw(c["type"], c["n"])
        e_base = get_startup_energy_kwh(c["type"], c["n"])
        e_load = get_load_energy_kwh(m["gb"], c["type"], p_full)

        results.append(
            {
                "Scenario_ID": f"{m['name']}_{c['id']}",
                "Model": m["name"],
                "System": c["id"],
                "P_Full_kW": p_full,
                "E_Base_kWh": e_base,
                "E_Load_kWh": e_load,
                "Total_Tax_kWh": round(e_base + e_load, 4),
            }
        )
    return pd.DataFrame(results)


if __name__ == "__main__":
    print(get_test_scenarios())
