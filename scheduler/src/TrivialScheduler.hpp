#ifndef SCHEDULER_TRIVIAL_SCHEDULER_HPP
#define SCHEDULER_TRIVIAL_SCHEDULER_HPP
#pragma once

#include "SchedulerBase.hpp"
#include "structs/SchedulerOutput.hpp"

namespace scheduler {

/**
 * @class TrivialScheduler
 * @brief A dumb greedy scheduler for computing a trivial (unoptimized) schedule
 * baseline.
 */
class TrivialScheduler : public SchedulerBase {
  public:
    using SchedulerBase::SchedulerBase;
    auto scheduleJob(JobRequest job) -> drogon::Task<SchedulerOutput>;
};

} // namespace scheduler

#endif // SCHEDULER_TRIVIAL_SCHEDULER_HPP
