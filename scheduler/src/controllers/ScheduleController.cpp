#include "ScheduleController.hpp"
#include "ScheduledInterval.hpp"
#include <JobRequest.hpp>
#include <utils/Utils.hpp>

using Callback = std::function<void(const drogon::HttpResponsePtr &)>;

namespace {
void sendBadRequest(const Callback &callback, std::string_view message) {
    auto resp = drogon::HttpResponse::newHttpResponse();
    resp->setStatusCode(drogon::k400BadRequest);
    Json::Value err;
    err["error"] = std::string(message);
    resp->setBody(err.toStyledString());
    resp->setContentTypeCode(drogon::CT_APPLICATION_JSON);
    callback(resp);
}

auto generateJobId() -> std::string {
    static int counter = 0;
    return "job-" + std::to_string(++counter);
}
} // namespace

auto ScheduleController::getSchedule(drogon::HttpRequestPtr req,
                                     Callback callback) -> drogon::Task<void> {

    // TODO: empty stub awaiting stats component's calendar persistence support
    Json::Value ret(Json::arrayValue);
    const auto resp = drogon::HttpResponse::newHttpJsonResponse(ret);
    callback(resp);
    co_return;
}

auto ScheduleController::calculateSchedule(drogon::HttpRequestPtr req,
                                           Callback callback)
    -> drogon::Task<void> {

    const auto jsonPtr = req->jsonObject();
    if (!jsonPtr) {
        sendBadRequest(callback, "Invalid JSON");
        co_return;
    }

    const auto &json = *jsonPtr;

    if (!json.isMember("job_type") || !json.isMember("workload_amount") ||
        !json.isMember("earliest_start") || !json.isMember("latest_finish")) {
        sendBadRequest(callback, "Missing required fields");
        co_return;
    }

    const auto jobType = json["job_type"].asString();
    const auto workload = json["workload_amount"].asDouble();
    const auto earliestStartStr = json["earliest_start"].asString();
    const auto latestFinishStr = json["latest_finish"].asString();

    // i like haskell better
    auto parseResult =
        scheduler::utils::parseIso8601(earliestStartStr)
            .and_then([&](auto timePoint) -> auto {
                return scheduler::utils::parseIso8601(latestFinishStr)
                    .transform([timePoint](auto latestFinish) -> auto {
                        return std::make_pair(timePoint, latestFinish);
                    });
            });
    if (!parseResult) {
        sendBadRequest(callback, parseResult.error());
        co_return;
    }
    const auto &[earliestStart, latestFinish] = parseResult.value();

    std::string jobId = generateJobId();

    const auto jobRequest =
        JobRequest(jobType, workload, earliestStart, latestFinish, jobId);

    auto scheduler = Scheduler{};

    SchedulingImpact impact = co_await scheduler.calculateSchedule(jobRequest);

    Json::Value ret;
    ret["schedule_id"] = "sched-" + jobId;
    ret["message"] = "Schedule created successfully";

    Json::Value blocks(Json::arrayValue);
    const auto &fullSchedule = scheduler.getSchedule();

    for (const auto &interval : fullSchedule | std::views::transform(toJson)) {
        Json::Value block;
        block["timestamp"] = interval["timestamp"]; // Already string from
                                                    // ScheduledInterval::toJson
        block["location"] = interval["location"];
        block["job_id"] = interval["job_id"];
        block["additional_load"] = interval["additional_load"];

        blocks.append(block);
    }

    ret["scheduled_blocks"] = blocks;

    ret["impact"] = toJson(impact);

    const auto resp = drogon::HttpResponse::newHttpJsonResponse(ret);
    callback(resp);
    co_return;
}
