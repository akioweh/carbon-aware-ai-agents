#include "utils/HardwareConversion.hpp"
#include "exceptions/ValidationException.hpp"
#include <json/value.h>

namespace scheduler::utils {
namespace {

constexpr auto FAN_SURGE_COEFF = 2.5;
constexpr auto CONTAINER_LOAD_W = 100;
constexpr auto TRANSFER_EFFICIENCY = 0.45;

auto get_full_power_kw(const std::string &gpu_type, int count) -> double {
    const auto &h = hardwareConstants::HW_LIB.at(gpu_type);
    return static_cast<double>((count * h.gpu_tdp) + h.sys_base) / 1000.0;
}

auto get_startup_energy_kwh(const std::string &gpu_type, int count) -> double {
    const auto &h = hardwareConstants::HW_LIB.at(gpu_type);

    // 1. BIOS/POST Phase
    auto p_bios = (static_cast<double>(h.sys_base) * 0.8) +
                  (static_cast<double>(h.sys_base) * 0.2 * FAN_SURGE_COEFF) +
                  static_cast<double>(count * h.gpu_idle);
    auto e_bios = (p_bios / 1000.0) * (2.0 / 60.0);

    // 2. OS/Driver Phase
    auto p_os = static_cast<double>(h.sys_base + CONTAINER_LOAD_W +
                                    (count * h.gpu_idle));
    auto e_os = (p_os / 1000.0) * (2.0 / 60.0);

    return e_bios + e_os;
}

auto get_load_energy_kwh(double model_gb, const std::string &gpu_type,
                         double p_full_kw) -> double {
    const auto &h = hardwareConstants::HW_LIB.at(gpu_type);
    auto p_load = p_full_kw * TRANSFER_EFFICIENCY;
    auto transfer_time_hr =
        (model_gb / static_cast<double>(h.bus_gbps)) / 3600.0;

    return p_load * transfer_time_hr;
}

auto get_workload_amount(const int length, double full_power) -> double {
    return full_power * (length / 60.0);
}

auto calculate_flo_per_kwh(const std::string &gpu_type) -> double {
    constexpr auto effectiveness = 0.99;
    const auto &[gpu_tdp, _, _, _, tflops] =
        hardwareConstants::HW_LIB.at(gpu_type);
    const auto total_flo_per_hour = tflops * 1e12 * 3600.0;
    const auto kwh_per_hour = gpu_tdp / 1000.0;
    return effectiveness * total_flo_per_hour / kwh_per_hour;
}

struct HardwareMetrics {
    std::string gpu_type;
    int length; // length of computation in minutes
    int gpu_count;
    int model_size;
};

auto validateHardwareMetrics(const Json::Value &json) -> HardwareMetrics {
    if (!json["length"].isNumeric())
        throw exceptions::ValidationException("length has to be a number.");
    if (!json["gpu_count"].isNumeric())
        throw exceptions::ValidationException("gpu_count has to be a number.");
    if (!json["model_size"].isNumeric())
        throw exceptions::ValidationException("model_size has to be a number.");
    if (!json["gpu_type"].isString())
        throw exceptions::ValidationException("gpu_type has to be a string.");

    const auto length = json["length"].asInt();
    const auto gpu_count = json["gpu_count"].asInt();
    const auto model_size = json["model_size"].asInt();
    const auto &gpu_type = json["gpu_type"].asString();

    if (length <= 0)
        throw exceptions::ValidationException("length has to be positive.");
    if (gpu_count <= 0)
        throw exceptions::ValidationException("gpu_count has to be positive.");
    if (model_size <= 0)
        throw exceptions::ValidationException("model_size has to be positive.");
    if (!hardwareConstants::HW_LIB.contains(gpu_type))
        throw exceptions::ValidationException("gpu_type not recognized!");

    return HardwareMetrics{.gpu_type = gpu_type,
                           .length = length,
                           .gpu_count = gpu_count,
                           .model_size = model_size};
}

} // namespace

auto convertRawJobRequest(const Json::Value &json)
    -> hardwareConstants::JobHardwareSpecifics {
    const auto hardwareMetrics = validateHardwareMetrics(json);
    const auto full_power =
        get_full_power_kw(hardwareMetrics.gpu_type, hardwareMetrics.gpu_count);
    const auto e_base = get_startup_energy_kwh(hardwareMetrics.gpu_type,
                                               hardwareMetrics.gpu_count);
    const auto e_load = get_load_energy_kwh(
        hardwareMetrics.model_size, hardwareMetrics.gpu_type, full_power);
    const auto workload_amount =
        get_workload_amount(hardwareMetrics.length, full_power);

    const auto max_workload_completed_in_block = full_power / 12.;

    const auto flo_per_kwh = calculate_flo_per_kwh(hardwareMetrics.gpu_type);

    return hardwareConstants::JobHardwareSpecifics{
        .startup_overhead = (e_base + e_load) * flo_per_kwh,
        .max_load = max_workload_completed_in_block * flo_per_kwh,
        .workload_amount = workload_amount * flo_per_kwh,
        .kwh_per_flo = 1. / flo_per_kwh};
}

} // namespace scheduler::utils
