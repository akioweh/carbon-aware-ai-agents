# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from testing.running_tests import (
    TestParams,
    run_specific_test,
)
from visualization.base_visualizer import Visualizer


class HeatmapVisulizer(Visualizer):
    def plot_roi_heatmap(self) -> None:
        windows = [12, 16, 20, 24, 36, 48]
        data = []

        for c in self.configs:
            for w in windows:
                params: TestParams = {
                    "config": c,
                    "window_hours": w,
                    "length_of_computation": 60 * 9,
                    "volatility_override": 15,
                }
                res = run_specific_test(params)
                print(w, res["sdk_emissions_kg"], res["agent_emissions_kg"])
                if res["sdk_emissions_kg"] == 0:
                    savings = 0
                else:
                    savings = (
                        (res["sdk_emissions_kg"] - res["agent_emissions_kg"])
                        / res["sdk_emissions_kg"]
                    ) * 100
                data.append(
                    {
                        "Power (kW)": round(c["full_power"], 1),
                        "Window (hrs)": w,
                        "% Savings": savings,
                    }
                )

        df = pd.DataFrame(data)
        pivot_df = df.pivot_table(
            index="Window (hrs)",
            columns="Power (kW)",
            values="% Savings",
            aggfunc="mean",
        )

        sns.heatmap(
            pivot_df,
            annot=True,
            cmap="YlGnBu",
            fmt=".1f",
            cbar_kws={"label": "% Savings"},
        )
        plt.title("ROI Heatmap: Configuration vs. User Patience")
        plt.gca().invert_yaxis()
        plt.tight_layout()
        plt.savefig(self.save_path + "plot_roi_heatmap.png", bbox_inches="tight")
        plt.close()

    def run_all(self):
        self.plot_roi_heatmap()
