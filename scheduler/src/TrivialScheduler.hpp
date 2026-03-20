#ifndef SCHEDULER_TRIVIAL_SCHEDULER_HPP
#define SCHEDULER_TRIVIAL_SCHEDULER_HPP
#pragma once

#include "SchedulerBase.hpp"

namespace scheduler {

/**
 * @class TrivialScheduler
 * @brief A dumb greedy scheduler for computing a trivial (unoptimized) schedule
 * baseline.
 */
class TrivialScheduler : public SchedulerBase {
  protected:
    auto doScheduleJob(JobRequest job)
        -> drogon::Task<SchedulerOutput> override;
};

} // namespace scheduler

#endif // SCHEDULER_TRIVIAL_SCHEDULER_HPP
