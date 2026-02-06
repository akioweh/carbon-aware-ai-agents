#ifndef SCHEDULER_OUTPUT_HPP
#define SCHEDULER_OUTPUT_HPP
#pragma once

#include "structs/ScheduleResult.hpp"
#include <chrono>
#include <string>
#include <vector>

/**
 * @class InternalBlock
 * @brief The scheduler's output block — a unit of scheduled work with no
 * persistence or API concerns.
 *
 * Unlike ScheduleBlock (the API DTO), this carries no jobId because the
 * scheduler doesn't know it — the DB assigns it on persistence.
 */
struct InternalBlock {
    std::chrono::system_clock::time_point timestamp;
    std::string location;
    double additionalLoad{};
};

/**
 * @class SchedulerOutput
 * @brief The complete output of the scheduling optimization engine.
 *
 * Contains the raw optimization results (scheduled blocks without job IDs)
 * and the computed environmental impact. The controller layer is responsible
 * for persisting this and constructing the API DTO (ScheduleResult) with
 * the DB-assigned job ID.
 */
struct SchedulerOutput {
    std::vector<InternalBlock> blocks;
    ScheduleImpact impact{};
};

#endif // SCHEDULER_OUTPUT_HPP
