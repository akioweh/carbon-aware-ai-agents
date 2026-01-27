#define BOOST_TEST_MODULE StatsAPIClientTest
#include "DrogonTestUtils.hpp"
#include <Datacenter.hpp>
#include <StatsAPIClient.hpp>
#include <boost/test/included/unit_test.hpp>
#include <drogon/drogon.h>

// NOTE: All tests assume the stats API is running on localhost:5000

// =============================================================================
// Test Suite: getLocations
// =============================================================================

BOOST_AUTO_TEST_SUITE(GetLocations)

BOOST_AUTO_TEST_CASE(returns_non_empty_list) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_TEST_MESSAGE("Received " << locations.size() << " locations");
    BOOST_CHECK(!locations.empty());
}

BOOST_AUTO_TEST_CASE(locations_have_valid_id_and_name) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    for (const auto &loc : locations) {
        BOOST_TEST_MESSAGE("Location: id=" << loc.id << ", name=" << loc.name);
        BOOST_CHECK(!loc.id.empty());
        BOOST_CHECK(!loc.name.empty());
        // IDs and names should be reasonable length
        BOOST_CHECK_LE(loc.id.size(), 256);
        BOOST_CHECK_LE(loc.name.size(), 256);
    }
}

BOOST_AUTO_TEST_CASE(location_ids_are_unique) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    std::set<std::string> ids;
    for (const auto &loc : locations) {
        auto [it, inserted] = ids.insert(loc.id);
        BOOST_CHECK_MESSAGE(inserted, "Duplicate location id found: " << loc.id);
    }
}

BOOST_AUTO_TEST_SUITE_END()

// =============================================================================
// Test Suite: getLoadForecast
// =============================================================================

BOOST_AUTO_TEST_SUITE(GetLoadForecast)

BOOST_AUTO_TEST_CASE(returns_valid_forecast_for_known_location) {
    // First get a valid location
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto forecastOpt = run_coro_in_drogon<std::optional<LoadForecast>>(
        [&testLocationId]() -> drogon::Task<std::optional<LoadForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLoadForecast(testLocationId);
        });

    BOOST_CHECK(forecastOpt.has_value());
    if (forecastOpt) {
        const auto &forecast = *forecastOpt;
        BOOST_TEST_MESSAGE("Load forecast for " << testLocationId << ": " << forecast.data.size()
                                                << " data points");
        BOOST_CHECK(!forecast.locationId.empty());
        BOOST_CHECK(!forecast.data.empty());
    }
}

BOOST_AUTO_TEST_CASE(load_forecast_has_required_fields) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto forecastOpt = run_coro_in_drogon<std::optional<LoadForecast>>(
        [&testLocationId]() -> drogon::Task<std::optional<LoadForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLoadForecast(testLocationId);
        });

    BOOST_REQUIRE(forecastOpt.has_value());
    const auto &forecast = *forecastOpt;
    
    // Required fields per OpenAPI spec
    BOOST_CHECK(!forecast.locationId.empty());
    BOOST_CHECK(!forecast.metric.empty());
    BOOST_CHECK(!forecast.unit.empty());
    BOOST_CHECK(!forecast.data.empty());
}

BOOST_AUTO_TEST_CASE(load_values_are_non_negative) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto forecastOpt = run_coro_in_drogon<std::optional<LoadForecast>>(
        [&testLocationId]() -> drogon::Task<std::optional<LoadForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLoadForecast(testLocationId);
        });

    BOOST_REQUIRE(forecastOpt.has_value());
    for (const auto &point : forecastOpt->data) {
        BOOST_CHECK_GE(point.value, 0.0);
        BOOST_CHECK_GE(point.availableGpus, 0);
    }
}

BOOST_AUTO_TEST_CASE(capacity_values_are_positive) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto forecastOpt = run_coro_in_drogon<std::optional<LoadForecast>>(
        [&testLocationId]() -> drogon::Task<std::optional<LoadForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLoadForecast(testLocationId);
        });

    BOOST_REQUIRE(forecastOpt.has_value());
    BOOST_CHECK_GT(forecastOpt->capacity.maxLoad, 0.0);
    BOOST_CHECK_GT(forecastOpt->capacity.totalGpus, 0);
}

BOOST_AUTO_TEST_CASE(data_points_have_valid_timestamps) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto forecastOpt = run_coro_in_drogon<std::optional<LoadForecast>>(
        [&testLocationId]() -> drogon::Task<std::optional<LoadForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLoadForecast(testLocationId);
        });

    BOOST_REQUIRE(forecastOpt.has_value());
    const auto &data = forecastOpt->data;

    // Timestamps should be ordered
    for (size_t i = 1; i < data.size(); ++i) {
        BOOST_CHECK_LE(data[i - 1].timestamp, data[i].timestamp);
    }
}

BOOST_AUTO_TEST_CASE(returns_nullopt_for_invalid_location) {
    auto forecastOpt = run_coro_in_drogon<std::optional<LoadForecast>>(
        []() -> drogon::Task<std::optional<LoadForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLoadForecast("nonexistent_location_xyz_12345");
        });

    BOOST_CHECK(!forecastOpt.has_value());
}

BOOST_AUTO_TEST_SUITE_END()

// =============================================================================
// Test Suite: getGreennessForecast
// =============================================================================

BOOST_AUTO_TEST_SUITE(GetGreennessForecast)

BOOST_AUTO_TEST_CASE(returns_valid_forecast_for_known_location) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto forecastOpt = run_coro_in_drogon<std::optional<GreennessForecast>>(
        [&testLocationId]() -> drogon::Task<std::optional<GreennessForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getGreennessForecast(testLocationId);
        });

    BOOST_CHECK(forecastOpt.has_value());
    if (forecastOpt) {
        const auto &forecast = *forecastOpt;
        BOOST_TEST_MESSAGE("Greenness forecast for " << testLocationId << ": " << forecast.data.size()
                                                     << " data points");
        BOOST_CHECK(!forecast.locationId.empty());
        BOOST_CHECK(!forecast.data.empty());
    }
}

BOOST_AUTO_TEST_CASE(greenness_forecast_has_required_fields) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto forecastOpt = run_coro_in_drogon<std::optional<GreennessForecast>>(
        [&testLocationId]() -> drogon::Task<std::optional<GreennessForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getGreennessForecast(testLocationId);
        });

    BOOST_REQUIRE(forecastOpt.has_value());
    const auto &forecast = *forecastOpt;
    
    // Required fields per OpenAPI spec
    BOOST_CHECK(!forecast.locationId.empty());
    BOOST_CHECK(!forecast.metric.empty());
    BOOST_CHECK(!forecast.unit.empty());
    BOOST_CHECK(!forecast.data.empty());
}

BOOST_AUTO_TEST_CASE(greenness_values_are_in_valid_range) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto forecastOpt = run_coro_in_drogon<std::optional<GreennessForecast>>(
        [&testLocationId]() -> drogon::Task<std::optional<GreennessForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getGreennessForecast(testLocationId);
        });

    BOOST_REQUIRE(forecastOpt.has_value());
    for (const auto &point : forecastOpt->data) {
        // Greenness should be a percentage (0-100)
        BOOST_CHECK_GE(point.value, 0.0);
        BOOST_CHECK_LE(point.value, 100.0);
    }
}

BOOST_AUTO_TEST_CASE(data_points_have_valid_timestamps) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto forecastOpt = run_coro_in_drogon<std::optional<GreennessForecast>>(
        [&testLocationId]() -> drogon::Task<std::optional<GreennessForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getGreennessForecast(testLocationId);
        });

    BOOST_REQUIRE(forecastOpt.has_value());
    const auto &data = forecastOpt->data;

    // Timestamps should be ordered
    for (size_t i = 1; i < data.size(); ++i) {
        BOOST_CHECK_LE(data[i - 1].timestamp, data[i].timestamp);
    }
}

BOOST_AUTO_TEST_CASE(returns_nullopt_for_invalid_location) {
    auto forecastOpt = run_coro_in_drogon<std::optional<GreennessForecast>>(
        []() -> drogon::Task<std::optional<GreennessForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getGreennessForecast("nonexistent_location_xyz_12345");
        });

    BOOST_CHECK(!forecastOpt.has_value());
}

BOOST_AUTO_TEST_SUITE_END()

// =============================================================================
// Test Suite: getDatacenter
// =============================================================================

BOOST_AUTO_TEST_SUITE(GetDatacenter)

BOOST_AUTO_TEST_CASE(returns_valid_datacenter_for_known_location) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto datacenter = run_coro_in_drogon<Datacenter>(
        [&testLocationId]() -> drogon::Task<Datacenter> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getDatacenter(testLocationId);
        });

    BOOST_TEST_MESSAGE("Datacenter: " << datacenter.name << " (id: " << datacenter.id << ")");
    BOOST_CHECK(!datacenter.id.empty());
    BOOST_CHECK(!datacenter.name.empty());
}

BOOST_AUTO_TEST_CASE(datacenter_has_valid_capacity) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto datacenter = run_coro_in_drogon<Datacenter>(
        [&testLocationId]() -> drogon::Task<Datacenter> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getDatacenter(testLocationId);
        });

    BOOST_CHECK_GT(datacenter.maxLoad, 0.0);
    BOOST_CHECK_GT(datacenter.totalGpus, 0);
}

BOOST_AUTO_TEST_CASE(timeseries_has_valid_data) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto datacenter = run_coro_in_drogon<Datacenter>(
        [&testLocationId]() -> drogon::Task<Datacenter> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getDatacenter(testLocationId);
        });

    BOOST_CHECK(!datacenter.timeSeries.empty());
    BOOST_TEST_MESSAGE("Time series has " << datacenter.timeSeries.size() << " entries");

    for (const auto &slot : datacenter.timeSeries) {
        BOOST_CHECK_GE(slot.predictedLoad, 0.0);
        BOOST_CHECK_GE(slot.predictedGreenness, 0.0);
        BOOST_CHECK_LE(slot.predictedGreenness, 100.0);
        BOOST_CHECK_GE(slot.availableGpus, 0);
    }
}

BOOST_AUTO_TEST_CASE(timeseries_is_sorted_by_timestamp) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto datacenter = run_coro_in_drogon<Datacenter>(
        [&testLocationId]() -> drogon::Task<Datacenter> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getDatacenter(testLocationId);
        });

    const auto &ts = datacenter.timeSeries;
    for (size_t i = 1; i < ts.size(); ++i) {
        BOOST_CHECK_LE(ts[i - 1].timestamp, ts[i].timestamp);
    }
}

BOOST_AUTO_TEST_CASE(returns_empty_datacenter_for_invalid_location) {
    auto datacenter = run_coro_in_drogon<Datacenter>(
        []() -> drogon::Task<Datacenter> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getDatacenter("nonexistent_location_xyz_12345");
        });

    // Should return empty datacenter when location not found
    BOOST_CHECK(datacenter.id.empty());
    BOOST_CHECK(datacenter.timeSeries.empty());
}

BOOST_AUTO_TEST_SUITE_END()

// =============================================================================
// Test Suite: getAllDatacenters
// =============================================================================

BOOST_AUTO_TEST_SUITE(GetAllDatacenters)

BOOST_AUTO_TEST_CASE(returns_non_empty_list) {
    auto datacenters = run_coro_in_drogon<std::vector<Datacenter>>(
        []() -> drogon::Task<std::vector<Datacenter>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getAllDatacenters();
        });

    BOOST_TEST_MESSAGE("Received " << datacenters.size() << " datacenters");
    BOOST_CHECK(!datacenters.empty());
}

BOOST_AUTO_TEST_CASE(all_datacenters_have_valid_ids) {
    auto datacenters = run_coro_in_drogon<std::vector<Datacenter>>(
        []() -> drogon::Task<std::vector<Datacenter>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getAllDatacenters();
        });

    for (const auto &dc : datacenters) {
        BOOST_TEST_MESSAGE("Checking datacenter: " << dc.name);
        BOOST_CHECK(!dc.id.empty());
        BOOST_CHECK(!dc.name.empty());
    }
}

BOOST_AUTO_TEST_CASE(all_datacenters_have_valid_capacity) {
    auto datacenters = run_coro_in_drogon<std::vector<Datacenter>>(
        []() -> drogon::Task<std::vector<Datacenter>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getAllDatacenters();
        });

    for (const auto &dc : datacenters) {
        BOOST_CHECK_GT(dc.maxLoad, 0.0);
        BOOST_CHECK_GT(dc.totalGpus, 0);
    }
}

BOOST_AUTO_TEST_CASE(all_datacenters_have_timeseries) {
    auto datacenters = run_coro_in_drogon<std::vector<Datacenter>>(
        []() -> drogon::Task<std::vector<Datacenter>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getAllDatacenters();
        });

    for (const auto &dc : datacenters) {
        BOOST_CHECK(!dc.timeSeries.empty());
    }
}

BOOST_AUTO_TEST_CASE(datacenter_count_matches_locations_count) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    auto datacenters = run_coro_in_drogon<std::vector<Datacenter>>(
        []() -> drogon::Task<std::vector<Datacenter>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getAllDatacenters();
        });

    BOOST_CHECK_EQUAL(locations.size(), datacenters.size());
}

BOOST_AUTO_TEST_SUITE_END()

// =============================================================================
// Test Suite: Custom host configuration
// =============================================================================

BOOST_AUTO_TEST_SUITE(CustomHostConfiguration)

BOOST_AUTO_TEST_CASE(accepts_custom_host) {
    // This test verifies that we can construct clients with custom hosts
    // Without actually making requests to invalid hosts
    auto client = std::make_shared<StatsAPIClient>("http://custom-host:8080");
    BOOST_CHECK(client != nullptr);
}

BOOST_AUTO_TEST_CASE(default_host_works) {
    // Verify default host (localhost:5000) works
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    // If we get here without exception, default host is working
    BOOST_CHECK(true);
}

BOOST_AUTO_TEST_SUITE_END()

// =============================================================================
// Test Suite: Data consistency
// =============================================================================

BOOST_AUTO_TEST_SUITE(DataConsistency)

BOOST_AUTO_TEST_CASE(load_and_greenness_forecasts_have_matching_timestamps) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto loadForecastOpt = run_coro_in_drogon<std::optional<LoadForecast>>(
        [&testLocationId]() -> drogon::Task<std::optional<LoadForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLoadForecast(testLocationId);
        });

    auto greennessForecastOpt = run_coro_in_drogon<std::optional<GreennessForecast>>(
        [&testLocationId]() -> drogon::Task<std::optional<GreennessForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getGreennessForecast(testLocationId);
        });

    BOOST_REQUIRE(loadForecastOpt.has_value());
    BOOST_REQUIRE(greennessForecastOpt.has_value());

    // Build a set of greenness timestamps
    std::set<std::chrono::system_clock::time_point> greennessTimestamps;
    for (const auto &point : greennessForecastOpt->data) {
        greennessTimestamps.insert(point.timestamp);
    }

    // Check that there's overlap between load and greenness timestamps
    size_t matchingTimestamps = 0;
    for (const auto &point : loadForecastOpt->data) {
        if (greennessTimestamps.contains(point.timestamp)) {
            ++matchingTimestamps;
        }
    }

    BOOST_TEST_MESSAGE("Matching timestamps: " << matchingTimestamps << " out of "
                                               << loadForecastOpt->data.size() << " load points");
    BOOST_CHECK_GT(matchingTimestamps, 0);
}

BOOST_AUTO_TEST_CASE(datacenter_timeseries_matches_combined_forecasts) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocationId = locations[0].id;

    auto datacenter = run_coro_in_drogon<Datacenter>(
        [&testLocationId]() -> drogon::Task<Datacenter> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getDatacenter(testLocationId);
        });

    auto loadForecastOpt = run_coro_in_drogon<std::optional<LoadForecast>>(
        [&testLocationId]() -> drogon::Task<std::optional<LoadForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLoadForecast(testLocationId);
        });

    BOOST_REQUIRE(loadForecastOpt.has_value());

    // The datacenter timeSeries should not exceed the load forecast data points
    // (it's the intersection of load and greenness)
    BOOST_CHECK_LE(datacenter.timeSeries.size(), loadForecastOpt->data.size());
    
    // Verify that capacity from forecast matches datacenter
    BOOST_CHECK_EQUAL(datacenter.maxLoad, loadForecastOpt->capacity.maxLoad);
    BOOST_CHECK_EQUAL(datacenter.totalGpus, loadForecastOpt->capacity.totalGpus);
}

BOOST_AUTO_TEST_CASE(location_id_consistency_across_endpoints) {
    auto locations =
        run_coro_in_drogon<std::vector<Location>>([]() -> drogon::Task<std::vector<Location>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLocations();
        });

    BOOST_REQUIRE(!locations.empty());
    const auto &testLocation = locations[0];

    auto loadForecastOpt = run_coro_in_drogon<std::optional<LoadForecast>>(
        [&testLocation]() -> drogon::Task<std::optional<LoadForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getLoadForecast(testLocation.id);
        });

    auto greennessForecastOpt = run_coro_in_drogon<std::optional<GreennessForecast>>(
        [&testLocation]() -> drogon::Task<std::optional<GreennessForecast>> {
            auto client = std::make_shared<StatsAPIClient>();
            co_return co_await client->getGreennessForecast(testLocation.id);
        });

    BOOST_REQUIRE(loadForecastOpt.has_value());
    BOOST_REQUIRE(greennessForecastOpt.has_value());

    // location_id in responses should match the requested location id
    BOOST_CHECK_EQUAL(loadForecastOpt->locationId, testLocation.id);
    BOOST_CHECK_EQUAL(greennessForecastOpt->locationId, testLocation.id);
}

BOOST_AUTO_TEST_SUITE_END()
