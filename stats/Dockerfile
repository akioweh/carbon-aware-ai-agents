# stats/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create empty databases if they don't exist
RUN touch cache.db carbon_intensity.db

EXPOSE 5000

ENV STATS_HOST=0.0.0.0
ENV STATS_PORT=5000

CMD ["python", "app.py"]
