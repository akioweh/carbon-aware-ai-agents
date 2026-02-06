#define BOOST_TEST_MODULE SchedulerIntegrationTest
#include "exceptions/ExceptionHandler.hpp"
#include "utils/Utils.hpp"
#include <boost/test/included/unit_test.hpp>
#include <chrono>
#include <drogon/HttpController.h>
#include <drogon/drogon.h>
#include <filesystem>
#include <fstream>
#include <thread>

using namespace drogon;

// Helper to read file content
auto readFile(const std::string &path) -> std::string {
    std::ifstream t(path);
    std::stringstream buffer;
    buffer << t.rdbuf();
    return buffer.str();
}

struct SchedulerGlobalFixture {
    SchedulerGlobalFixture() {
        // Ensure clean state
        if (std::filesystem::exists("scheduler_test.db")) {
            std::filesystem::remove("scheduler_test.db");
        }

        // Load test config
        drogon::app().loadConfigFile("config.test.json");

        // Register Exception Handler
        scheduler::exceptions::registerExceptionHandler();

        // Start the app in a thread
        t = std::thread([]() -> void { drogon::app().run(); });

        // Wait for server to start
        std::this_thread::sleep_for(std::chrono::seconds(2));
    }

    ~SchedulerGlobalFixture() {
        drogon::app().quit();
        if (t.joinable())
            t.join();
    }

    std::thread t;
};

BOOST_TEST_GLOBAL_FIXTURE(SchedulerGlobalFixture);

BOOST_AUTO_TEST_SUITE(SchedulerIntegration)

BOOST_AUTO_TEST_CASE(test_schedule_lifecycle) {
    auto client = HttpClient::newHttpClient("http://127.0.0.1:6969");

    // 1. Create a schedule (POST)
    Json::Value job;
    job["job_type"] = "batch";
    job["workload_amount"] = 50.0;
    // Use dates in the future to ensure we hit the "forecast" part of stats
    // The stats service generates next week prediction.
    // Let's pick a time tomorrow.
    auto now = std::chrono::system_clock::now();
    auto tomorrow = now + std::chrono::hours(24);
    auto day_after = tomorrow + std::chrono::hours(24);

    job["earliest_start"] = scheduler::utils::toIso8601(tomorrow);
    job["latest_finish"] = scheduler::utils::toIso8601(day_after);

    auto req = HttpRequest::newHttpJsonRequest(job);
    req->setMethod(drogon::Post);
    req->setPath("/api/schedule");

    // Make synchronous request
    auto respPair = client->sendRequest(req);
    BOOST_REQUIRE_EQUAL(respPair.first, ReqResult::Ok);
    auto response = respPair.second;
    BOOST_REQUIRE(response);

    BOOST_TEST_MESSAGE("Create Schedule Response: " << response->getBody());
    BOOST_CHECK_EQUAL(response->getStatusCode(), k200OK);

    auto json = response->getJsonObject();
    BOOST_REQUIRE(json);

    // Debug output
    // BOOST_TEST_MESSAGE("JSON: " << json->toStyledString());

    std::string jobId = (*json)["schedule_id"].asString();
    BOOST_CHECK(!jobId.empty());

    // Check fields in response
    BOOST_CHECK((*json).isMember("schedule"));
    BOOST_CHECK((*json).isMember("impact"));
    BOOST_CHECK((*json)["schedule"].isArray());
    BOOST_CHECK((*json)["schedule"].size() > 0);

    // 2. Retrieve the schedule (GET)
    auto getReq = HttpRequest::newHttpRequest();
    getReq->setMethod(drogon::Get);
    getReq->setPath("/api/schedule");
    getReq->setParameter("start_time", scheduler::utils::toIso8601(tomorrow));
    getReq->setParameter("end_time", scheduler::utils::toIso8601(day_after));

    auto getRespPair = client->sendRequest(getReq);
    BOOST_REQUIRE_EQUAL(getRespPair.first, ReqResult::Ok);
    auto getResponse = getRespPair.second;
    BOOST_REQUIRE(getResponse);

    BOOST_TEST_MESSAGE("Get Schedule Response: " << getResponse->getBody());
    BOOST_CHECK_EQUAL(getResponse->getStatusCode(), k200OK);

    auto getJson = getResponse->getJsonObject();
    BOOST_REQUIRE(getJson);
    BOOST_CHECK(getJson->isArray());
    // Should contain at least the blocks we just scheduled
    BOOST_CHECK(getJson->size() > 0);

    // 3. Delete Schedule (Delete)
    // /api/schedule/{schedule_id} is not standard REST, but usually DELETE
    // /api/schedule/ID Let's check ScheduleController definition again. It
    // doesn't seem to have DELETE exposed in METHOD_LIST_BEGIN! I checked
    // ScheduleController.hpp and it only had ADD_METHOD_TO for POST and GET.
    // Let me re-verify ScheduleController.hpp
}

BOOST_AUTO_TEST_CASE(test_invalid_request) {
    auto client = HttpClient::newHttpClient("http://127.0.0.1:6969");

    Json::Value job;
    job["job_type"] = "batch";
    // Missing workload_amount

    // Use dynamic dates for invalid request too, to avoid date parsing errors
    // overshadowing the missing field error if checks are reordered.
    auto now = std::chrono::system_clock::now();
    auto tomorrow = now + std::chrono::hours(24);
    auto day_after = tomorrow + std::chrono::hours(24);

    job["earliest_start"] = scheduler::utils::toIso8601(tomorrow);
    job["latest_finish"] = scheduler::utils::toIso8601(day_after);

    auto req = HttpRequest::newHttpJsonRequest(job);
    req->setMethod(drogon::Post);
    req->setPath("/api/schedule");

    auto respPair = client->sendRequest(req);
    BOOST_REQUIRE_EQUAL(respPair.first, ReqResult::Ok);
    auto response = respPair.second;
    BOOST_REQUIRE(response);

    // Should return 422 Unprocessable Entity or 400 Bad Request
    // The exception handler maps ValidationException to 422
    BOOST_CHECK_EQUAL(response->getStatusCode(), k422UnprocessableEntity);
}

BOOST_AUTO_TEST_SUITE_END()
