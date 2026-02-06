#ifndef SCHEDULER
#define SCHEDULER
#pragma once

#include "StatsAPIClient.hpp"
#include "structs/JobRequest.hpp"
#include "structs/SchedulerOutput.hpp"

namespace scheduler {

/**
 * @class Scheduler
 * @brief The main schedule optimization engine.
 *
 * The scheduler itself is stateless. It produces a SchedulerOutput
 * containing the optimal allocation and impact metrics. It has no
 * knowledge of persistence or API concerns.
 */
class Scheduler {
  private:
    static constexpr unsigned int KWH = 1000 * 60 * 60;

    StatsAPIClient stats_api;

  public:
    auto scheduleJob(JobRequest job) -> drogon::Task<SchedulerOutput>;
};

} // namespace scheduler

#endif
