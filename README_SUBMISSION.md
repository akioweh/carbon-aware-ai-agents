# Carbon-Aware AI Workload Scheduler

**Client:** NTT DATA | **Team:** Team 25

---

## 1. Overview & Objective

The **Carbon-Aware AI Workload Scheduler** is an end-to-end platform designed to minimize the environmental impact of resource-intensive AI operations. Instead of scheduling jobs based purely on speed or cost, the system dynamically shifts workloads to data centers and time windows where the energy grid's carbon intensity is at its lowest.

### Key Features & Capabilities

*   **Spatio-Temporal Routing:** Optimizes task placement across multiple geographic locations and timeframes using 7-day, 5-minute resolution carbon forecasts.
*   **Workload Discretization:** Breaks naturally parallelizable AI jobs into shorter, discrete blocks to exploit optimal clean energy windows.
*   **Physical Constraint Modeling:** Mathematically accounts for the real-world energy overheads of pausing and resuming jobs, such as the power required to transfer model weights into VRAM.
*   **Direct Comparison:** Generates both an optimized schedule and an unoptimized baseline, presenting a side-by-side UI comparison of the carbon saved.
*   **Standardized Reporting:** Produces environmental impact estimates that align with recognized methodologies like the Software Carbon Intensity (SCI) standard.

---

## 2. Environment & Open-Source Dependencies

All software components, libraries, and frameworks utilized in this project rely strictly on **open-source dependencies**.

### Core Infrastructure
*   **Database:** PostgreSQL (Internal port: `5432` / External port: `5433`).

### C++ Scheduler
*   **Compiler:** Requires a C++23 compatible toolchain.
*   **Key Libraries:** 
    *   `Boost` (Utility/Math functions)
    *   `Drogon` (Asynchronous Web Framework)

### Python Stats & Forecasting Service
*   **Environment:** Python 3.x
*   **Libraries:** `fastapi`, `pandas`, `uvicorn`, `scikit-learn`, `statsmodels`, `lightgbm`, `numpy`, `requests`.

### Frontend (UI)
*   **Framework:** Next.js / React
*   **Setup:** The frontend utilizes a modular dependency tree. Navigate to the UI directory and run `npm install` to initialize the environment and fetch all required open-source packages.

---

## 3. Docker Environments

We provide two primary containerized methods to handle these dependencies without requiring manual local installation:

### Dev Containers
If you cannot install a C++23 toolchain or specific libraries locally, we highly recommend using the provided **VS Code Dev Container**. This includes pre-configured and isolated environments for C++, Python, and Node.js.

### Release Images
Ready-to-use production images are published and available via the GitHub Container Registry. You can run the entire pre-compiled stack using our release compose file:

```bash
docker compose -f docker-compose.release.yml up
```

---

## 4. Local Development (Standard "How to Run")

### Basic Stack (Default)
This command starts the UI, Scheduler, and Database. By default, the system will connect to a remote Stats API.

```bash
docker compose up --build
```
*   **UI Dashboard:**[http://localhost:8080](http://localhost:8080)
*   **Scheduler API:**[http://localhost:6970](http://localhost:6970)

### Full Stack
This command starts *all* system components, including the local Python-based Stats and Forecasting service.

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

---

## 5. Cloud Deployment (Azure Example)

For production-grade hosting, the following architecture is recommended:

*   **Orchestration:** Run the UI and the C++ Scheduler as Azure Container Apps (ACA).
*   **Compute Optimization:** The ACA environment should be configured with a **Dedicated Workload Profile**. Specifically, utilize a `d4` work profile for the Scheduler to guarantee the high CPU and RAM overhead required for the Dynamic Programming engine.
*   **Database:** Utilize *Azure Database for PostgreSQL - Flexible Server*.
*   **Networking & Security:**
    *   Set `allowInsecure: true` on the internal Azure network configuration to allow internal microservices to communicate seamlessly via HTTP.
    *   By default, the environment should be locked to the Azure WAN (with **no** public internet exposure).
    *   Your Infrastructure-as-Code (Bicep configuration) should explicitly expose *only* the UI image to the public internet for end-user access.

---

## 6. Temporary deployment (On Azure)

For simplicity of testing, our website is currently deployed on this [page](https://carbonaware-ui.purplewave-8746eae9.uksouth.azurecontainerapps.io/). It is worth mentioning, that because of the incompatible hardware, vectorization of the hot-loop was impossible, hence the website is running slower than it would normally.