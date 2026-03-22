#ifndef SCHEDULER_FORECAST_CONTROLLER_HPP
#define SCHEDULER_FORECAST_CONTROLLER_HPP
#pragma once

#include "structs/TimeIntervalParams.hpp"
#include <drogon/HttpController.h>
#include <structs/DatacenterIdentifierParam.hpp>

namespace scheduler::controllers {

class ForecastController : public drogon::HttpController<ForecastController> {
  public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(ForecastController::getForecast, "/api/forecast",
                  drogon::Get);
    METHOD_LIST_END

    [[nodiscard]] auto getForecast(drogon::HttpRequestPtr,
                                   DatacenterIdentifierParam,
                                   TimeIntervalParams) const
        -> drogon::Task<drogon::HttpResponsePtr>;
};

} // namespace scheduler::controllers

#endif // SCHEDULER_FORECAST_CONTROLLER_HPP
