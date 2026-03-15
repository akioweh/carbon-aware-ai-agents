# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
import json
import os
from typing import Optional

import matplotlib.pyplot as plt
import seaborn as sns
from tabulate import tabulate

from running_tests import TestResult, run_tests
from test_setups import get_full_power_kw


def filter_results(
    results: list[TestResult],
    window_size_hours: Optional[int] = None,
    config_id: Optional[str] = None,
    system_id: Optional[str] = None,
    comp_length_mins: Optional[int] = None,
) -> list[TestResult]:
    """Helper method to slice the results exactly how we need them for each graph."""
    filtered: list[TestResult] = []
    r: TestResult
    for r in results:
        if (
            window_size_hours is not None
            and r["window_size_hours"] != window_size_hours
        ):
            continue
        if config_id is not None and r["config_id"] != config_id:
            continue
        if system_id is not None and r["system_id"] != system_id:
            continue
        if (
            comp_length_mins is not None
            and r["workload_length_mins"] != comp_length_mins
        ):
            continue
        filtered.append(r)
    return filtered


# =============================================================================
# GRAPH 1: Original Baseline
# =============================================================================
def plot_emissions_vs_execution_time(
    results: list[TestResult], output_dir: str
) -> None:
    # Use 144h as the default maximum scheduling window for these graphs
    filtered_results: list[TestResult] = filter_results(results, window_size_hours=144)
    config_ids: set[str] = {r["config_id"] for r in filtered_results}

    cid: str
    for cid in config_ids:
        cid_results: list[TestResult] = filter_results(filtered_results, config_id=cid)
        cid_results.sort(key=lambda x: x["workload_length_mins"])

        x_axis: list[int] = [r["workload_length_mins"] for r in cid_results]
        y_sdk: list[float] = [r["sdk_emissions"] for r in cid_results]
        y_our: list[float] = [r["our_emissions"] for r in cid_results]

        plt.figure(figsize=(10, 6))
        plt.plot(
            x_axis,
            y_sdk,
            marker="o",
            linestyle="-",
            linewidth=2,
            label="SDK (Baseline)",
        )
        plt.plot(
            x_axis, y_our, marker="s", linestyle="-", linewidth=2, label="Our Software"
        )

        plt.title(
            f"Carbon Emissions vs. Execution Time\nSetup: {cid} (144h Window)",
            fontsize=14,
            fontweight="bold",
        )
        plt.xlabel("Execution Time (minutes)", fontsize=12)
        plt.ylabel("Carbon Emissions (kg CO2eq)", fontsize=12)
        plt.legend(fontsize=12)
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.tight_layout()

        safe_filename: str = f"01_base_{cid.replace(' ', '_').replace('/', '_')}.png"
        filepath: str = os.path.join(output_dir, safe_filename)
        plt.savefig(filepath, dpi=300)
        plt.close()


# =============================================================================
# GRAPH 2: Increasing Model Size Effect
# =============================================================================
def plot_emissions_vs_model_size(results: list[TestResult], output_dir: str) -> None:
    target_sys: str = "V100-5x"
    target_len: int = 3 * 60 * 5

    filtered: list[TestResult] = filter_results(
        results,
        window_size_hours=48,
        system_id=target_sys,
        comp_length_mins=target_len,
    )
    filtered.sort(key=lambda x: x["model_gb"])

    if not filtered:
        return

    x_vals: list[int] = [r["model_gb"] for r in filtered]
    labels: list[str] = [r["model_name"] for r in filtered]
    sdk_y: list[float] = [r["sdk_emissions"] for r in filtered]
    our_y: list[float] = [r["our_emissions"] for r in filtered]
    for help in our_y:
        print(help)

    plt.figure(figsize=(10, 6))
    """
    plt.plot(
        x_vals,
        sdk_y,
        marker="o",
        linestyle="--",
        linewidth=2,
        label="SDK (Baseline)",
        color="red",
    )
    """
    plt.plot(
        x_vals,
        our_y,
        marker="s",
        linestyle="-",
        linewidth=2,
        label="Our Software",
        color="green",
    )

    # Annotate points with the model name directly on the graph
    i: int
    for i, txt in enumerate(labels):
        """
        plt.annotate(
            txt,
            (x_vals[i], sdk_y[i]),
            textcoords="offset points",
            xytext=(0, 10),
            ha="center",
        )
        """
        plt.annotate(
            txt,
            (x_vals[i], our_y[i]),
            textcoords="offset points",
            xytext=(0, -15),
            ha="center",
        )

    plt.title(
        f"Carbon Emissions vs. Model Size\nSystem: {target_sys} | Length: {target_len}m",
        fontsize=14,
        fontweight="bold",
    )
    plt.xlabel("Model Size (GB)", fontsize=12)
    plt.ylabel("Carbon Emissions (kg CO2eq)", fontsize=12)
    plt.legend(fontsize=12)
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.tight_layout()

    filepath: str = os.path.join(output_dir, "02_model_size_comparison.png")
    plt.savefig(filepath, dpi=300)
    plt.close()


# =============================================================================
# GRAPH 3: Scatter Plot - Rate of Carbon Savings
# =============================================================================
def plot_savings_scatter(results: list[TestResult], output_dir: str) -> None:
    # Filter for a specific scenario so the dots don't overlap too much
    filtered = [
        r
        for r in results
        if r["window_size_hours"] == 144 and r["workload_length_mins"] >= 3 * 60 * 3
    ]

    plt.figure(figsize=(10, 6))
    systems: set[str] = {r["system_id"] for r in filtered}

    for sys_id in systems:
        sys_results: list[TestResult] = filter_results(filtered, system_id=sys_id)

        # X = How long the script took to run (Overhead)
        # Y = How many grams we saved
        x_compute_time: list[float] = []
        y_grams_saved: list[float] = []

        for r in sys_results:
            # Absolute savings in grams (assuming emissions are in kg)
            savings_g: float = r["sdk_emissions"] - r["our_emissions"]

            # The real-world time the Python script spent calculating
            # (X-axis now shows the 'cost' of the software)
            compute_overhead: float = r["our_compute_time_sec"]

            x_compute_time.append(compute_overhead)
            y_grams_saved.append(savings_g)

        plt.scatter(
            x_compute_time, y_grams_saved, label=sys_id, alpha=0.6, edgecolors="w", s=80
        )

    plt.title(
        "Carbon ROI: Savings vs. Scheduler Overhead", fontsize=14, fontweight="bold"
    )
    plt.xlabel("Scheduler Execution Time (seconds)", fontsize=12)
    plt.ylabel("Carbon Saved (grams CO2e)", fontsize=12)

    plt.legend(title="System Config")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()

    plt.savefig(os.path.join(output_dir, "03_savings_vs_overhead_scatter.png"), dpi=300)
    plt.close()


# =============================================================================
# GRAPH 4: Dependency on Schedule End Time (Window Size)
# =============================================================================
def plot_emissions_vs_window_size(results: list[TestResult], output_dir: str) -> None:
    target_config: str = "Llama-3-400B_V100-50x"
    target_len: int = 3 * 60 * 2

    filtered: list[TestResult] = filter_results(
        results, config_id=target_config, comp_length_mins=target_len
    )
    # Ensure they are plotted in chronological window size
    filtered.sort(key=lambda x: x["window_size_hours"])

    if not filtered:
        return

    x_vals: list[int] = [r["window_size_hours"] for r in filtered]
    sdk_y: list[float] = [r["sdk_emissions"] for r in filtered]
    our_y: list[float] = [r["our_emissions"] for r in filtered]

    plt.figure(figsize=(10, 6))
    plt.plot(
        x_vals,
        sdk_y,
        marker="o",
        linestyle="--",
        linewidth=2,
        label="SDK (Baseline)",
        color="red",
    )
    plt.plot(
        x_vals,
        our_y,
        marker="s",
        linestyle="-",
        linewidth=2,
        label="Our Software",
        color="green",
    )

    plt.title(
        f"Emissions vs. Scheduling Deadline Window\nSetup: {target_config} | Workload: {target_len}m",
        fontsize=14,
        fontweight="bold",
    )
    plt.xlabel("Available Time Window (hours into the future)", fontsize=12)
    plt.ylabel("Carbon Emissions (kg CO2eq)", fontsize=12)
    plt.legend(fontsize=12)
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.tight_layout()

    filepath: str = os.path.join(output_dir, "04_window_size_dependency.png")
    plt.savefig(filepath, dpi=300)
    plt.close()


# =============================================================================
# Graph 5: Savings vs Power
# =============================================================================
def plot_savings_vs_power(results: list[TestResult], output_dir: str):
    # Filter for long jobs (9h+)
    filtered = [r for r in results if r["workload_length_mins"] >= 540]

    if not filtered:
        return

    x_power: list[float] = []
    y_savings: list[float] = []

    for r in filtered:
        # Pull metadata directly from the result dict
        gpu_type = r["gpu_type"]
        count = r["gpu_count"]

        # Calculate Watts using your central logic
        wattage = get_full_power_kw(gpu_type, count) * 1000.0

        x_power.append(wattage)
        y_savings.append(r["sdk_emissions"] - r["our_emissions"])

    plt.figure(figsize=(10, 6))
    sns.regplot(
        x=x_power,
        y=y_savings,
        scatter_kws={"alpha": 0.6, "s": 80, "edgecolor": "w"},
        line_kws={"color": "red"},
    )

    plt.title(
        "Carbon Savings ROI vs. System Power Draw", fontsize=14, fontweight="bold"
    )
    plt.xlabel("Theoretical Max Power Draw (Watts)", fontsize=12)
    plt.ylabel("Carbon Saved (grams CO2e)", fontsize=12)
    plt.grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "05_power_correlation.png"), dpi=300)
    plt.close()


# =============================================================================
# Graph 6: PNG ASCII TABLE
# =============================================================================
def generate_savings_table(results: list[TestResult], output_dir: str) -> None:
    # Filter only on the max window size for the summary metrics
    filtered: list[TestResult] = filter_results(results, window_size_hours=144)
    config_ids: set[str] = {r["config_id"] for r in filtered}

    table_data: list[list[str]] = []

    cid: str
    for cid in sorted(config_ids):
        cid_results: list[TestResult] = filter_results(filtered, config_id=cid)

        total_sdk: float = sum(r["sdk_emissions"] for r in cid_results)
        total_our: float = sum(r["our_emissions"] for r in cid_results)

        absolute_savings: float = total_sdk - total_our
        percent_saved: float = (
            (absolute_savings / total_sdk * 100.0) if total_sdk > 0 else 0.0
        )

        table_data.append(
            [
                cid,
                f"{total_sdk:.4f}",
                f"{total_our:.4f}",
                f"{absolute_savings:.4f}",
                f"{percent_saved:.2f}%",
            ]
        )

    headers: list[str] = [
        "Test Setup (Config ID)",
        "Total SDK Emissions",
        "Total Our Emissions",
        "Carbon Saved (Absolute)",
        "% Carbon Saved",
    ]

    print("\n" + "=" * 85)
    print(" CARBON SAVINGS SUMMARY (144h WINDOW) ".center(85, "="))
    print("=" * 85 + "\n")
    print(
        tabulate(table_data, headers=headers, tablefmt="fancy_grid", stralign="center")
    )
    print("\n")

    fig_height: float = max(4.0, len(table_data) * 0.5 + 2.0)
    _, ax = plt.subplots(figsize=(12, fig_height))
    ax.axis("off")
    ax.axis("tight")

    mpl_table = ax.table(
        cellText=table_data, colLabels=headers, loc="center", cellLoc="center"
    )
    mpl_table.auto_set_font_size(False)
    mpl_table.set_fontsize(11)
    mpl_table.scale(1.2, 1.8)

    cell_key: tuple[int, int]
    for cell_key, cell in mpl_table.get_celld().items():
        row_idx: int = cell_key[0]
        if row_idx == 0:
            cell.set_text_props(weight="bold", color="black")
            cell.set_facecolor("#e0e0e0")
        else:
            if row_idx % 2 == 0:
                cell.set_facecolor("#f9f9f9")

    plt.title(
        "Total Carbon Savings per Setup Configuration (144h Window)",
        fontweight="bold",
        fontsize=16,
        pad=20,
    )
    plt.tight_layout()

    table_filepath: str = os.path.join(output_dir, "06_carbon_savings_summary.png")
    plt.savefig(table_filepath, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Saved savings table PNG to: {table_filepath}\n")


CACHE_FILE = "test_results_cache.json"


def main() -> None:
    output_dir: str = "test_graphs"
    os.makedirs(output_dir, exist_ok=True)

    results: list[TestResult]

    # 1. Check if we have cached data
    if os.path.exists(CACHE_FILE):
        print(f"Loading cached results from {CACHE_FILE}...")
        with open(CACHE_FILE, "r") as f:
            results = json.load(f)
    else:
        # 2. Run tests and save to cache
        print("Starting comprehensive test matrix...")
        results = run_tests()
        with open(CACHE_FILE, "w") as f:
            json.dump(results, f, indent=4)
        print(f"Saved results to {CACHE_FILE}.")

    print(f"Test suite finished. Generating {len(results)} metrics worth of graphs...")

    # Execute visualization methods
    plot_emissions_vs_execution_time(results, output_dir)
    plot_emissions_vs_model_size(results, output_dir)
    plot_savings_scatter(results, output_dir)
    plot_emissions_vs_window_size(results, output_dir)
    plot_savings_vs_power(results, output_dir)
    generate_savings_table(results, output_dir)


if __name__ == "__main__":
    main()
