#include "Calendar.hpp"
#include "structs/TimeIntervalParams.hpp"
#include <controllers/ScheduleController.hpp>
#include <drogon/HttpResponse.h>
#include <drogon/HttpTypes.h>
#include <structs/JobRequest.hpp>
#include <structs/ScheduleBlock.hpp>
#include <utils/Utils.hpp>

using namespace std;
using namespace drogon;

auto ScheduleController::getSchedule(
    HttpRequestPtr /*req*/, const TimeIntervalParams /*time_interval*/) const
    -> Task<HttpResponsePtr> {
    // TODO: use time_interval to filter results once calendar supports it
    const auto res = co_await calendarService::get();
    auto ret = Json::Value(Json::arrayValue);
    for (const auto &block : res)
        ret.append(toJson(block));
    const auto resp = HttpResponse::newHttpJsonResponse(ret);
    co_return resp;
}

auto ScheduleController::calculateSchedule(HttpRequestPtr /*req*/,
                                           const JobRequest job_request) const
    -> Task<HttpResponsePtr> {
    const auto res = co_await schedulingQueue.computeSchedule(job_request);
    const auto ret = toJson(res);
    const auto resp = HttpResponse::newHttpJsonResponse(ret);
    co_return resp;
}
