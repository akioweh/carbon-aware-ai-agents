#ifndef SCHEDULE_CONTROLLER_HPP
#define SCHEDULE_CONTROLLER_HPP
#pragma once

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
    METHOD_LIST_END

    [[nodiscard]] auto calculateSchedule(drogon::HttpRequestPtr,
                                         JobRequest) const
        -> drogon::Task<drogon::HttpResponsePtr>;

    [[nodiscard]] auto getSchedule(drogon::HttpRequestPtr,
                                   TimeIntervalParams) const
        -> drogon::Task<drogon::HttpResponsePtr>;
};

} // namespace scheduler::controllers

#endif
