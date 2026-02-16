#define BOOST_TEST_MODULE SchedulerIntegrationTest

#include "exceptions/ExceptionHandler.hpp"
#include "utils/Utils.hpp"
#include <boost/test/included/unit_test.hpp>
#include <chrono>
#include <drogon/HttpController.h>
#include <drogon/drogon.h>
#include <filesystem>
#include <thread>

using namespace drogon;

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
        t = std::jthread([]() -> void { drogon::app().run(); });

        // Wait for server to start
        using namespace std::chrono_literals;
        auto start = std::chrono::steady_clock::now();
        while (!drogon::app().isRunning()) {
            if (std::chrono::steady_clock::now() - start > 10s) {
                throw std::runtime_error("Timeout waiting for Drogon to start");
            }
            std::this_thread::sleep_for(10ms);
        }
    }

    ~SchedulerGlobalFixture() { drogon::app().quit(); }

    std::jthread t;
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
    BOOST_CHECK((*json).isMember("scheduled_blocks"));
    BOOST_CHECK((*json).isMember("impact"));
    BOOST_CHECK((*json)["scheduled_blocks"].isArray());
    BOOST_CHECK((*json)["scheduled_blocks"].size() > 0);

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
    auto deleteReq = HttpRequest::newHttpRequest();
    deleteReq->setMethod(drogon::Delete);
    deleteReq->setPath("/api/schedule/" + jobId);

    auto deleteRespPair = client->sendRequest(deleteReq);
    BOOST_REQUIRE_EQUAL(deleteRespPair.first, ReqResult::Ok);
    auto deleteResponse = deleteRespPair.second;
    BOOST_REQUIRE(deleteResponse);
    BOOST_CHECK_EQUAL(deleteResponse->getStatusCode(), k200OK);

    // 4. Verify Deletion (GET should not return the deleted blocks)
    auto verifyReq = HttpRequest::newHttpRequest();
    verifyReq->setMethod(drogon::Get);
    verifyReq->setPath("/api/schedule");
    verifyReq->setParameter("start_time",
                            scheduler::utils::toIso8601(tomorrow));
    verifyReq->setParameter("end_time", scheduler::utils::toIso8601(day_after));

    auto verifyRespPair = client->sendRequest(verifyReq);
    BOOST_REQUIRE_EQUAL(verifyRespPair.first, ReqResult::Ok);
    auto verifyResponse = verifyRespPair.second;
    BOOST_REQUIRE(verifyResponse);

    auto verifyJson = verifyResponse->getJsonObject();
    BOOST_REQUIRE(verifyJson);
    BOOST_CHECK(verifyJson->isArray());
    // Should be empty now (assuming clean DB state at start and no other jobs)
    BOOST_CHECK_EQUAL(verifyJson->size(), 0);
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

BOOST_AUTO_TEST_CASE(test_delete_non_existent) {
    auto client = HttpClient::newHttpClient("http://127.0.0.1:6969");
    auto deleteReq = HttpRequest::newHttpRequest();
    deleteReq->setMethod(drogon::Delete);
    deleteReq->setPath("/api/schedule/sched-99999999"); // Non-existent ID

    auto deleteRespPair = client->sendRequest(deleteReq);
    BOOST_REQUIRE_EQUAL(deleteRespPair.first, ReqResult::Ok);
    auto deleteResponse = deleteRespPair.second;
    BOOST_REQUIRE(deleteResponse);
    // Should be 200 OK (idempotent)
    BOOST_CHECK_EQUAL(deleteResponse->getStatusCode(), k200OK);
}

BOOST_AUTO_TEST_CASE(test_delete_invalid_id) {
    auto client = HttpClient::newHttpClient("http://127.0.0.1:6969");
    auto deleteReq = HttpRequest::newHttpRequest();
    deleteReq->setMethod(drogon::Delete);
    deleteReq->setPath("/api/schedule/invalidid"); // Invalid format (no dash)

    auto deleteRespPair = client->sendRequest(deleteReq);
    BOOST_REQUIRE_EQUAL(deleteRespPair.first, ReqResult::Ok);
    auto deleteResponse = deleteRespPair.second;
    BOOST_REQUIRE(deleteResponse);
    // Should be 422 Unprocessable Entity (ValidationException)
    BOOST_CHECK_EQUAL(deleteResponse->getStatusCode(), k422UnprocessableEntity);
}

BOOST_AUTO_TEST_CASE(test_list_jobs_and_get_specific) {
    auto client = HttpClient::newHttpClient("http://127.0.0.1:6969");

    // Helper to create a job
    auto createJob = [&](const std::string &type) -> std::string {
        Json::Value job;
        job["job_type"] = type;
        job["workload_amount"] = 30.0;
        auto now = std::chrono::system_clock::now();
        auto start = now + std::chrono::hours(24);
        auto end = start + std::chrono::hours(24);
        job["earliest_start"] = scheduler::utils::toIso8601(start);
        job["latest_finish"] = scheduler::utils::toIso8601(end);

        auto req = HttpRequest::newHttpJsonRequest(job);
        req->setMethod(drogon::Post);
        req->setPath("/api/schedule");

        auto respPair = client->sendRequest(req);
        BOOST_REQUIRE_EQUAL(respPair.first, ReqResult::Ok);
        auto response = respPair.second;
        BOOST_REQUIRE(response);
        BOOST_REQUIRE_EQUAL(response->getStatusCode(), k200OK);

        auto json = response->getJsonObject();
        return (*json)["schedule_id"].asString();
    };

    // 1. Create two jobs
    std::string id1 = createJob("batch");
    std::string id2 = createJob("inference");

    BOOST_TEST_MESSAGE("Created jobs: " << id1 << ", " << id2);

    // 2. List Jobs (GET /api/schedule/jobs)
    auto listReq = HttpRequest::newHttpRequest();
    listReq->setMethod(drogon::Get);
    listReq->setPath("/api/schedule/jobs");

    auto listRespPair = client->sendRequest(listReq);
    BOOST_REQUIRE_EQUAL(listRespPair.first, ReqResult::Ok);
    auto listResponse = listRespPair.second;
    BOOST_REQUIRE(listResponse);
    BOOST_CHECK_EQUAL(listResponse->getStatusCode(), k200OK);

    auto listJson = listResponse->getJsonObject();
    BOOST_REQUIRE(listJson);
    BOOST_CHECK(listJson->isArray());
    BOOST_TEST_MESSAGE("List Jobs Response: " << listJson->toStyledString());

    // Verify both IDs are present
    bool found1 = false;
    bool found2 = false;
    for (const auto &id : *listJson) {
        if (id.asString() == id1)
            found1 = true;
        if (id.asString() == id2)
            found2 = true;
    }
    BOOST_CHECK(found1);
    BOOST_CHECK(found2);

    // 3. Get Specific Job (GET /api/schedule/{id})
    auto getReq = HttpRequest::newHttpRequest();
    getReq->setMethod(drogon::Get);
    getReq->setPath("/api/schedule/" + id1);

    auto getRespPair = client->sendRequest(getReq);
    BOOST_REQUIRE_EQUAL(getRespPair.first, ReqResult::Ok);
    auto getResponse = getRespPair.second;
    BOOST_REQUIRE(getResponse);
    BOOST_CHECK_EQUAL(getResponse->getStatusCode(), k200OK);

    auto getJson = getResponse->getJsonObject();
    BOOST_REQUIRE(getJson);
    BOOST_CHECK((*getJson).isMember("schedule_id"));
    BOOST_CHECK_EQUAL((*getJson)["schedule_id"].asString(), id1);
    BOOST_CHECK((*getJson).isMember("scheduled_blocks"));
    BOOST_CHECK((*getJson)["scheduled_blocks"].isArray());
    BOOST_CHECK((*getJson).isMember("impact"));
}

BOOST_AUTO_TEST_SUITE_END()
