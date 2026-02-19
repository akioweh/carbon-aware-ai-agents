#define BOOST_TEST_MODULE ControllerDeserializationTest
#include "structs/JobRequest.hpp"
#include "structs/ScheduleIdentifierParam.hpp"
#include "structs/TimeIntervalParams.hpp"
#include <boost/test/included/unit_test.hpp>
#include <drogon/HttpRequest.h>
#include <json/json.h>

using namespace scheduler;
using namespace scheduler::exceptions;

BOOST_AUTO_TEST_SUITE(JobRequestDeserialization)

BOOST_AUTO_TEST_CASE(valid_request) {
    Json::Value json;
    json["job_type"] = "batch";
    json["workload_amount"] = 10.5;
    json["earliest_start"] = "2023-10-26T10:00:00Z";
    json["latest_finish"] = "2023-10-26T12:00:00Z";

    auto req = drogon::HttpRequest::newHttpJsonRequest(json);
    auto jobRequest = drogon::fromRequest<JobRequest>(*req);

    BOOST_CHECK_EQUAL(jobRequest.job_type, "batch");
    BOOST_CHECK_CLOSE(jobRequest.workload_amount, 10.5, 1e-9);
    // Check if time points are valid (non-zero)
    BOOST_CHECK(jobRequest.earliest_start.time_since_epoch().count() > 0);
    BOOST_CHECK(jobRequest.latest_finish.time_since_epoch().count() > 0);
    BOOST_CHECK(jobRequest.latest_finish > jobRequest.earliest_start);
}

BOOST_AUTO_TEST_CASE(valid_request_integer_workload) {
    // workload_amount can be integer in JSON, should parse to double
    Json::Value json;
    json["job_type"] = "batch";
    json["workload_amount"] = 10;
    json["earliest_start"] = "2023-10-26T10:00:00Z";
    json["latest_finish"] = "2023-10-26T12:00:00Z";

    auto req = drogon::HttpRequest::newHttpJsonRequest(json);
    auto jobRequest = drogon::fromRequest<JobRequest>(*req);

    BOOST_CHECK_CLOSE(jobRequest.workload_amount, 10.0, 1e-9);
}

BOOST_AUTO_TEST_CASE(missing_body) {
    auto req = drogon::HttpRequest::newHttpRequest(); // No JSON body
    BOOST_CHECK_THROW(drogon::fromRequest<JobRequest>(*req),
                      ValidationException);
}

BOOST_AUTO_TEST_CASE(missing_fields) {
    Json::Value json;
    json["job_type"] = "batch";
    // Missing others

    auto req = drogon::HttpRequest::newHttpJsonRequest(json);
    // Check specific error message if possible, or just the exception type
    BOOST_CHECK_THROW(drogon::fromRequest<JobRequest>(*req),
                      ValidationException);
}

BOOST_AUTO_TEST_CASE(null_fields) {
    Json::Value json;
    json["job_type"] = "batch";
    json["workload_amount"] = Json::nullValue; // Null
    json["earliest_start"] = "2023-10-26T10:00:00Z";
    json["latest_finish"] = "2023-10-26T12:00:00Z";

    auto req = drogon::HttpRequest::newHttpJsonRequest(json);
    BOOST_CHECK_THROW(drogon::fromRequest<JobRequest>(*req),
                      ValidationException);
}

BOOST_AUTO_TEST_CASE(invalid_types_string_for_number) {
    Json::Value json;
    json["job_type"] = "batch";
    json["workload_amount"] = "10.5"; // String instead of number
    json["earliest_start"] = "2023-10-26T10:00:00Z";
    json["latest_finish"] = "2023-10-26T12:00:00Z";

    auto req = drogon::HttpRequest::newHttpJsonRequest(json);
    BOOST_CHECK_THROW(drogon::fromRequest<JobRequest>(*req),
                      ValidationException);
}

BOOST_AUTO_TEST_CASE(invalid_types_number_for_string) {
    Json::Value json;
    json["job_type"] = 123; // Number instead of string
    json["workload_amount"] = 10.5;
    json["earliest_start"] = "2023-10-26T10:00:00Z";
    json["latest_finish"] = "2023-10-26T12:00:00Z";

    auto req = drogon::HttpRequest::newHttpJsonRequest(json);
    BOOST_CHECK_THROW(drogon::fromRequest<JobRequest>(*req),
                      ValidationException);
}

BOOST_AUTO_TEST_CASE(invalid_time_format) {
    Json::Value json;
    json["job_type"] = "batch";
    json["workload_amount"] = 10.5;
    json["earliest_start"] = "invalid-date";
    json["latest_finish"] = "2023-10-26T12:00:00Z";

    auto req = drogon::HttpRequest::newHttpJsonRequest(json);
    BOOST_CHECK_THROW(drogon::fromRequest<JobRequest>(*req),
                      ValidationException);
}

BOOST_AUTO_TEST_CASE(start_after_finish) {
    Json::Value json;
    json["job_type"] = "batch";
    json["workload_amount"] = 10.5;
    json["earliest_start"] = "2023-10-26T13:00:00Z"; // After finish
    json["latest_finish"] = "2023-10-26T12:00:00Z";

    auto req = drogon::HttpRequest::newHttpJsonRequest(json);
    BOOST_CHECK_THROW(drogon::fromRequest<JobRequest>(*req),
                      ValidationException);
}

BOOST_AUTO_TEST_CASE(negative_workload) {
    Json::Value json;
    json["job_type"] = "batch";
    json["workload_amount"] = -5.0;
    json["earliest_start"] = "2023-10-26T10:00:00Z";
    json["latest_finish"] = "2023-10-26T12:00:00Z";

    auto req = drogon::HttpRequest::newHttpJsonRequest(json);
    BOOST_CHECK_THROW(drogon::fromRequest<JobRequest>(*req),
                      ValidationException);
}

BOOST_AUTO_TEST_SUITE_END()

BOOST_AUTO_TEST_SUITE(TimeIntervalParamsDeserialization)

BOOST_AUTO_TEST_CASE(valid_params) {
    auto req = drogon::HttpRequest::newHttpRequest();
    req->setParameter("start_time", "2023-10-26T10:00:00Z");
    req->setParameter("end_time", "2023-10-26T12:00:00Z");

    auto params = drogon::fromRequest<TimeIntervalParams>(*req);
    BOOST_CHECK(params.start.has_value());
    BOOST_CHECK(params.end.has_value());
    BOOST_CHECK(params.end.value() > params.start.value());
}

BOOST_AUTO_TEST_CASE(optional_params) {
    auto req = drogon::HttpRequest::newHttpRequest();
    // No params

    auto params = drogon::fromRequest<TimeIntervalParams>(*req);
    BOOST_CHECK(!params.start.has_value());
    BOOST_CHECK(!params.end.has_value());
}

BOOST_AUTO_TEST_CASE(only_start) {
    auto req = drogon::HttpRequest::newHttpRequest();
    req->setParameter("start_time", "2023-10-26T10:00:00Z");

    auto params = drogon::fromRequest<TimeIntervalParams>(*req);
    BOOST_CHECK(params.start.has_value());
    BOOST_CHECK(!params.end.has_value());
}

BOOST_AUTO_TEST_CASE(invalid_time_format) {
    auto req = drogon::HttpRequest::newHttpRequest();
    req->setParameter("start_time", "invalid");

    BOOST_CHECK_THROW(drogon::fromRequest<TimeIntervalParams>(*req),
                      ValidationException);
}

BOOST_AUTO_TEST_CASE(start_after_end) {
    auto req = drogon::HttpRequest::newHttpRequest();
    req->setParameter("start_time", "2023-10-26T13:00:00Z");
    req->setParameter("end_time", "2023-10-26T12:00:00Z");

    BOOST_CHECK_THROW(drogon::fromRequest<TimeIntervalParams>(*req),
                      ValidationException);
}

BOOST_AUTO_TEST_SUITE_END()

BOOST_AUTO_TEST_SUITE(JobIdentifierParamValidation)

BOOST_AUTO_TEST_CASE(valid_id) {
    ScheduleIdentifierParam param("12345");
    BOOST_CHECK_EQUAL(param.getScheduleId(), "12345");
}

BOOST_AUTO_TEST_CASE(empty_id_throws) {
    BOOST_CHECK_THROW(ScheduleIdentifierParam(""), ValidationException);
}

BOOST_AUTO_TEST_SUITE_END()
