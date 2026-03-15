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


class WindowFlexibilityVisulizer(Visualizer):
    def plot_window_flexibility(self) -> None:
        windows = [6, 12, 18, 24, 30, 36, 48, 72, 144]
        data = []
        c = self.configs[2]

        for w in windows:
            params: TestParams = {
                "config": c,
                "window_hours": w,
                "length_of_computation": 3 * 60 * 5,
                "volatility_override": 15,
            }
            res = run_specific_test(params)
            savings = 0.0
            if res["sdk_emissions_kg"] > 0 and res["sdk_emissions_kg"] != 9999.0:
                savings = (
                    (res["sdk_emissions_kg"] - res["agent_emissions_kg"])
                    / res["sdk_emissions_kg"]
                ) * 100
            data.append({"Window (hours)": w, "% Saved": savings})

        df = pd.DataFrame(data)
        sns.lineplot(
            data=df,
            x="Window (hours)",
            y="% Saved",
            color="seagreen",
            marker="s",
            linewidth=2.5,
        )
        plt.title("Flexibility Frontier: Diminishing Returns")
        plt.ylabel("% Saved over Baseline")
        plt.tight_layout()
        plt.savefig(
            self.save_path + "plot_flexibility_frontier.png", bbox_inches="tight"
        )
        plt.close()

    def run_all(self):
        self.plot_window_flexibility()
