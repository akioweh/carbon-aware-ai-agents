#ifndef SCHEDULER_SCHEDULE_CONTROLLER_HPP
#define SCHEDULER_SCHEDULE_CONTROLLER_HPP
#include <drogon/HttpRequest.h>
#include <drogon/HttpTypes.h>
#pragma once

#include "structs/DatacenterIdentifierParam.hpp"
#include "structs/JobRequest.hpp"
#include "structs/ScheduleIdentifierParam.hpp"
#include "structs/TimeIntervalParams.hpp"
#include <drogon/HttpController.h>
#include <drogon/HttpResponse.h>
#include <drogon/utils/coroutine.h>

namespace scheduler::controllers {

class ScheduleController : public drogon::HttpController<ScheduleController> {
  public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(ScheduleController::calculateSchedule, "/api/schedules",
                  drogon::Post);
    ADD_METHOD_TO(ScheduleController::getSchedule, "/api/schedules",
                  drogon::Get);
    ADD_METHOD_TO(ScheduleController::deleteSchedule,
                  "/api/schedules/{schedule_id}", drogon::Delete);
    ADD_METHOD_TO(ScheduleController::getSpecificSchedule,
                  "/api/schedules/{schedule_id}", drogon::Get);
    ADD_METHOD_TO(ScheduleController::getSpecificTrivialSchedule,
                  "/api/schedules/{schedule_id}/trivial", drogon::Get);
    ADD_METHOD_TO(ScheduleController::getScheduleSummaries,
                  "/api/schedules/summary", drogon::Get);
    ADD_METHOD_TO(ScheduleController::getForecast, "/api/forecast",
                  drogon::Get);
    METHOD_LIST_END

    [[nodiscard]] auto calculateSchedule(drogon::HttpRequestPtr,
                                         JobRequest) const
        -> drogon::Task<drogon::HttpResponsePtr>;

    [[nodiscard]] auto getSchedule(drogon::HttpRequestPtr,
                                   DatacenterIdentifierParam,
                                   TimeIntervalParams) const
        -> drogon::Task<drogon::HttpResponsePtr>;

    [[nodiscard]] auto deleteSchedule(drogon::HttpRequestPtr,
                                      ScheduleIdentifierParam) const
        -> drogon::Task<drogon::HttpResponsePtr>;
    [[nodiscard]] auto getSpecificSchedule(drogon::HttpRequestPtr,
                                           ScheduleIdentifierParam,
                                           DatacenterIdentifierParam) const
        -> drogon::Task<drogon::HttpResponsePtr>;
    [[nodiscard]] auto
        getSpecificTrivialSchedule(drogon::HttpRequestPtr,
                                   ScheduleIdentifierParam,
                                   DatacenterIdentifierParam) const
        -> drogon::Task<drogon::HttpResponsePtr>;
    [[nodiscard]] auto getScheduleSummaries(drogon::HttpRequestPtr) const
        -> drogon::Task<drogon::HttpResponsePtr>;

    [[nodiscard]] auto getForecast(drogon::HttpRequestPtr,
                                   DatacenterIdentifierParam) const
        -> drogon::Task<drogon::HttpResponsePtr>;
};

} // namespace scheduler::controllers

#endif // SCHEDULER_SCHEDULE_CONTROLLER_HPP
