#define BOOST_TEST_MODULE NewAlgoTest
#include "../src/TimeWindowScheduler.hpp"
#include <boost/test/included/unit_test.hpp>
#include <iostream>

using namespace scheduler;

BOOST_AUTO_TEST_CASE(BasicFunctionality) {
    TimeWindowScheduler scheduler(1.0); // work_unit = 1.0

    // Block 1: Cap 100, Green 1.0
    BlockData b1{100.0, 0.0, 1.0, "loc1", {}};
    scheduler.addBlock(b1);

    // Query 1 block, work 10
    // Should use b1. Cost = 10 / 100 = 0.1
    double cost = scheduler.query(0, 0, 10.0);
    BOOST_CHECK_CLOSE(cost, 0.1, 0.001);

    // Block 2: Cap 100, Green 0.5 (Twice as expensive)
    BlockData b2{100.0, 0.0, 0.5, "loc2", {}};
    scheduler.addBlock(b2);

    // Query 2 blocks [0, 1], work 10
    // b1 cost rate = 1/100 = 0.01
    // b2 cost rate = 1/50 = 0.02
    // Should prefer b1.
    cost = scheduler.query(0, 1, 10.0);
    BOOST_CHECK_CLOSE(cost, 0.1, 0.001);

    // Query 2 blocks, work 110
    // b1 max = 100. Cost = 1.0
    // remaining 10 to b2. Cost = 10 / 50 = 0.2
    // Total = 1.2
    // BUT penalty?
    // Transition active->active = no penalty.
    cost = scheduler.query(0, 1, 110.0);
    BOOST_CHECK_CLOSE(cost, 1.2, 0.001);
}

BOOST_AUTO_TEST_CASE(PenaltyLogic) {
    TimeWindowScheduler scheduler(1.0);

    // b1: Cap 10, Green 1.0
    scheduler.addBlock({10.0, 0.0, 1.0, "loc1", {}});
    // b2: Cap 100, Green 1.0
    scheduler.addBlock({100.0, 0.0, 1.0, "loc2", {}});

    // Work 5.
    // Option 1: All in b1 (expensive). Cost 5/10 = 0.5.
    // Option 2: All in b2 (cheap but penalty). Cost (5+20)/100 = 0.25.
    // Option 3: Split. Activate b1 with 1 unit to bridge, put rest in b2.
    //           b1(1) -> 0.1. b2(4) -> 0.04 (no penalty). Total 0.14.
    // The algorithm finds Option 3.
    double cost = scheduler.query(0, 1, 5.0);
    BOOST_CHECK_CLOSE(cost, 0.14, 0.001);
}

BOOST_AUTO_TEST_CASE(RollingWindow) {
    TimeWindowScheduler scheduler(1.0);

    for (int i = 0; i < 5; ++i) {
        scheduler.addBlock({100.0, 0.0, 1.0, "loc1", {}});
    }

    // Head = 0, Tail = 5
    // Query [0, 4]
    double cost = scheduler.query(0, 4, 10.0);
    BOOST_CHECK_GT(cost, 0.0);

    // Pop 2 blocks
    scheduler.popBlock(); // Head = 1
    scheduler.popBlock(); // Head = 2

    // Now window is [2, 4] (3 blocks)
    // Query offset 0 (logical 2) to offset 2 (logical 4)
    cost = scheduler.query(0, 2, 10.0);
    BOOST_CHECK_GT(cost, 0.0);
}

BOOST_AUTO_TEST_CASE(Reservation) {
    TimeWindowScheduler scheduler(1.0);

    // Block 1: Cap 10, Green 1.0. Rate 0.1
    scheduler.addBlock({10.0, 0.0, 1.0, "loc1", {}});

    // Reserve 5 units. Should cost 0.5.
    // And update the block load to 5.
    auto blocks = scheduler.reserve(0, 0, 5.0);
    BOOST_CHECK(!blocks.empty());

    // Query again for 5 units.
    // Block 1 now has load 5.
    // Cost = (5+5)/10 - 5/10 = 1.0 - 0.5 = 0.5.
    // Wait, cost function is linear?
    // Cost(w) = (L+w)/C - L/C = w/C.
    // It is linear. So marginal cost is constant until full.
    // So cost should still be 0.5.
    double cost = scheduler.query(0, 0, 5.0);
    BOOST_CHECK_CLOSE(cost, 0.5, 0.001);

    // Reserve another 5.
    blocks = scheduler.reserve(0, 0, 5.0);
    BOOST_CHECK(!blocks.empty());

    // Now block is full (10/10).
    // Next reservation should fail or be infinite cost.
    double cost_full = scheduler.query(0, 0, 1.0);
    BOOST_CHECK(cost_full < 0); // returns -1 if infeasible (infinite cost)

    blocks = scheduler.reserve(0, 0, 1.0);
    BOOST_CHECK(blocks.empty());
}
