#include "StatsForwardController.hpp"
#include "../utils/Utils.hpp"
#include <drogon/HttpResponse.h>

namespace scheduler::controllers {

using namespace std;
using namespace drogon;

auto StatsForwardController::getGreenness(HttpRequestPtr /*req*/, string location) const
    -> Task<HttpResponsePtr> {
    
    auto jsonPtr = co_await scheduler::utils::makeGetRequest("http://140.238.79.139:5000", "/locations/" + location + "/metrics/forecast_greenness");
    
    auto resp = HttpResponse::newHttpJsonResponse(*jsonPtr);
    co_return resp;
}

} // namespace scheduler::controllers
