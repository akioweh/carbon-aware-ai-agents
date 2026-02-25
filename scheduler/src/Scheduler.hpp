#ifndef SCHEDULER_SCHEDULER_HPP
#define SCHEDULER_SCHEDULER_HPP
#pragma once

#include "SchedulerBase.hpp"

namespace scheduler {

/**
 * @class Scheduler
 * @brief The main schedule optimization engine.
 *
 * The scheduler itself is stateless. It produces a SchedulerOutput
 * containing the optimal allocation and impact metrics. It has no
 * knowledge of persistence or API concerns.
 */
class Scheduler : public SchedulerBase {
  public:
    auto scheduleJob(JobRequest job) -> drogon::Task<SchedulerOutput>;
};

} // namespace scheduler

#endif // SCHEDULER_SCHEDULER_HPP
