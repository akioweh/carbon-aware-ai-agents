#ifndef PREDICTED_DATACENTER_INFORMATION
#define PREDICTED_DATACENTER_INFORMATION
#pragma once

#include <DatacenterSpecificInformation.hpp>
#include <chrono>
#include <utility>

struct PredictedDatacenterInformation {
    std::chrono::system_clock::time_point timestamp;
    std::chrono::seconds lengthOfInterval;
    double currentLoad;
    double currentGreenness;
    DatacenterSpecificInformation datacenterInfo;

    PredictedDatacenterInformation(
        std::chrono::system_clock::time_point timestamp,
        std::chrono::seconds lengthOfInterval, double currentLoad,
        double currentGreenness, DatacenterSpecificInformation datacenterInfo)
        : timestamp(timestamp), lengthOfInterval(lengthOfInterval),
          currentLoad(currentLoad), currentGreenness(currentGreenness),
          datacenterInfo(std::move(datacenterInfo)) {};

    auto operator<(const PredictedDatacenterInformation &other) const -> bool {
        // Sort by greenness first (greedy approach)
        // If greenness is equal, maybe sort by load?
        return currentGreenness < other.currentGreenness;
    }
};

#endif
