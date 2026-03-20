#include "controllers/ForecastController.hpp"
#include "StatsAPIClient.hpp"
#include "structs/TimeIntervalParams.hpp"
#include <drogon/HttpRequest.h>
#include <drogon/HttpResponse.h>
#include <drogon/HttpTypes.h>
#include <vector>

namespace scheduler::controllers {

using namespace drogon;

auto ForecastController::
    getForecast( // NOLINT(readability-convert-member-functions-to-static)
        HttpRequestPtr /*req*/, const DatacenterIdentifierParam datacenter,
        const TimeIntervalParams interval) const -> Task<HttpResponsePtr> {
    const auto stats = StatsAPIClient();
    Json::Value ret;
    if (datacenter.name == scheduler::calendar::ANY_DATACENTER) {
        ret = toJson(co_await stats.getAllDatacenters({}, interval));
    } else {
        ret = toJson(std::vector{
            co_await stats.getDatacenter(datacenter.name, interval)});
    }
    const auto resp = HttpResponse::newHttpJsonResponse(ret);
    co_return resp;
}

} // namespace scheduler::controllers
