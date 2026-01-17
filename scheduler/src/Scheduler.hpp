#ifndef SCHEDULER
#define SCHEDULER
#include "ScheduledInterval.hpp"
#pragma once

#include <JobRequest.hpp>
#include <PredictionApi.hpp>
#include <Serializable.hpp>
#include <map>
#include <set>

struct SchedulingImpact : public Serializable {
    double carbon_intensity;
    double total_emissions;
    double sci;

    SchedulingImpact(double carbon_intensity, double total_emissions,
                     double sci)
        : carbon_intensity(carbon_intensity), total_emissions(total_emissions),
          sci(sci) {}

    [[nodiscard]] auto toJson() const -> Json::Value override {
        auto json = Json::Value{};
        json["carbon_intensity"] = carbon_intensity;
        json["total_emissions"] = total_emissions;
        json["sci"] = sci;
        return json;
    }
};

class Scheduler {
  private:
    static const unsigned int KWH = 1000 * 60 * 60;

    PredictionApi predictionApi;

    std::set<ScheduledInterval> fullSchedule;

    auto getCombinedIntervals(
        std::map<long long, std::vector<PredictedDatacenterInformation>> &data)
        -> std::multiset<PredictedDatacenterInformation>;

    auto schedule(PredictedDatacenterInformation &interval, JobRequest &job)
        -> double;

  public:
    auto calculateSchedule(JobRequest job) -> drogon::Task<SchedulingImpact>;
    void show() const;
    [[nodiscard]] auto getSchedule() const
        -> const std::set<ScheduledInterval> & {
        return fullSchedule;
    }
};

#endif
