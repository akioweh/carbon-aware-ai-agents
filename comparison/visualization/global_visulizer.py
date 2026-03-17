from visualization.base_visualizer import Visualizer
from visualization.baseline import BaselineVisulizer
from visualization.heat_map import HeatmapVisulizer
from visualization.power_leverage import PowerLeverageVisulizer
from visualization.runtime_complexity import RuntimeComplexityVisulizer
from visualization.window_flexibility import WindowFlexibilityVisulizer


class GlobalVisulizer(Visualizer):
    def __init__(self) -> None:
        self.visulizers: list[Visualizer] = [
            BaselineVisulizer(),
            HeatmapVisulizer(),
            PowerLeverageVisulizer(),
            RuntimeComplexityVisulizer(),
            WindowFlexibilityVisulizer(),
        ]

    def run_all(self):
        for i in self.visulizers:
            i.run_all()


if __name__ == "__main__":
    vis = GlobalVisulizer()
    vis.run_all()
