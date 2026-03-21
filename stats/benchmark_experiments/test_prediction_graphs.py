import json

import matplotlib.pyplot as plt
from generate_history import DATA_CENTRES

# Load the data
with open('history.json', 'r') as f:
    history_data = json.load(f)

with open('predictions.json', 'r') as f:
    prediction_data = json.load(f)

# Create figure with 2 subplots
plt.figure(figsize=(14, 10))

# Define colors for each data centre
colors = ['blue', 'red', 'green', 'orange', 'purple']

# Plot 1: Load comparison
plt.subplot(2, 1, 1)
for idx, dc in enumerate(DATA_CENTRES):
    if dc in history_data:
        history_load = [item['load'] for item in history_data[dc]]
        history_indices = range(len(history_load))
        plt.plot(
            history_indices,
            history_load,
            label=f'{dc} History',
            linestyle='-',
            alpha=0.6,
            color=colors[idx],
        )

    if dc in prediction_data:
        prediction_load = [item['value'] for item in prediction_data[dc]['load_prediction']['data']]
        prediction_indices = range(len(prediction_load))
        plt.plot(
            prediction_indices,
            prediction_load,
            label=f'{dc} Prediction',
            linestyle='--',
            alpha=0.8,
            color=colors[idx],
        )

plt.xlabel('Index (5-minute intervals)')
plt.ylabel('Load')
plt.title('Load: History vs Prediction (All Data Centres)')
plt.legend(loc='upper left', fontsize=8)
plt.grid(True, alpha=0.3)

# Plot 2: Carbon Intensity comparison
plt.subplot(2, 1, 2)
for idx, dc in enumerate(DATA_CENTRES):
    if dc in history_data:
        history_carbon_intensity = [item['carbon_intensity'] for item in history_data[dc]]
        history_indices = range(len(history_carbon_intensity))
        plt.plot(
            history_indices,
            history_carbon_intensity,
            label=f'{dc} History',
            linestyle='-',
            alpha=0.6,
            color=colors[idx],
        )

    if dc in prediction_data:
        prediction_carbon_intensity = [
            item['value'] for item in prediction_data[dc]['carbon_intensity_prediction']['data']
        ]
        prediction_indices = range(len(prediction_carbon_intensity))
        plt.plot(
            prediction_indices,
            prediction_carbon_intensity,
            label=f'{dc} Prediction',
            linestyle='--',
            alpha=0.8,
            color=colors[idx],
        )

plt.xlabel('Index (5-minute intervals)')
plt.ylabel('Carbon Intensity (gCO2eq/kWh)')
plt.title('Carbon Intensity: History vs Prediction (All Data Centres)')
plt.legend(loc='upper left', fontsize=8)
plt.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()
