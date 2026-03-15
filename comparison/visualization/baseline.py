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

        for w in workloads:
            params: TestParams = {
                "config": c,
                "window_hours": 36,
                "length_of_computation": w,
                "volatility_override": 15,
            }
            res = run_specific_test(params)
            data.append(
                {
                    "Workload (min)": w,
                    "Emissions": res["sdk_emissions_kg"],
                    "Strategy": "GSF SDK",
                }
            )
            data.append(
                {
                    "Workload (min)": w,
                    "Emissions": res["agent_emissions_kg"],
                    "Strategy": "Agent",
                }
            )

        df = pd.DataFrame(data)
        sns.lineplot(
            data=df, x="Workload (min)", y="Emissions", hue="Strategy", marker="o"
        )
        plt.title("Baseline Validation: Agent vs GSF SDK (window = 36h)")
        plt.ylabel(r"Emissions (g $CO_2e$)")
        plt.tight_layout()
        plt.savefig(
            self.save_path + "plot_baseline_validation.png", bbox_inches="tight"
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
    vis.generate_model_comparison_table()
