#include "ScheduleController.hpp"
#include <JobRequest.hpp>

using Callback = std::function<void(const drogon::HttpResponsePtr &)>;

namespace {
void sendBadRequest(const Callback &callback, std::string_view message) {
    auto resp = drogon::HttpResponse::newHttpResponse();
    resp->setStatusCode(drogon::k400BadRequest);
    resp->setBody(std::string(message));
    callback(resp);
}
} // namespace

auto ScheduleController::calculateSchedule(const drogon::HttpRequestPtr req,
                                           Callback callback)
    -> drogon::Task<void> {

    const auto jsonPtr = req->jsonObject();
    if (!jsonPtr) {
        sendBadRequest(callback, "Invalid JSON");
        co_return;
    }

    const auto &json = *jsonPtr;

    // manual validation eeeee... find solution later
    // (will have to consider library or learn the basic functionality drogon
    // provides)

    if (!json.isMember("job_spec")) {
        sendBadRequest(callback, "Missing job_spec field");
        co_return;
    }

    const auto &jobSpec = json["job_spec"];

    if (!jobSpec.isMember("deadline") || !jobSpec.isMember("type") ||
        !jobSpec.isMember("work") || !jobSpec.isMember("jobId")) {
        sendBadRequest(callback, "Missing fields in job_spec");
        co_return;
    }

    const auto deadline = jobSpec["deadline"].asInt64();
    const auto type = jobSpec["type"].asString();
    const auto work = jobSpec["work"].asDouble();
    const auto jobId = jobSpec["jobId"].asInt();

    const auto jobRequest = JobRequest(deadline, type, work, jobId);

    auto scheduler = Scheduler{};

    auto ret = Json::Value{};
    ret["emissions"] = co_await scheduler.calculateSchedule(jobRequest);

    auto scheduleJson = Json::Value{};
    const auto &fullSchedule = scheduler.getSchedule();
    for (const auto &[dcId, scheduleForDC] : fullSchedule)
        scheduleJson[std::to_string(dcId)] = scheduleForDC.toJson();
    ret["schedule"] = scheduleJson;

    const auto resp = drogon::HttpResponse::newHttpJsonResponse(ret);
    callback(resp);
    co_return;
}
