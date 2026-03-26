#ifndef SCHEDULER_TEST_CONSTANTS_HPP
#define SCHEDULER_TEST_CONSTANTS_HPP
#pragma once

#include <string_view>

namespace scheduler::test {

using namespace std::literals;

// network
inline constexpr auto LOCAL_STATS_URL = "http://127.0.0.1:5000"sv;
inline constexpr auto TEST_SERVER_URL = "http://127.0.0.1:6969"sv;
inline constexpr auto NETWORK_TIMEOUT = 2.0;
inline constexpr auto SERVER_START_TIMEOUT_SEC = 10;
inline constexpr auto SERVER_START_POLL_MS = 10;

// api
inline constexpr auto API_SCHEDULES = "/api/schedules"sv;
inline constexpr auto API_SCHEDULES_SUMMARY = "/api/schedules/summary"sv;
inline constexpr auto API_GPUS = "/api/hardwareSpecs/gpus"sv;
inline constexpr auto API_FORECAST = "/api/forecast"sv;
inline constexpr auto TEST_DB_FILENAME = "scheduler_test.db"sv;

// mock data
inline constexpr auto DATACENTER_PREFIX = "Data-Center-"sv;
inline constexpr auto NUM_MOCK_DATACENTERS = 14;
inline constexpr auto MOCK_JOB_TYPE1 = "batch"sv;
inline constexpr auto MOCK_JOB_TYPE2 = "inference"sv;
inline constexpr auto MOCK_GPU1 = "V100_PCIE"sv;
inline constexpr auto MOCK_GPU2 = "A100_SXM4"sv;
inline constexpr auto NONEXISTENT_LOCATION = "nonexistent_location_xyz_12345"sv;

} // namespace scheduler::test

#endif // SCHEDULER_TEST_CONSTANTS_HPP
