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

namespace {
auto badRequest(string_view message, HttpStatusCode code = k400BadRequest) {
    auto resp = HttpResponse::newHttpResponse();
    resp->setStatusCode(code);
    Json::Value err;
    err["error"] = string(message);
    resp->setBody(err.toStyledString());
    resp->setContentTypeCode(CT_APPLICATION_JSON);
    return resp;
}
} // namespace
auto ScheduleController::getSchedule(
    HttpRequestPtr /*unused*/,
    const optional<TimeIntervalParams> time_interval) const
    -> Task<HttpResponsePtr> {
    if (!time_interval)
        co_return badRequest("Input data validation error",
                             k422UnprocessableEntity);

    // TODO: use time_interval to filter results once calendar supports it
    const auto res = calendarService.get();
    auto ret = Json::Value(Json::arrayValue);
    for (const auto &[jobId, schedulePair] : res) {
        const auto &[impact, scheduleBlocks] = schedulePair;
        for (const auto &block : scheduleBlocks) {
            ret.append(toJson(block));
        }
    }
    const auto resp = HttpResponse::newHttpJsonResponse(ret);
    co_return resp;
}

auto ScheduleController::calculateSchedule(
    HttpRequestPtr /*unused*/, const optional<JobRequest> job_request) const
    -> Task<HttpResponsePtr> {
    if (!job_request)
        co_return badRequest("Input data validation error",
                             k422UnprocessableEntity);

    const auto res =
        co_await schedulingQueue.computeSchedule(job_request.value());
    const auto ret = toJson(res);
    const auto resp = HttpResponse::newHttpJsonResponse(ret);
    co_return resp;
}
