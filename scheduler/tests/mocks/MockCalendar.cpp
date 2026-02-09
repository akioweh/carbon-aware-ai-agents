#include "Calendar.hpp"
#include "structs/ScheduleResult.hpp"
#include "structs/SchedulerOutput.hpp"
#include "utils/Utils.hpp"
#include <atomic>
#include <drogon/drogon.h>
#include <map>
#include <mutex>

namespace scheduler::calendar {

// Simple in-memory storage
// Using static map to persist across calls since Calendar is a namespace of
// functions
static std::mutex g_mutex;
static std::map<std::string, ScheduleResult> g_storage;
static std::atomic<int> g_id_counter{1};

auto add(const SchedulerOutput &output) -> drogon::Task<std::string> {
    std::string id = scheduler::utils::parseIntToStringID(g_id_counter++);

    // Convert InternalBlock to ScheduleBlock
    std::vector<ScheduleBlock> blocks;
    blocks.reserve(output.blocks.size());
    for (const auto &ib : output.blocks) {
        blocks.push_back({.timestamp = ib.timestamp,
                          .jobId = id,
                          .location = ib.location,
                          .additionalLoad = ib.additionalLoad});
    }

    ScheduleResult res{
        .jobId = id, .schedule = blocks, .impact = output.impact};

    std::lock_guard<std::mutex> lock(g_mutex);
    g_storage[id] = res;

    co_return id;
}

auto get(const std::string &jobIdString) -> drogon::Task<ScheduleResult> {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_storage.contains(jobIdString)) {
        co_return g_storage[jobIdString];
    }
    // Return empty result if not found
    co_return ScheduleResult{};
}

auto get(time_point start, time_point end)
    -> drogon::Task<std::vector<ScheduleBlock>> {
    std::lock_guard<std::mutex> lock(g_mutex);
    std::vector<ScheduleBlock> result;

    for (const auto &[id, res] : g_storage) {
        for (const auto &block : res.schedule) {
            if (block.timestamp >= start && block.timestamp < end) {
                result.push_back(block);
            }
        }
    }
    co_return result;
}

auto deleteSchedule(const std::string &jobId) -> drogon::Task<> {
    // Validate ID format (mimic real implementation)
    scheduler::utils::parseStringIDtoInt(jobId);

    std::lock_guard<std::mutex> lock(g_mutex);
    g_storage.erase(jobId);
    co_return;
}

} // namespace scheduler::calendar
