# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# --- START OF FILE visualizer.py ---

import os

import matplotlib.pyplot as plt
import seaborn as sns

from testing.test_setups import get_test_configs


class Visualizer:
    def __init__(self) -> None:
        sns.set_theme(style="whitegrid")
        plt.rcParams.update(
            {
                "axes.titlesize": 14,
                "axes.labelsize": 12,
                "figure.figsize": (8, 6),
                "figure.dpi": 300,
            }
        )
        self.configs = get_test_configs()
        self.save_path = "graphs"
        os.makedirs(self.save_path, exist_ok=True)
        self.save_path += "/"

    def run_all(self):
        pass
