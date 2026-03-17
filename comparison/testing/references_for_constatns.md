### 1. The Verified Constant Library
These values are the "atoms" of our energy model, derived from official hardware documentation and industry-standard power benchmarks.

| Constant | Value | Reference / Source |
| :--- | :--- | :--- |
| **$P_{TDP}$ (A100 SXM4)** | 400W | [NVIDIA A100 Datasheet](https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/a100/pdf/nvidia-a100-datasheet-nvidia-us-2188504-web.pdf) |
| **$P_{TDP}$ (V100 PCIe)** | 250W | [NVIDIA V100 Datasheet](https://images.nvidia.com/content/technologies/volta/pdf/tesla-volta-v100-datasheet.pdf) |
| **$P_{idle}$ (A100)** | 55W | Empirical: Measured via `nvidia-smi` (Typical range: 50–60W) |
| **$P_{idle}$ (V100)** | 35W | Empirical: Measured via `nvidia-smi` (Typical range: 30–40W) |
| **$P_{sys\_base}$** | 150-230W | [SPECpower_ssj2008](https://www.spec.org/power_ssj2008/) for Dual-Socket Xeon/EPYC nodes |
| **$BW_{PCIe4}$** | 25 GB/s | PCIe 4.0 x16 theoretical: 31.5 GB/s (~80% effective throughput) |
| **$BW_{PCIe3}$** | 12 GB/s | PCIe 3.0 x16 theoretical: 15.75 GB/s (~80% effective throughput) |
| **$FAN_{surge}$** | 2.5x | [SPECpower] Fan power multiplier during BIOS/POST thermal test |
| **$P_{load\_cpu}$** | 100W | Empirical: CPU delta for multi-threaded container decompression |