#include "Calendar.hpp"
#include "structs/TimeIntervalParams.hpp"
#include <chrono>
#include <controllers/ScheduleController.hpp>
#include <drogon/HttpResponse.h>
#include <drogon/HttpTypes.h>
#include <structs/JobRequest.hpp>
#include <structs/ScheduleBlock.hpp>
#include <utils/Utils.hpp>

using namespace std;
using namespace drogon;

auto ScheduleController::getSchedule(HttpRequestPtr /*req*/,
                                     const TimeIntervalParams interval) const
    -> Task<HttpResponsePtr> {
    const auto res = co_await calendarService::get(
        interval.start.value_or(chrono::system_clock::time_point::min()),
        interval.end.value_or(chrono::system_clock::time_point::max()));
    auto ret = Json::Value(Json::arrayValue);
    for (const auto &block : res)
        ret.append(toJson(block));
    const auto resp = HttpResponse::newHttpJsonResponse(ret);
    co_return resp;
}

auto ScheduleController::calculateSchedule(HttpRequestPtr /*req*/,
                                           const JobRequest job_request) const
    -> Task<HttpResponsePtr> {
    auto output = co_await schedulingQueue.computeSchedule(job_request);

    // persist and get the DB-assigned job ID
    const auto job_id = co_await calendarService::add(output);

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
