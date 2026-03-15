# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
import os

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from testing.running_tests import (
    TestParams,
    get_lengths_of_computation,
    run_specific_test,
    run_tests,
)
from visualization.base_visualizer import Visualizer


class BaselineVisulizer(Visualizer):
    def plot_baseline_validation(self) -> None:
        workloads = get_lengths_of_computation()
        data = []
        c = self.configs[0]
        best_dc = "Data-Center-5"

        for w in workloads:
            # Pass 1: Restricted to Best Single DC (DC5)
            # Provides: SDK (Contiguous) vs DP (Splitting)
            params_restricted: TestParams = {
                "config": c,
                "window_hours": 36,
                "length_of_computation": w,
                "volatility_override": 15,
            }
            res_r = run_specific_test(params_restricted, best_dc)

            # Pass 2: Unrestricted Global (All DCs)
            # Provides: DP (Splitting + Routing)
            params_global: TestParams = {
                "config": c,
                "window_hours": 36,
                "length_of_computation": w,
                "volatility_override": 15,
            }
            res_g = run_specific_test(params_global)

            # Tier 1: Industry Standard (SDK on best DC)
            data.append(
                {
                    "Workload (min)": w,
                    "Emissions": res_r["sdk_emissions_kg"],
                    "Strategy": f"GSF SDK ({best_dc})",
                }
            )
            # Tier 2: DP Temporal Advantage (Same DC, but splitting allowed)
            data.append(
                {
                    "Workload (min)": w,
                    "Emissions": res_r["agent_emissions_kg"],
                    "Strategy": f"DP Algorithm ({best_dc})",
                }
            )
            # Tier 3: DP Global Advantage (Splitting + 5-DC Routing)
            data.append(
                {
                    "Workload (min)": w,
                    "Emissions": res_g["agent_emissions_kg"],
                    "Strategy": "DP Algorithm (Global Optimal)",
                }
            )

        df = pd.DataFrame(data)
        plt.figure(figsize=(10, 6))

        # Define palette to clearly distinguish between temporal and spatial gains
        palette = {
            f"GSF SDK ({best_dc})": "#95a5a6",  # Gray (Baseline)
            f"DP Algorithm ({best_dc})": "#3498db",  # Blue (Temporal Gain)
            "DP Algorithm (Global Optimal)": "#2ecc71",  # Green (Spatial Gain)
        }

        sns.lineplot(
            data=df,
            x="Workload (min)",
            y="Emissions",
            hue="Strategy",
            palette=palette,
            marker="o",
            linewidth=2.5,
        )

        # Shading areas to highlight "Sources of Superiority"
        # Note: These values must be pivot-aligned for fill_between
        pivot_df = df.pivot(
            index="Workload (min)", columns="Strategy", values="Emissions"
        )
        plt.fill_between(
            pivot_df.index,
            pivot_df[f"GSF SDK ({best_dc})"],
            pivot_df[f"DP Algorithm ({best_dc})"],
            color="#3498db",
            alpha=0.1,
        )
        plt.fill_between(
            pivot_df.index,
            pivot_df[f"DP Algorithm ({best_dc})"],
            pivot_df["DP Algorithm (Global Optimal)"],
            color="#2ecc71",
            alpha=0.1,
        )

        plt.title(
            "Emissions Hierarchy: Temporal Splitting vs. Spatial Routing (36h Window)"
        )
        plt.ylabel(r"Emissions (g $CO_2e$)")
        plt.xlabel("Workload Length (minutes)")
        plt.grid(True, linestyle=":", alpha=0.5)
        plt.tight_layout()

        plt.savefig(
            self.save_path + "plot_baseline_validation_final.png", bbox_inches="tight"
        )
        plt.close()

    def generate_model_comparison_table(self) -> None:
        all_results = run_tests()
        df = pd.DataFrame(all_results)

        # 1. Convert grams to kg
        df["sdk_emissions_kg"] = df["sdk_emissions_kg"] / 1000
        df["agent_emissions_kg"] = df["agent_emissions_kg"] / 1000

        config_map = {
            c[
                "config_id"
            ]: f"{c['model']['gb']}B | {c['system']['type']} x{c['system']['n']}"
            for c in self.configs
        }
        df["Configuration"] = df["config_id"].map(config_map)

        df["Pct_Saved"] = (
            (df["sdk_emissions_kg"] - df["agent_emissions_kg"])
            / df["sdk_emissions_kg"]
            * 100
        ).clip(lower=0)

        summary = (
            df.groupby("Configuration")
            .agg(
                {
                    "sdk_emissions_kg": "sum",
                    "agent_emissions_kg": "sum",
                    "Pct_Saved": "mean",
                }
            )
            .reset_index()
        )

        summary["Total Saved (kg)"] = (
            summary["sdk_emissions_kg"] - summary["agent_emissions_kg"]
        )

        summary = summary.rename(
            columns={
                "sdk_emissions_kg": "SDK Total (kg)",
                "agent_emissions_kg": "Agent Total (kg)",
                "Pct_Saved": "Avg. Efficiency",
            }
        )

        display_df = summary.copy()
        display_df["Avg. Efficiency"] = display_df["Avg. Efficiency"].map(
            "{:.2f}%".format
        )
        for col in ["SDK Total (kg)", "Agent Total (kg)", "Total Saved (kg)"]:
            display_df[col] = display_df[col].map("{:.2f}".format)

        fig_height = 2 + (len(display_df) * 0.4)
        _, ax = plt.subplots(figsize=(12, fig_height))
        ax.axis("off")

        table = ax.table(
            cellText=display_df.values,  # type: ignore
            colLabels=display_df.columns,  # type: ignore
            cellLoc="center",
            loc="center",
            colColours=["#f2f2f2"] * len(display_df.columns),
        )

        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.0, 1.5)

        plt.title(
            "Detailed System Efficiency Comparison (48h Window, Varying length of a workload)",
            pad=20,
        )

        # Ensure self.save_path ends with / or use os.path.join
        save_file = os.path.join(self.save_path, "model_comparison_table.png")
        plt.savefig(save_file, bbox_inches="tight", dpi=300)
        plt.close()
        print(f"Comparison table saved to {save_file}")

    def run_all(self):
        self.plot_baseline_validation()
        self.generate_model_comparison_table()


if __name__ == "__main__":
    vis = BaselineVisulizer()
    vis.plot_baseline_validation()
