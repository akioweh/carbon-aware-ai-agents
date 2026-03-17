# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
import os

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from testing.running_tests import (
    run_tests,
)
from visualization.base_visualizer import Visualizer


class ModelsizeVisulizer(Visualizer):
    def plot_model_size_comparison(self):
        all_results = run_tests()
        df = pd.DataFrame(all_results)

        # 1. TIGHT FILTER: Same Window AND Same Workload Length
        # This removes the "vertical noise" caused by varying job sizes
        df = df[
            (df["window_hours"] == 48) & (df["length_of_computation"] >= 3 * 60 * 3)
        ]

        model_map = {c["config_id"]: f"{c['model']['gb']}B" for c in self.configs}
        df["Model Size"] = df["config_id"].map(model_map)
        df["Savings (%)"] = (
            (df["sdk_emissions_kg"] - df["agent_emissions_kg"])
            / df["sdk_emissions_kg"]
            * 100
        ).clip(lower=0)

        plt.figure(figsize=(7, 5))

        sns.boxplot(data=df, x="Model Size", y="Savings (%)", width=0.3, palette="Set2")
        sns.stripplot(
            data=df, x="Model Size", y="Savings (%)", color=".1", size=5, jitter=0.05
        )

        plt.title("Carbon Savings Efficiency Stability (48h Window, <= 9h workload)")
        plt.ylabel("Carbon Savings (%)")
        plt.ylim(50, 80)
        plt.grid(axis="y", linestyle="--", alpha=0.7)

        plt.savefig(
            os.path.join(self.save_path, "model_size_comparison.png"),
            bbox_inches="tight",
        )
        plt.close()


if __name__ == "__main__":
    vis = ModelsizeVisulizer()
    vis.plot_model_size_comparison()
