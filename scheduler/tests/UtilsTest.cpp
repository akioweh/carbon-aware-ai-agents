#define BOOST_TEST_MODULE UtilsTest
#include "utils/Utils.hpp"
#include <boost/test/unit_test.hpp>
#include <chrono>

using namespace scheduler::utils;

BOOST_AUTO_TEST_SUITE(TimestampParsing)

BOOST_AUTO_TEST_CASE(parse_valid_z_suffix) {
    const std::string ts = "2030-10-26T12:00:00Z";
    auto res = parseIso8601(ts);
    BOOST_CHECK(res.has_value());

    // Verify time point (rough check or exact if possible)
    // 2030-10-26 12:00:00 UTC
    // We can use toIso8601 to check round trip or construct a time point
    auto str = toIso8601(res.value());
    BOOST_CHECK_EQUAL(str, ts);
}

BOOST_AUTO_TEST_CASE(parse_valid_offset_basic) {
    // 2030-10-26T14:00:00+0200 -> 12:00:00 UTC
    const std::string ts = "2030-10-26T14:00:00+0200";
    auto res = parseIso8601(ts);
    BOOST_CHECK(res.has_value());

    auto str = toIso8601(res.value());
    // toIso8601 always outputs Z suffix (UTC)
    BOOST_CHECK_EQUAL(str, "2030-10-26T12:00:00Z");
}

BOOST_AUTO_TEST_CASE(parse_valid_offset_extended) {
    // 2030-10-26T14:00:00+02:00 -> 12:00:00 UTC
    const std::string ts = "2030-10-26T14:00:00+02:00";
    auto res = parseIso8601(ts);
    BOOST_CHECK(res.has_value());

    auto str = toIso8601(res.value());
    BOOST_CHECK_EQUAL(str, "2030-10-26T12:00:00Z");
}

BOOST_AUTO_TEST_CASE(parse_no_offset_assumes_utc) {
    // 2030-10-26T12:00:00 -> 12:00:00 UTC
    const std::string ts = "2030-10-26T12:00:00";
    auto res = parseIso8601(ts);
    BOOST_CHECK(res.has_value());

    auto str = toIso8601(res.value());
    BOOST_CHECK_EQUAL(str, "2030-10-26T12:00:00Z");
}

BOOST_AUTO_TEST_CASE(parse_decimal_seconds) {
    const std::string ts = "2030-10-26T12:00:00.1564Z";
    auto res = parseIso8601(ts);
    BOOST_CHECK(res.has_value());

    auto str = toIso8601(res.value());
    BOOST_CHECK_EQUAL(str, "2030-10-26T12:00:00Z");
}

BOOST_AUTO_TEST_CASE(parse_invalid_format) {
    const std::string ts = "invalid-date";
    auto res = parseIso8601(ts);
    BOOST_CHECK(!res.has_value());
    BOOST_CHECK_EQUAL(res.error(), "Failed to parse ISO8601 string: " + ts);
}

BOOST_AUTO_TEST_CASE(parse_invalid_date) {
    const std::string ts = "2030-13-45T12:00:00Z";
    auto res = parseIso8601(ts);
    // chrono::parse usually validates date ranges
    BOOST_CHECK(!res.has_value());
}

BOOST_AUTO_TEST_CASE(round_trip) {
    auto now = std::chrono::system_clock::now();
    auto now_sec = std::chrono::floor<std::chrono::seconds>(now);

    auto str = toIso8601(now_sec);
    auto res = parseIso8601<decltype(now_sec)>(str);

    BOOST_CHECK(res.has_value());
    BOOST_CHECK(res.value() == now_sec);
}

BOOST_AUTO_TEST_SUITE_END()
