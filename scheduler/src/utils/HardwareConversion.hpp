#ifndef HARDWARE_CONVERSION
#define HARDWARE_CONVERSION
#pragma once

#include <json/value.h>
#include <ranges>
#include <string>
#include <unordered_map>

namespace scheduler::utils {

namespace hardwareConstants {
struct HardwareSpecs {
    int gpu_tdp;
    int gpu_idle;
    int bus_gbps;
    int sys_base;
    double tflops_fp32;
};

struct JobHardwareSpecifics {
    double startup_overhead;
    double max_load;
    double workload_amount;
    double kwh_per_flo;
};

const auto HW_LIB =
    std::unordered_map<std::string, HardwareSpecs>{{"V100_PCIE",
                                                    {.gpu_tdp = 250,
                                                     .gpu_idle = 35,
                                                     .bus_gbps = 12,
                                                     .sys_base = 150,
                                                     .tflops_fp32 = 15.7}},
                                                   {"A100_SXM4",
                                                    {.gpu_tdp = 400,
                                                     .gpu_idle = 55,
                                                     .bus_gbps = 25,
                                                     .sys_base = 230,
                                                     .tflops_fp32 = 19.5}}};

inline auto getAvailableGpuTypes() -> std::vector<std::string> {
    return HW_LIB | std::ranges::views::keys | std::ranges::to<std::vector>();
}

} // namespace hardwareConstants

auto convertRawJobRequest(const Json::Value &json)
    -> hardwareConstants::JobHardwareSpecifics;

} // namespace scheduler::utils

#endif