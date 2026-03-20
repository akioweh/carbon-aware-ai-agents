#define BOOST_TEST_MODULE SchedulerIntegrationTest

#include "Calendar.hpp"
#include "exceptions/ExceptionHandler.hpp"
#include "structs/SchedulerOutput.hpp"
#include "utils/Utils.hpp"
#include <boost/test/tools/old/interface.hpp>
#include <boost/test/unit_test.hpp>
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
    job["gpu_type"] = "V100_PCIE";
    job["gpu_count"] = 1;
    job["model_size"] = 10;
    job["length"] = 60;
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
    req->setPath("/api/schedules");

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

    // 2. Retrieve the specific schedule to check its fields (GET
    // /api/schedules/{id})
    auto getSpecificReq = HttpRequest::newHttpRequest();
    getSpecificReq->setMethod(drogon::Get);
    getSpecificReq->setPath("/api/schedules/" + jobId);

    auto getSpecificRespPair = client->sendRequest(getSpecificReq);
    BOOST_REQUIRE_EQUAL(getSpecificRespPair.first, ReqResult::Ok);
    auto getSpecificResponse = getSpecificRespPair.second;
    BOOST_REQUIRE(getSpecificResponse);
    BOOST_CHECK_EQUAL(getSpecificResponse->getStatusCode(), k200OK);

    auto specificJson = getSpecificResponse->getJsonObject();
    BOOST_REQUIRE(specificJson);
    BOOST_CHECK((*specificJson).isMember("scheduled_blocks"));
    BOOST_CHECK((*specificJson)["scheduled_blocks"].isArray());
    BOOST_CHECK((*specificJson)["scheduled_blocks"].size() > 0);
    BOOST_CHECK((*specificJson).isMember("impact"));

    // 3. Retrieve the schedule blocks for calendar (GET /api/schedules)
    auto getReq = HttpRequest::newHttpRequest();
    getReq->setMethod(drogon::Get);
    getReq->setPath("/api/schedules");
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

    // 4. Delete Schedule (Delete)
    auto deleteReq = HttpRequest::newHttpRequest();
    deleteReq->setMethod(drogon::Delete);
    deleteReq->setPath("/api/schedules/" + jobId);

    auto deleteRespPair = client->sendRequest(deleteReq);
    BOOST_REQUIRE_EQUAL(deleteRespPair.first, ReqResult::Ok);
    auto deleteResponse = deleteRespPair.second;
    BOOST_REQUIRE(deleteResponse);
    BOOST_CHECK_EQUAL(deleteResponse->getStatusCode(), k204NoContent);

    // 5. Verify Deletion (GET should not return the deleted blocks)
    auto verifyReq = HttpRequest::newHttpRequest();
    verifyReq->setMethod(drogon::Get);
    verifyReq->setPath("/api/schedules");
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
    req->setPath("/api/schedules");

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
    deleteReq->setPath("/api/schedules/sched-99999999"); // Non-existent ID

    auto deleteRespPair = client->sendRequest(deleteReq);
    BOOST_REQUIRE_EQUAL(deleteRespPair.first, ReqResult::Ok);
    auto deleteResponse = deleteRespPair.second;
    BOOST_REQUIRE(deleteResponse);
    // Should be 204 No Content (idempotent)
    BOOST_CHECK_EQUAL(deleteResponse->getStatusCode(), k204NoContent);
}

BOOST_AUTO_TEST_CASE(test_delete_invalid_id) {
    auto client = HttpClient::newHttpClient("http://127.0.0.1:6969");
    auto deleteReq = HttpRequest::newHttpRequest();
    deleteReq->setMethod(drogon::Delete);
    deleteReq->setPath("/api/schedules/invalidid"); // Invalid format (no dash)

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
        job["gpu_type"] = "V100_PCIE";
        job["gpu_count"] = 1;
        job["model_size"] = 10;
        job["length"] = 60;
        auto now = std::chrono::system_clock::now();
        auto start = now + std::chrono::hours(24);
        auto end = start + std::chrono::hours(24);
        job["earliest_start"] = scheduler::utils::toIso8601(start);
        job["latest_finish"] = scheduler::utils::toIso8601(end);

        auto req = HttpRequest::newHttpJsonRequest(job);
        req->setMethod(drogon::Post);
        req->setPath("/api/schedules");

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
    listReq->setPath("/api/schedules/summary");

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
    for (const auto &obj : *listJson) {
        if (obj["schedule_id"].asString() == id1)
            found1 = true;
        if (obj["schedule_id"].asString() == id2)
            found2 = true;
    }
    BOOST_CHECK(found1);
    BOOST_CHECK(found2);

    // 3. Get Specific Job (GET /api/schedule/{id})
    auto getReq = HttpRequest::newHttpRequest();
    getReq->setMethod(drogon::Get);
    getReq->setPath("/api/schedules/" + id1);

    auto getRespPair = client->sendRequest(getReq);
    BOOST_REQUIRE_EQUAL(getRespPair.first, ReqResult::Ok);
    auto getResponse = getRespPair.second;
    BOOST_REQUIRE(getResponse);
    BOOST_CHECK_EQUAL(getResponse->getStatusCode(), k200OK);

    auto getJson = getResponse->getJsonObject();
    BOOST_REQUIRE(getJson);
    BOOST_CHECK((*getJson).isMember("schedule_id"));
    BOOST_CHECK((*getJson)["schedule_id"].asString() == id1);
    BOOST_CHECK((*getJson).isMember("scheduled_blocks"));
    BOOST_CHECK((*getJson)["scheduled_blocks"].isArray());
    BOOST_CHECK((*getJson).isMember("impact"));
}

BOOST_AUTO_TEST_CASE(test_calendar_trivial_operations) {
    drogon::sync_wait([]() -> drogon::Task<void> {
        scheduler::SchedulerOutput mockOutput;
        mockOutput.impact.carbon_intensity = 50.5;
        mockOutput.impact.total_emissions = 100.0;
        mockOutput.impact.sci = 10.0;

        std::string mockScheduleId = "999999";

        // 1. Test Insertion
        BOOST_REQUIRE_NO_THROW(co_await scheduler::calendar::addTrivial(
            mockOutput, mockScheduleId));

        // 2. Test Retrieval
        auto result = co_await scheduler::calendar::getTrivial(mockScheduleId);
        BOOST_CHECK_EQUAL(result.scheduleId, mockScheduleId);
        BOOST_CHECK_CLOSE(result.impact.carbon_intensity, 50.5, 0.01);

        // 3. Test Retrieval Failure (Should throw SchedulingException)
        auto result2 = co_await scheduler::calendar::getTrivial("999");
        BOOST_CHECK_EQUAL(result2.impact.carbon_intensity,
                          0.0); // default autoconstructed value
    }());
}

BOOST_AUTO_TEST_CASE(test_schedule_summaries_aggregation) {
    drogon::sync_wait([]() -> drogon::Task<void> {
        // scheduleSummaries executes complex SQL joins for IDs, times, and
        // loads[cite: 1]
        BOOST_CHECK_NO_THROW(co_await scheduler::calendar::scheduleSummaries());
    }());
}

BOOST_AUTO_TEST_CASE(test_get_gpu_types) {
    auto client = HttpClient::newHttpClient("http://127.0.0.1:6969");

    auto req = HttpRequest::newHttpRequest();
    req->setMethod(drogon::Get);
    req->setPath("/api/hardwareSpecs/gpus");

    auto respPair = client->sendRequest(req);
    BOOST_REQUIRE_EQUAL(respPair.first, ReqResult::Ok);
    auto response = respPair.second;

    // Verify 200 OK and JSON array structure[cite: 5]
    BOOST_CHECK_EQUAL(response->getStatusCode(), k200OK);
    auto json = response->getJsonObject();
    BOOST_REQUIRE(json && json->isArray());

    // Verify it contains at least the default hardware types[cite: 8]
    bool foundV100 = false;
    bool foundA100 = false;
    for (const auto &type : *json) {
        if (type.asString() == "V100_PCIE")
            foundV100 = true;
        if (type.asString() == "A100_SXM4")
            foundA100 = true;
    }
    BOOST_CHECK(foundV100);
    BOOST_CHECK(foundA100);
}

BOOST_AUTO_TEST_CASE(test_forecast_specific_datacenter) {
    auto client = HttpClient::newHttpClient("http://127.0.0.1:6969");

    auto req = HttpRequest::newHttpRequest();
    req->setMethod(drogon::Get);
    req->setPath("/api/forecast");
    // "datacenter" key is required by the custom fromRequest template
    req->setParameter("datacenter", "Data-Center-1");

    auto respPair = client->sendRequest(req);
    BOOST_REQUIRE_EQUAL(respPair.first, ReqResult::Ok);
    auto response = respPair.second;

    BOOST_CHECK_EQUAL(response->getStatusCode(), k200OK);
    auto json = response->getJsonObject();
    BOOST_REQUIRE(json && json->isArray());

    // Controller wraps the result in a vector
    if (json->size() > 0) {
        const auto &dc = (*json)[0];
        // The Datacenter DTO serializes 'id' as "location"[cite: 11]
        BOOST_CHECK_EQUAL(dc["location"].asString(), "Data-Center-1");
        BOOST_CHECK(dc.isMember("timeseries"));
        BOOST_CHECK(dc["timeseries"].isArray());
    }
}

BOOST_AUTO_TEST_CASE(test_forecast_any_datacenter_explicit) {
    auto client = HttpClient::newHttpClient("http://127.0.0.1:6969");

    auto req = HttpRequest::newHttpRequest();
    req->setMethod(drogon::Get);
    req->setPath("/api/forecast");
    req->setParameter("datacenter", scheduler::calendar::ANY_DATACENTER);

    auto respPair = client->sendRequest(req);
    BOOST_REQUIRE_EQUAL(respPair.first, ReqResult::Ok);

    auto response = respPair.second;
    BOOST_CHECK_EQUAL(response->getStatusCode(), k200OK);

    auto json = response->getJsonObject();
    BOOST_REQUIRE(json && json->isArray());

    // Should return all datacenters from the StatsAPIClient[cite: 3, 9]
    BOOST_CHECK(json->size() >= 1);
    if (json->size() > 0) {
        BOOST_CHECK((*json)[0].isMember("location"));
        BOOST_CHECK((*json)[0].isMember("timeseries"));
    }
}

BOOST_AUTO_TEST_CASE(test_forecast_any_datacenter_implicit) {
    auto client = HttpClient::newHttpClient("http://127.0.0.1:6969");

    auto req = HttpRequest::newHttpRequest();
    req->setMethod(drogon::Get);
    req->setPath("/api/forecast");
    // No parameters set—tests the 'defaultName' logic in fromRequest

    auto respPair = client->sendRequest(req);
    BOOST_REQUIRE_EQUAL(respPair.first, ReqResult::Ok);

    auto response = respPair.second;
    BOOST_CHECK_EQUAL(response->getStatusCode(), k200OK);

    auto json = response->getJsonObject();
    BOOST_REQUIRE(json && json->isArray());

    // Should match the 'explicit' any behavior[cite: 3]
    BOOST_CHECK(json->size() >= 1);
    if (json->size() > 0) {
        // Verify TimeSlot serialization within the timeseries[cite: 11]
        const auto &firstSeries = (*json)[0]["timeseries"];
        if (firstSeries.size() > 0) {
            BOOST_CHECK(firstSeries[0].isMember("timestamp"));
            BOOST_CHECK(firstSeries[0].isMember("carbon_intensity"));
        }
    }
}

BOOST_AUTO_TEST_SUITE_END()
