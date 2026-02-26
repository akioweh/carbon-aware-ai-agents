#ifndef SCHEDULER_STATS_FORWARD_CONTROLLER_HPP
#define SCHEDULER_STATS_FORWARD_CONTROLLER_HPP
#pragma once

#include <drogon/HttpController.h>
#include <drogon/HttpResponse.h>
#include <drogon/utils/coroutine.h>
#include <string>

namespace scheduler::controllers {

class StatsForwardController : public drogon::HttpController<StatsForwardController> {
  public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(StatsForwardController::getGreenness, "/api/locations/{1}/metrics/forecast_greenness", drogon::Get);
    METHOD_LIST_END

    [[nodiscard]] auto getGreenness(drogon::HttpRequestPtr req, std::string location) const
        -> drogon::Task<drogon::HttpResponsePtr>;
};

} // namespace scheduler::controllers

#endif // SCHEDULER_STATS_FORWARD_CONTROLLER_HPP
