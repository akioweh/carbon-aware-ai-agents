import json
import matplotlib.pyplot as plt

# Load the data
with open('history.json', 'r') as f:
    history_data = json.load(f)

with open('prediction.json', 'r') as f:
    prediction_data = json.load(f)

# Extract load values
history_load = [item['load'] for item in history_data]
prediction_load = [item['predicted_load'] for item in prediction_data]

# Extract greenness values
history_greenness = [item['greenness'] for item in history_data]
prediction_greenness = [item['predicted_greenness'] for item in prediction_data]

# Create indices for x-axis
history_indices = range(len(history_load))
prediction_indices = range(len(prediction_load))

# Plot load data
plt.figure(figsize=(12, 10))

plt.subplot(2, 1, 1)
plt.plot(history_indices, history_load, label='Historical Load', linestyle='-', alpha=0.7)
plt.plot(prediction_indices, prediction_load, label='Predicted Load', linestyle='--', alpha=0.7)
plt.xlabel('Index (5-minute intervals)')
plt.ylabel('Load')
plt.title('Load: History vs Prediction')
plt.legend()
plt.grid(True, alpha=0.3)

# Plot greenness data
plt.subplot(2, 1, 2)
plt.plot(history_indices, history_greenness, label='Historical Greenness', linestyle='-', alpha=0.7, color='green')
plt.plot(prediction_indices, prediction_greenness, label='Predicted Greenness', linestyle='--', alpha=0.7, color='lightgreen')
plt.xlabel('Index (5-minute intervals)')
plt.ylabel('Greenness')
plt.title('Greenness: History vs Prediction')
plt.legend()
plt.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()