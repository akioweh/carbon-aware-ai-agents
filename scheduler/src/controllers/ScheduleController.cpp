#include "controllers/ScheduleController.hpp"
#include "Calendar.hpp"
#include "SchedulingQueue.hpp"
#include "TrivialScheduler.hpp"
#include "structs/DatacenterIdentifierParam.hpp"
#include "structs/JobRequest.hpp"
#include "structs/ScheduleIdentifierParam.hpp"
#include "structs/TimeIntervalParams.hpp"
#include "utils/TimeGridder.hpp"
#include <drogon/HttpRequest.h>
#include <drogon/HttpResponse.h>
#include <drogon/HttpTypes.h>

namespace scheduler::controllers {

using namespace std;
using namespace drogon;
using namespace scheduler;

auto ScheduleController::
    getSchedule( // NOLINT(readability-convert-member-functions-to-static)
        HttpRequestPtr /*req*/, const DatacenterIdentifierParam datacenter,
        const TimeIntervalParams interval) const -> Task<HttpResponsePtr> {
    const auto res = co_await calendar::get(
        interval.start.value_or(scheduler::utils::MIN_TIME),
        interval.end.value_or(scheduler::utils::MAX_TIME), datacenter.name);
    auto ret = Json::Value(Json::arrayValue);
    for (const auto &block : res)
        ret.append(toJson(block));
    const auto resp = HttpResponse::newHttpJsonResponse(ret);
    co_return resp;
}

auto ScheduleController::
    getSpecificSchedule( // NOLINT(readability-convert-member-functions-to-static)
        HttpRequestPtr /*req*/, const ScheduleIdentifierParam schedule_id,
        const DatacenterIdentifierParam datacenter) const
    -> Task<HttpResponsePtr> {

    auto res =
        co_await calendar::get(schedule_id.getScheduleId(), datacenter.name);

    co_return HttpResponse::newHttpJsonResponse(toJson(res));
}

auto ScheduleController::
    getSpecificTrivialSchedule( // NOLINT(readability-convert-member-functions-to-static)
        HttpRequestPtr /*req*/, const ScheduleIdentifierParam schedule_id,
        const DatacenterIdentifierParam datacenter) const
    -> Task<HttpResponsePtr> {
    const auto res = co_await calendar::getTrivial(schedule_id.getScheduleId(),
                                                   datacenter.name);

    const auto resp = HttpResponse::newHttpJsonResponse(toJson(res));
    co_return resp;
}

auto ScheduleController::
    deleteSchedule( // NOLINT(readability-convert-member-functions-to-static)
        HttpRequestPtr /*req*/, const ScheduleIdentifierParam schedule_id) const
    -> Task<HttpResponsePtr> {
    co_await calendar::deleteSchedule(schedule_id.getScheduleId());
    auto resp = HttpResponse::newHttpResponse();
    resp->setStatusCode(k204NoContent);
    co_return resp;
}

auto ScheduleController::
    calculateSchedule( // NOLINT(readability-convert-member-functions-to-static)
        HttpRequestPtr /*req*/, const JobRequest job_request) const
    -> Task<HttpResponsePtr> {
    auto output = co_await schedulingQueue.computeSchedule(job_request);

    // persist and get the DB-assigned job ID
    const auto schedule_id = co_await calendar::add(output);

    auto trivialResult = optional<ScheduleResult>{};
    // Also compute trivial and persist
    try {
        auto tSched = TrivialScheduler{};
        auto tOutput = co_await tSched.scheduleJob(job_request);
        co_await calendar::addTrivial(tOutput, schedule_id);

    } catch (const exception &e) {
        LOG_WARN << "Failed to generate trivial schedule for " << schedule_id
                 << ": " << e.what();
    }

    // construct the API DTO with the real job ID
    auto result = scheduler::ScheduleCreatedResponse{.scheduleId = schedule_id};

    co_return HttpResponse::newHttpJsonResponse(toJson(result));
}

auto ScheduleController::
    getScheduleSummaries( // NOLINT(readability-convert-member-functions-to-static)
        HttpRequestPtr /*req*/) const -> Task<HttpResponsePtr> {
    const auto scheduleSummaries = co_await calendar::scheduleSummaries();
    Json::Value ret(Json::arrayValue);
    for (const auto &scheduleSummary : scheduleSummaries)
        ret.append(toJson(scheduleSummary));
    const auto resp = HttpResponse::newHttpJsonResponse(ret);
    co_return resp;
}
} // namespace scheduler::controllers
