#include "ScheduleController.hpp"
#include <JobRequest.hpp>

using Callback = std::function<void(const drogon::HttpResponsePtr &)>;

auto ScheduleController::calculateSchedule(const drogon::HttpRequestPtr req,
                                           Callback callback)
    -> drogon::Task<void> {

    auto jsonPtr = req->jsonObject();
    if (!jsonPtr) {
        auto resp = drogon::HttpResponse::newHttpResponse();
        resp->setStatusCode(drogon::k400BadRequest);
        resp->setBody("Invalid JSON");
        callback(resp);
        co_return;
    }

    auto &json = *jsonPtr;

    // manual validation eeeee... find solution later
    // (will have to consider library or learn the basic functionality drogon
    // provides)

    if (!json.isMember("job_spec")) {
        auto resp = drogon::HttpResponse::newHttpResponse();
        resp->setStatusCode(drogon::k400BadRequest);
        resp->setBody("Missing job_spec field");
        callback(resp);
        co_return;
    }

    const auto &jobSpec = json["job_spec"];

    if (!jobSpec.isMember("deadline") || !jobSpec.isMember("type") ||
        !jobSpec.isMember("work") || !jobSpec.isMember("jobId")) {
        auto resp = drogon::HttpResponse::newHttpResponse();
        resp->setStatusCode(drogon::k400BadRequest);
        resp->setBody("Missing fields in job_spec");
        callback(resp);
        co_return;
    }

    const long long deadline = jobSpec["deadline"].asInt64();
    const std::string type = jobSpec["type"].asString();
    const double work = jobSpec["work"].asDouble();
    const int jobId = jobSpec["jobId"].asInt();

    JobRequest jobRequest(deadline, type, work, jobId);

    Scheduler scheduler;
    double emissions = co_await scheduler.calculateSchedule(jobRequest);

    Json::Value ret;
    ret["emissions"] = emissions;

    Json::Value scheduleJson;
    const auto &fullSchedule = scheduler.getSchedule();
    for (const auto &[dcId, scheduleForDC] : fullSchedule)
        scheduleJson[std::to_string(dcId)] = scheduleForDC.toJson();
    ret["schedule"] = scheduleJson;

    auto resp = drogon::HttpResponse::newHttpJsonResponse(ret);
    callback(resp);
    co_return;
}
