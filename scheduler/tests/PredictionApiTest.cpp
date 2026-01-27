#define BOOST_TEST_MODULE PredictionApiTest
#include "DrogonTestUtils.hpp"
#include <PredictionApi.hpp>
#include <boost/test/included/unit_test.hpp>
#include <drogon/drogon.h>

BOOST_AUTO_TEST_CASE(test_get_data) {
    // assumes stats api running on localhost:5000.

    try {
        auto data = run_coro_in_drogon<
            std::map<long long, std::vector<PredictedDatacenterInformation>>>(
            []() -> drogon::Task<std::map<
                     long long, std::vector<PredictedDatacenterInformation>>> {
                // Keep api alive while the coroutine runs
                auto api = std::make_shared<PredictionApi>();
                co_return co_await api->getData();
            });

        BOOST_TEST_MESSAGE("Received data size: " << data.size());

        BOOST_CHECK(!data.empty());

        for (const auto &[id, infoVec] : data) {
            BOOST_TEST_MESSAGE("Checking DC ID: " << id << " with "
                                                  << infoVec.size()
                                                  << " entries");
            BOOST_CHECK(!infoVec.empty());
            if (!infoVec.empty()) {
                const auto &firstItem = infoVec[0];
                BOOST_CHECK_GE(firstItem.currentLoad, 0.0);
                BOOST_CHECK_GE(firstItem.currentGreenness, 0.0);
            }
        }
    } catch (const std::exception &e) {
        BOOST_FAIL(std::string("Test failed with exception: ") + e.what());
    }
}
