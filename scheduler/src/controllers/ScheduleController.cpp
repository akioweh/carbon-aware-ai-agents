#include "controllers/ScheduleController.hpp"
#include "Calendar.hpp"
#include "SchedulingQueue.hpp"
#include "structs/JobIdentifierParam.hpp"
#include "structs/JobRequest.hpp"
#include "structs/ScheduleBlock.hpp"
#include "structs/TimeIntervalParams.hpp"
#include "utils/TimeGridder.hpp"
#include <drogon/HttpResponse.h>
#include <drogon/HttpTypes.h>

namespace scheduler::controllers {

using namespace std;
using namespace drogon;
using namespace scheduler;

auto ScheduleController::getSchedule(HttpRequestPtr /*req*/,
                                     const TimeIntervalParams interval) const
    -> Task<HttpResponsePtr> {
    const auto res = co_await calendar::get(
        interval.start.value_or(scheduler::utils::MIN_TIME),
        interval.end.value_or(scheduler::utils::MAX_TIME));
    auto ret = Json::Value(Json::arrayValue);
    for (const auto &block : res)
        ret.append(toJson(block));
    const auto resp = HttpResponse::newHttpJsonResponse(ret);
    co_return resp;
}

auto ScheduleController::getSpecificSchedule(
    HttpRequestPtr /*req*/, const JobIdentifierParam job_id) const
    -> Task<HttpResponsePtr> {
    const auto res = co_await calendar::get(job_id.jobId);
    const auto resp = HttpResponse::newHttpJsonResponse(toJson(res));
    co_return resp;
}

auto ScheduleController::deleteSchedule(HttpRequestPtr /*req*/,
                                        const JobIdentifierParam job_id) const
    -> Task<HttpResponsePtr> {
    co_await calendar::deleteSchedule(job_id.jobId);
    co_return HttpResponse::newHttpResponse();
}

auto ScheduleController::calculateSchedule(HttpRequestPtr /*req*/,
                                           const JobRequest job_request) const
    -> Task<HttpResponsePtr> {
    auto output = co_await schedulingQueue.computeSchedule(job_request);

    // persist and get the DB-assigned job ID
    const auto job_id = co_await calendar::add(output);

    // construct the API DTO with the real job ID
    auto schedule = vector<ScheduleBlock>{};
    schedule.reserve(output.blocks.size());
    for (auto &block : output.blocks)
        schedule.push_back({
            .timestamp = block.timestamp,
            .jobId = job_id,
            .location = std::move(block.location),
            .additionalLoad = block.additionalLoad,
        });

    const auto result = ScheduleResult{
        .jobId = job_id,
        .schedule = std::move(schedule),
        .impact = output.impact,
    };

    co_return HttpResponse::newHttpJsonResponse(toJson(result));
}

auto ScheduleController::getScheduledJobs(HttpRequestPtr /*req*/) const
    -> Task<HttpResponsePtr> {
    const auto jobIds = co_await calendar::listJobs();
    Json::Value ret(Json::arrayValue);
    for (const auto &id : jobIds)
        ret.append(id);
    const auto resp = HttpResponse::newHttpJsonResponse(ret);
    co_return resp;
}

} // namespace scheduler::controllers
