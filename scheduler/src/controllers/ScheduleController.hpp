#ifndef SCHEDULER_SCHEDULE_CONTROLLER_HPP
#define SCHEDULER_SCHEDULE_CONTROLLER_HPP
#pragma once

#include "structs/JobIdentifierParam.hpp"
#include "structs/JobRequest.hpp"
#include "structs/TimeIntervalParams.hpp"
#include <drogon/HttpController.h>
#include <drogon/HttpResponse.h>
#include <drogon/utils/coroutine.h>

namespace scheduler::controllers {

class ScheduleController : public drogon::HttpController<ScheduleController> {
  public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(ScheduleController::calculateSchedule, "/api/schedule",
                  drogon::Post);
    ADD_METHOD_TO(ScheduleController::getSchedule, "/api/schedule",
                  drogon::Get);
    ADD_METHOD_TO(ScheduleController::deleteSchedule, "/api/schedule/{job_id}",
                  drogon::Delete);
    ADD_METHOD_TO(ScheduleController::getSpecificSchedule,
                  "/api/schedule/{job_id}", drogon::Get);
    ADD_METHOD_TO(ScheduleController::getScheduledJobs, "/api/schedule/jobs",
                  drogon::Get);
    METHOD_LIST_END

    [[nodiscard]] auto calculateSchedule(drogon::HttpRequestPtr,
                                         JobRequest) const
        -> drogon::Task<drogon::HttpResponsePtr>;

    [[nodiscard]] auto getSchedule(drogon::HttpRequestPtr,
                                   TimeIntervalParams) const
        -> drogon::Task<drogon::HttpResponsePtr>;

    [[nodiscard]] auto deleteSchedule(drogon::HttpRequestPtr,
                                      JobIdentifierParam) const
        -> drogon::Task<drogon::HttpResponsePtr>;
    [[nodiscard]] auto getSpecificSchedule(drogon::HttpRequestPtr,
                                           JobIdentifierParam) const
        -> drogon::Task<drogon::HttpResponsePtr>;
    [[nodiscard]] auto getScheduledJobs(drogon::HttpRequestPtr) const
        -> drogon::Task<drogon::HttpResponsePtr>;
};

} // namespace scheduler::controllers

#endif // SCHEDULER_SCHEDULE_CONTROLLER_HPP
