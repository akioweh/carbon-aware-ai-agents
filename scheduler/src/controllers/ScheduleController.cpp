#include <controllers/ScheduleController.hpp>
#include <structs/JobRequest.hpp>
#include <structs/ScheduleBlock.hpp>
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

    const auto jobRequest = JobRequest{
        .job_type = jobType,
        .workload_amount = workload,
        .earliest_start = earliestStart,
        .latest_finish = latestFinish,
    };

    const auto res = co_await schedulingQueue.computeSchedule(jobRequest);
    const auto ret = toJson(res);
    const auto resp = drogon::HttpResponse::newHttpJsonResponse(ret);
    callback(resp);
    co_return;
}
