#ifndef FORECAST_CONTROLLER
#define FORECAST_CONTROLLER
#include <drogon/HttpController.h>
#pragma once

#include <structs/DatacenterIdentifierParam.hpp>

namespace scheduler::controllers {

class ForecastController : public drogon::HttpController<ForecastController> {
  public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(ForecastController::getForecast, "/api/forecast",
                  drogon::Get);
    METHOD_LIST_END

    [[nodiscard]] auto getForecast(drogon::HttpRequestPtr,
                                   DatacenterIdentifierParam) const
        -> drogon::Task<drogon::HttpResponsePtr>;
};

} // namespace scheduler::controllers

#endif