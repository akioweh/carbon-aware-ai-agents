#ifndef SCHEDULE_CONTROLLER_HPP
#define SCHEDULE_CONTROLLER_HPP
#include "SchedulingQueue.hpp"
#pragma once

#include <Scheduler.hpp>
#include <drogon/HttpController.h>
#include <drogon/utils/coroutine.h>

class ScheduleController : public drogon::HttpController<ScheduleController> {
  public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(ScheduleController::calculateSchedule, "/api/schedule",
                  drogon::Post);
    ADD_METHOD_TO(ScheduleController::getSchedule, "/api/schedule",
                  drogon::Get);
    METHOD_LIST_END

    auto calculateSchedule(
        drogon::HttpRequestPtr req,
        std::function<void(const drogon::HttpResponsePtr &)> callback)
        -> drogon::Task<void>;

    auto
    getSchedule(drogon::HttpRequestPtr req,
                std::function<void(const drogon::HttpResponsePtr &)> callback)
        -> drogon::Task<void>;

    static std::shared_ptr<SchedulingQueue> schedulingQueue;

    static auto setSchedulingQueue(std::shared_ptr<SchedulingQueue> queue) {
        schedulingQueue = std::move(queue);
    }
};

#endif
