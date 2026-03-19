#define BOOST_TEST_MODULE TimeGridderTest

#include "utils/TimeGridder.hpp"
#include <boost/test/unit_test.hpp>
#include <chrono>

using namespace scheduler::utils;
using namespace std::chrono_literals;

BOOST_AUTO_TEST_SUITE(TimeGridderTests)

BOOST_AUTO_TEST_CASE(test_default_initialization) {
    // The default constructor initializes with epoch start[cite: 1]
    TimeGridder<> default_gridder;
    TimeGridder<> explicit_gridder(std::chrono::system_clock::time_point{});

    BOOST_CHECK(default_gridder == explicit_gridder); //[cite: 1]
}

BOOST_AUTO_TEST_CASE(test_to_index_floor) {
    auto start = std::chrono::system_clock::time_point(0s);
    TimeGridder<> tg(start); // Resolution is FiveMinutes (300s)[cite: 1]

    // toIndex should round down to the nearest 5-minute bucket[cite: 1]
    BOOST_CHECK_EQUAL(tg.toIndex(start), 0);
    BOOST_CHECK_EQUAL(tg.toIndex(start + 1s), 0);
    BOOST_CHECK_EQUAL(tg.toIndex(start + 299s), 0);
    BOOST_CHECK_EQUAL(tg.toIndex(start + 300s), 1);
    BOOST_CHECK_EQUAL(tg.toIndex(start + 599s), 1);
    BOOST_CHECK_EQUAL(tg.toIndex(start + 600s), 2);
}

BOOST_AUTO_TEST_CASE(test_to_index_ceil) {
    auto start = std::chrono::system_clock::time_point(0s);
    TimeGridder<> tg(start);

    // toIndexCeil should round up to the nearest 5-minute bucket[cite: 1]
    BOOST_CHECK_EQUAL(tg.toIndexCeil(start), 0);
    BOOST_CHECK_EQUAL(tg.toIndexCeil(start + 1s), 1);
    BOOST_CHECK_EQUAL(tg.toIndexCeil(start + 299s), 1);
    BOOST_CHECK_EQUAL(tg.toIndexCeil(start + 300s), 1);
    BOOST_CHECK_EQUAL(tg.toIndexCeil(start + 301s), 2);
}

BOOST_AUTO_TEST_CASE(test_to_time_point) {
    auto start = std::chrono::system_clock::time_point(0s);
    TimeGridder<> tg(start);

    // toTimePoint should map integer indices back to 5-minute intervals[cite:
    // 1]
    BOOST_CHECK(tg.toTimePoint(0) == start);
    BOOST_CHECK(tg.toTimePoint(1) == start + 300s);
    BOOST_CHECK(tg.toTimePoint(2) == start + 600s);
}

BOOST_AUTO_TEST_CASE(test_negative_indices_and_times) {
    auto start = std::chrono::system_clock::time_point(1000s);
    TimeGridder<> tg(start);

    // Handling time points before the gridder's start time[cite: 1]
    BOOST_CHECK_EQUAL(tg.toIndex(start - 1s), -1);
    BOOST_CHECK_EQUAL(tg.toIndex(start - 300s), -1);
    BOOST_CHECK_EQUAL(tg.toIndex(start - 301s), -2);

    BOOST_CHECK_EQUAL(tg.toIndexCeil(start - 1s), 0);
    BOOST_CHECK_EQUAL(tg.toIndexCeil(start - 300s), -1);
    BOOST_CHECK_EQUAL(tg.toIndexCeil(start - 301s), -1);

    BOOST_CHECK(tg.toTimePoint(-1) == start - 300s);
}

BOOST_AUTO_TEST_CASE(test_custom_resolution) {
    auto start = std::chrono::system_clock::time_point(0s);
    // Overriding the default FiveMinutes template parameter with minutes[cite:
    // 1]
    TimeGridder<std::chrono::minutes> tg(start);

    BOOST_CHECK_EQUAL(tg.toIndex(start + 59s), 0);
    BOOST_CHECK_EQUAL(tg.toIndex(start + 60s), 1);

    BOOST_CHECK_EQUAL(tg.toIndexCeil(start + 1s), 1);
    BOOST_CHECK_EQUAL(tg.toIndexCeil(start + 60s), 1);

    BOOST_CHECK(tg.toTimePoint(5) == start + 300s);
}

BOOST_AUTO_TEST_CASE(test_equality_operator) {
    auto start1 = std::chrono::system_clock::time_point(1000s);
    auto start2 = std::chrono::system_clock::time_point(2000s);

    TimeGridder<> tg1(start1);
    TimeGridder<> tg2(start1);
    TimeGridder<> tg3(start2);

    // Gridders are equal if their start times match[cite: 1]
    BOOST_CHECK(tg1 == tg2);
    BOOST_CHECK(!(tg1 == tg3));
}

BOOST_AUTO_TEST_CASE(test_global_instance) {
    // Check the pre-instantiated global TIME_GRIDDER variable[cite: 1]
    auto epoch = std::chrono::system_clock::time_point{};
    BOOST_CHECK(scheduler::TIME_GRIDDER.toTimePoint(0) == epoch);
}

BOOST_AUTO_TEST_SUITE_END()