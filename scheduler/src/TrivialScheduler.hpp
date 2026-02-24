#ifndef SCHEDULER_TRIVIAL_SCHEDULER_HPP
#define SCHEDULER_TRIVIAL_SCHEDULER_HPP
#pragma once

#include "StatsAPIClient.hpp"
#include "structs/JobRequest.hpp"
#include "structs/SchedulerOutput.hpp"

namespace scheduler {

/**
 * @class TrivialScheduler
 * @brief A dumb greedy scheduler for computing a trivial (unoptimized) schedule baseline.
 */
class TrivialScheduler {
  private:
    static constexpr unsigned int KWH = 1000 * 60 * 60;
    StatsAPIClient stats_api;

  public:
    auto scheduleJob(JobRequest job) -> drogon::Task<SchedulerOutput>;
};

} // namespace scheduler

#endif // SCHEDULER_TRIVIAL_SCHEDULER_HPP
