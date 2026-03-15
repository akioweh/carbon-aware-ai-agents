# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from scipy import stats  # type: ignore

from testing.running_tests import (
    TestParams,
    run_specific_test,
)
from visualization.base_visualizer import Visualizer


class PowerLeverageVisulizer(Visualizer):
    def plot_compression_leverage_relative(self) -> None:
        data = []
        target_model_gb = 140

        for c in self.configs:
            if c["model"]["gb"] != target_model_gb:
                continue

            params: TestParams = {
                "config": c,
                "window_hours": 24,
                "length_of_computation": 60 * 9,
                "volatility_override": 15,
            }
            res = run_specific_test(params)

            sdk_val = res["sdk_emissions_kg"]
            agent_val = res["agent_emissions_kg"]
            pct_saved = ((sdk_val - agent_val) / sdk_val * 100) if sdk_val > 0 else 0

            data.append(
                {
                    "Peak Power (kW)": c["full_power"],
                    "Savings (%)": pct_saved,
                    "Hardware": f"{c['system']['type']} x{c['system']['n']}",
                }
            )

        df = pd.DataFrame(data)

        slope, _, r_value, _, _ = stats.linregress(
            df["Peak Power (kW)"], df["Savings (%)"]
        )

        plt.figure(figsize=(9, 6))

        sns.regplot(
            data=df,
            x="Peak Power (kW)",
            y="Savings (%)",
            scatter=False,
            color="gray",
            line_kws={"linestyle": "--", "label": f"Slope: {slope:.4f} %/kW"},
        )

        sns.scatterplot(
            data=df,
            x="Peak Power (kW)",
            y="Savings (%)",
            hue="Hardware",
            s=250,
            palette="viridis",
            edgecolor="black",
        )

        r_squared = float(r_value) ** 2  # type: ignore
        plt.text(
            0.05,
            0.95,
            f"Slope: {slope:.4f} % savings per kW\n$R^2$: {r_squared:.4f}",
            transform=plt.gca().transAxes,
            verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )

        plt.legend(title="Hardware Config", bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.title(f"Relative Efficiency Stability ({target_model_gb}B Model)")
        plt.ylabel("Carbon Savings (%)")
        y_min = df["Savings (%)"].min() - 1
        y_max = df["Savings (%)"].max() + 1
        plt.ylim(y_min, y_max)
        plt.grid(True, linestyle=":", alpha=0.5)
        plt.tight_layout()
        plt.savefig(
            self.save_path + "plot_leverage_relative_final.png", bbox_inches="tight"
        )
        plt.close()

    def plot_compression_leverage_absolute(self) -> None:
        data = []
        # Filter for only one model size to clean up the plot
        target_model_gb = 140

        for c in self.configs:
            if c["model"]["gb"] != target_model_gb:
                continue

            params: TestParams = {
                "config": c,
                "window_hours": 36,
                "length_of_computation": 60 * 9,
                "volatility_override": 15,
            }
            res = run_specific_test(params)
            saved = max(0.0, res["sdk_emissions_kg"] - res["agent_emissions_kg"])

            # ultra-clean label: GPU + Count
            short_label = f"{c['system']['type']} x{c['system']['n']}"

            data.append(
                {
                    "Peak Power of the system (kW)": c["full_power"],
                    "Abs. Saved (kg)": saved,
                    "Hardware": short_label,
                }
            )

        df = pd.DataFrame(data)
        plt.figure(figsize=(9, 6))

        sns.regplot(
            data=df,
            x="Peak Power of the system (kW)",
            y="Abs. Saved (kg)",
            scatter=False,
            color="gray",
            line_kws={"linestyle": "--"},
        )

        sns.scatterplot(
            data=df,
            x="Peak Power of the system (kW)",
            y="Abs. Saved (kg)",
            hue="Hardware",
            s=250,
            palette="magma",
            edgecolor="black",
        )

        plt.legend(title="Hardware Config", bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.title(f"System Leverage ({target_model_gb}B Model)")
        plt.ylabel(r"Absolute Saved (kg $CO_2e$)")
        plt.grid(True, linestyle=":", alpha=0.5)
        plt.tight_layout()
        plt.savefig(self.save_path + "plot_leverage_absolute.png", bbox_inches="tight")
        plt.close()

    def run_all(self):
        self.plot_compression_leverage_absolute()
        self.plot_compression_leverage_relative()


if __name__ == "__main__":
    vis = PowerLeverageVisulizer()
    vis.plot_compression_leverage_relative()
