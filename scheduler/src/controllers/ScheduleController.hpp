#ifndef SCHEDULE_CONTROLLER_HPP
#define SCHEDULE_CONTROLLER_HPP
#pragma once

#include <Scheduler.hpp>
#include <drogon/HttpController.h>
#include <drogon/utils/coroutine.h>

class ScheduleController : public drogon::HttpController<ScheduleController> {
  public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(ScheduleController::calculateSchedule, "/api/schedule",
                  drogon::Post);
    METHOD_LIST_END

    static auto calculateSchedule(
        drogon::HttpRequestPtr req,
        std::function<void(const drogon::HttpResponsePtr &)> callback)
        -> drogon::Task<void>;
};

#endif
