# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from testing.running_tests import (
    TestParams,
    get_lengths_of_computation,
    run_specific_test,
)
from visualization.base_visualizer import Visualizer


class RuntimeComplexityVisulizer(Visualizer):
    def getWindowSizes(self) -> list[int]:
        return [
            4,
            6,
            8,
            10,
            12,
            14,
            16,
            18,
            20,
            22,
            24,
            30,
            36,
            42,
            48,
            50,
            62,
            74,
            144,
        ]

    def plot_complexity_scaling_with_window(self) -> None:
        windows = self.getWindowSizes()
        data = []
        c = self.configs[0]

        for w in windows:
            params: TestParams = {
                "config": c,
                "window_hours": w,
                "length_of_computation": 180,
                "volatility_override": 15,
            }
            res = run_specific_test(params)
            data.append({"Window (hours)": w, "Runtime (sec)": res["runtime_sec"]})

        df = pd.DataFrame(data)
        sns.lineplot(
            data=df,
            x="Window (hours)",
            y="Runtime (sec)",
            color="navy",
            marker="o",
            linewidth=2,
        )
        plt.title(r"Runtime complexity with window size (length of workload: 3h)")
        plt.tight_layout()
        plt.savefig(
            self.save_path + "plot_complexity_scaling_window.png", bbox_inches="tight"
        )
        plt.close()

    def plot_complexity_scaling_with_length_of_computation(self) -> None:
        lengths = get_lengths_of_computation()
        data = []
        c = self.configs[0]

        for length in lengths:
            params: TestParams = {
                "config": c,
                "window_hours": 48,
                "length_of_computation": length,
                "volatility_override": 15,
            }
            res = run_specific_test(params)
            data.append(
                {
                    "Length of a schedule (hours)": length,
                    "Runtime (sec)": res["runtime_sec"],
                }
            )

        df = pd.DataFrame(data)
        sns.lineplot(
            data=df,
            x="Length of a schedule (hours)",
            y="Runtime (sec)",
            color="navy",
            marker="o",
            linewidth=2,
        )
        plt.title(r"Runtime complexity with length of workload (window: 48h)")
        plt.tight_layout()
        plt.savefig(
            self.save_path + "plot_complexity_scaling_length_of_schedule.png",
            bbox_inches="tight",
        )
        plt.close()

    def run_all(self):
        self.plot_complexity_scaling_with_length_of_computation()
        self.plot_complexity_scaling_with_window()
