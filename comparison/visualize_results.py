import os

import matplotlib.pyplot as plt
from tabulate import tabulate

from running_tests import run_tests

# Import types and functions from your provided files
# Replace 'your_test_script' with the name of your file containing run_tests (e.g., 'main')
from test_setups import TestConfig, get_test_configs


def generate_graphs(
    test_configs: list[TestConfig], results: list[dict[int, tuple[float, float]]]
) -> None:
    """
    Generates and saves line graphs for each test setup.
    X-axis: Execution time in minutes
    Y-axis: Carbon Emissions
    """
    output_dir: str = "test_graphs"
    os.makedirs(output_dir, exist_ok=True)

    print(f"Generating graphs in the '{output_dir}' directory...")

    config: TestConfig
    result_data: dict[int, tuple[float, float]]

    for config, result_data in zip(test_configs, results):
        config_id: str = config.get("config_id", "Unknown_Setup")

        # Sort data points by execution time (X-axis)
        sorted_times: list[int] = sorted(result_data.keys())

        x_axis: list[int] = sorted_times
        y_sdk: list[float] = [result_data[time][0] for time in sorted_times]
        y_our: list[float] = [result_data[time][1] for time in sorted_times]

        plt.figure(figsize=(10, 6))

        # Plot lines with markers for discrete points
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

        # Formatting the graph
        plt.title(
            f"Carbon Emissions vs. Execution Time\nSetup: {config_id}",
            fontsize=14,
            fontweight="bold",
        )
        plt.xlabel("Execution Time (minutes)", fontsize=12)
        plt.ylabel("Carbon Emissions (kg CO2eq)", fontsize=12)
        plt.legend(fontsize=12)
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.tight_layout()

        # Save the graph
        safe_filename: str = config_id.replace(" ", "_").replace("/", "_") + ".png"
        filepath: str = os.path.join(output_dir, safe_filename)
        plt.savefig(filepath, dpi=300)
        plt.close()

    print(f"Successfully saved {len(test_configs)} graphs!\n")


def generate_savings_table(
    test_configs: list[TestConfig], results: list[dict[int, tuple[float, float]]]
) -> None:
    """
    Creates and prints a nicely formatted ASCII table, and also saves it as a stylized PNG image.
    """
    table_data: list[list[str]] = []

    config: TestConfig
    result_data: dict[int, tuple[float, float]]

    for config, result_data in zip(test_configs, results):
        config_id: str = config.get("config_id", "Unknown_Setup")

        total_sdk: float = 0.0
        total_our: float = 0.0

        sdk_emission: float
        our_emission: float

        # Aggregate emissions over all execution times for this setup
        for _, (sdk_emission, our_emission) in result_data.items():
            total_sdk += sdk_emission
            total_our += our_emission

        absolute_savings: float = total_sdk - total_our
        percent_saved: float = (
            (absolute_savings / total_sdk * 100) if total_sdk > 0 else 0.0
        )

        table_data.append(
            [
                config_id,
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

    # 1. Print beautifully to the console
    print("\n" + "=" * 85)
    print(" CARBON SAVINGS SUMMARY ".center(85, "="))
    print("=" * 85 + "\n")
    print(
        tabulate(table_data, headers=headers, tablefmt="fancy_grid", stralign="center")
    )
    print("\n")

    # 2. Render and save nicely to a PNG
    output_dir: str = "test_graphs"
    os.makedirs(output_dir, exist_ok=True)

    # Calculate a dynamic height for the figure based on the number of rows
    fig_height: float = max(4.0, len(table_data) * 0.5 + 2.0)
    fig, ax = plt.subplots(figsize=(12, fig_height))

    # Hide axes completely
    ax.axis("off")
    ax.axis("tight")

    # Create the table
    mpl_table = ax.table(
        cellText=table_data, colLabels=headers, loc="center", cellLoc="center"
    )

    # Style the table
    mpl_table.auto_set_font_size(False)
    mpl_table.set_fontsize(11)
    mpl_table.scale(1.2, 1.8)  # Widen and heighten cells for breathing room

    # Style the header row to stand out (bold text, light grey background)
    cell_key: tuple[int, int]
    for cell_key, cell in mpl_table.get_celld().items():
        row_idx: int = cell_key[0]
        if row_idx == 0:
            cell.set_text_props(weight="bold", color="black")
            cell.set_facecolor("#e0e0e0")
        else:
            # Alternating row colors for better readability
            if row_idx % 2 == 0:
                cell.set_facecolor("#f9f9f9")

    plt.title(
        "Total Carbon Savings per Setup Configuration",
        fontweight="bold",
        fontsize=16,
        pad=20,
    )
    plt.tight_layout()

    table_filepath: str = os.path.join(output_dir, "carbon_savings_summary.png")
    plt.savefig(table_filepath, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Saved savings table PNG to: {table_filepath}\n")


def main() -> None:
    # 1. Fetch the setups
    test_configs: list[TestConfig] = get_test_configs()

    print(
        f"Starting test runs across {len(test_configs)} configurations... This might take a moment.\n"
    )

    # 2. Run the tests (Using the external function from your_test_script)
    results: list[dict[int, tuple[float, float]]] = run_tests()

    # Validation
    if len(test_configs) != len(results):
        print(
            "Warning: Mismatch between number of configurations and results returned."
        )
        return

    # 3. Generate the line graphs and the data table PNG
    generate_graphs(test_configs, results)
    generate_savings_table(test_configs, results)


if __name__ == "__main__":
    main()
