#ifndef HARDWARE_CONVERSION
#define HARDWARE_CONVERSION
#include "exceptions/ValidationException.hpp"
#pragma once

#include <json/value.h>
#include <string>
#include <unordered_map>

namespace scheduler::utils {

namespace hardwareConstants {
struct HardwareSpecs {
    int gpu_tdp;
    int gpu_idle;
    int bus_gbps;
    int sys_base;
};

struct JobHardwareSpecifics {
    double startup_overhead;
    double max_load;
    double workload_amount;
};

const auto HW_LIB = std::unordered_map<std::string, HardwareSpecs>{
    {"V100_PCIE",
     {.gpu_tdp = 250, .gpu_idle = 35, .bus_gbps = 12, .sys_base = 150}},
    {"A100_SXM4",
     {.gpu_tdp = 400, .gpu_idle = 55, .bus_gbps = 25, .sys_base = 230}}};

} // namespace hardwareConstants

auto convertRawJobRequest(const Json::Value &json)
    -> hardwareConstants::JobHardwareSpecifics;

} // namespace scheduler::utils

#endif