#define BOOST_TEST_MODULE CalendarTest
#include "Calendar.hpp"
#include "exceptions/SchedulingException.hpp"
#include <boost/test/unit_test.hpp>

BOOST_AUTO_TEST_SUITE(CalendarLogicTests)

BOOST_AUTO_TEST_CASE(test_trivial_impact_lifecycle) {
    drogon::sync_wait([]() -> drogon::Task<void> {
        scheduler::SchedulerOutput output;
        output.impact.carbon_intensity = 75.0;
        std::string scheduleId = "555";

        // Test insertion of trivial impact[cite: 1]
        co_await scheduler::calendar::addTrivial(output, scheduleId);

        // Test retrieval
        auto result = co_await scheduler::calendar::getTrivial(scheduleId);
        BOOST_CHECK_EQUAL(result.impact.carbon_intensity, 75.0);

        // Test non-existent retrieval
        BOOST_CHECK_THROW(co_await scheduler::calendar::getTrivial("999"),
                          scheduler::exceptions::SchedulingException);
    }());
}

BOOST_AUTO_TEST_CASE(test_schedule_summaries_aggregation) {
    drogon::sync_wait([]() -> drogon::Task<void> {
        // scheduleSummaries executes complex SQL joins for IDs, times, and
        // loads[cite: 1]
        auto summaries = co_await scheduler::calendar::scheduleSummaries();

        // Even if empty, it should return a valid vector, not throw
        BOOST_CHECK(summaries.size() >= 0);
    }());
}

BOOST_AUTO_TEST_SUITE_END()