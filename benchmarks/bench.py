import json
import os
import time
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import pandas as pd
import requests

# --- CONFIGURATION ---
BASE_URL = "http://localhost:6969/api"
RESULTS_DIR = "bench_results"
GPU_TYPES = ["V100_PCIE", "A100_SXM4"]

if not os.path.exists(RESULTS_DIR):
    os.makedirs(RESULTS_DIR)


def get_current_branch():
    """Returns the current git branch name."""
    return "Cache_and_Vectorization_Optimization"


def generate_test_batch(size=40):
    """
    Generates a deterministic batch of requests.
    We vary 'length' (Work W) and 'deadline window' (n blocks).
    """
    batch = []
    base_start = datetime(2026, 3, 20, 4, 0, 0)

    # We use a range of complexities
    # Complexity is roughly proportional to: (deadline_window) * (length * gpu_count)
    window_hours = 72
    for i in range(10, size + 10):
        work_minutes = i * 60  # Work volume grows
        req = {
            "job_type": "training",
            "earliest_start": base_start.isoformat() + "Z",
            "latest_finish": (base_start + timedelta(hours=window_hours)).isoformat()
            + "Z",
            "gpu_type": GPU_TYPES[i % len(GPU_TYPES)],
            "length": work_minutes,
            "gpu_count": i * 2,
            "model_size": 10 + (i * 2),
            # Metadata for plotting
            "_complexity_score": work_minutes,
        }
        batch.append(req)
    return batch


def run_benchmark():
    branch = get_current_branch()
    print(f"🚀 Starting benchmark for branch: {branch}")

    batch = generate_test_batch()
    results = []

    for i, payload in enumerate(batch):
        # Extract metadata for logging, then clean payload
        complexity = payload.pop("_complexity_score")

        print(
            f"  [{i + 1}/{len(batch)}] Sending request (Complexity: {complexity})...",
            end="",
            flush=True,
        )

        try:
            avg_time = 0
            for p in range(5):
                start_time = time.perf_counter()
                resp = requests.post(f"{BASE_URL}/schedules", json=payload)
                end_time = time.perf_counter()
                duration = end_time - start_time
                avg_time += duration
                schedule_id = resp.json().get("schedule_id")
                requests.delete(f"{BASE_URL}/schedules/{schedule_id}")
            avg_time /= 5

            if resp.status_code == 200:
                print(f" OK ({avg_time:.4f}s)")
                results.append(
                    {
                        "complexity": complexity,
                        "duration": avg_time,
                        "status": resp.status_code,
                        "schedule_id": schedule_id,
                    }
                )
            else:
                print(f" FAILED ({resp.status_code})")
                print(resp.text)
        except Exception as e:
            print(f" ERROR: {e}")

    # Save data
    output_path = os.path.join(RESULTS_DIR, f"results_{branch}.json")
    with open(output_path, "w") as f:
        json.dump(
            {
                "branch": branch,
                "timestamp": datetime.now().isoformat(),
                "data": results,
            },
            f,
            indent=2,
        )

    print(f"✅ Results saved to {output_path}")


def plot_comparison():
    """Reads all json files in RESULTS_DIR and plots execution time vs complexity."""
    plt.figure(figsize=(10, 6))

    files = [f for f in os.listdir(RESULTS_DIR) if f.endswith(".json")]

    if not files:
        print("No result files found to plot.")
        return

    for file in files:
        with open(os.path.join(RESULTS_DIR, file), "r") as f:
            res = json.load(f)
            df = pd.DataFrame(res["data"])
            if not df.empty:
                # Sort by complexity for a clean line
                df = df.sort_values("complexity")
                plt.plot(
                    df["complexity"], df["duration"], marker="o", label=res["branch"]
                )

    plt.title("Scheduling Algorithm Performance Comparison")
    plt.xlabel("Complexity (Work Load) with deadline=72h")
    plt.ylabel("Execution Time (seconds)")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.7)

    plot_file = "performance_comparison.png"
    plt.savefig(plot_file)
    print(f"📊 Graph saved to {plot_file}")
    plt.show()


def plot_relative_speedup():
    """Reads result files and plots relative speedup compared to First_Solution."""
    baseline_path = os.path.join(RESULTS_DIR, "results_First_Solution.json")

    if not os.path.exists(baseline_path):
        print(f"⚠️ Baseline file not found: {baseline_path}. Cannot plot speedup.")
        return

    # Load baseline
    with open(baseline_path, "r") as f:
        baseline_res = json.load(f)
        df_baseline = pd.DataFrame(baseline_res["data"])
        if df_baseline.empty:
            return
        df_baseline = df_baseline.set_index("complexity")

    plt.figure(figsize=(10, 6))

    files = [
        f
        for f in os.listdir(RESULTS_DIR)
        if f.endswith(".json") and f != "results_First_Solution.json"
    ]

    if not files:
        print("No other result files found to compare against baseline.")
        return

    for file in files:
        with open(os.path.join(RESULTS_DIR, file), "r") as f:
            res = json.load(f)
            df = pd.DataFrame(res["data"])
            if not df.empty:
                df = df.set_index("complexity")
                # Calculate speedup (Baseline Time / New Time)
                # Speedup > 1 means the new solution is faster
                speedup = df_baseline["duration"] / df["duration"]

                plt.plot(speedup.index, speedup.values, marker="s", label=res["branch"])

    # Add a reference line for 1.0x (Baseline)
    plt.axhline(y=1.0, color="r", linestyle="--", label="Baseline (1.0x)")

    plt.title("Relative Speedup Compared to First_Solution")
    plt.xlabel("Complexity (Work Load) with deadline=72h")
    plt.ylabel("Speedup Factor (Baseline Time / Current Time)")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.7)

    plot_file = "relative_speedup.png"
    plt.savefig(plot_file)
    print(f"📈 Speedup graph saved to {plot_file}")
    plt.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--plot":
        plot_comparison()
        plot_relative_speedup()
    else:
        run_benchmark()
