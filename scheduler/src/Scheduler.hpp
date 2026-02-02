#ifndef SCHEDULER
#define SCHEDULER
#include "ScheduledInterval.hpp"
#pragma once

#include <Datacenter.hpp>
#include <JobRequest.hpp>
#include <PredictedDatacenterInformation.hpp>
#include <Serializable.hpp>
#include <StatsAPIClient.hpp>
#include <set>

struct SchedulingImpact {
    double carbon_intensity{};
    double total_emissions{};
    double sci{};
};

inline auto f_toJson(const SchedulingImpact &obj) -> Json::Value {
    auto res = Json::Value{};
    res["carbon_intensity"] = obj.carbon_intensity;
    res["total_emissions"] = obj.total_emissions;
    res["sci"] = obj.sci;
    return res;
}

static_assert(Serializable<SchedulingImpact>);

class Scheduler {
  private:
    static const unsigned int KWH = 1000 * 60 * 60;

    StatsAPIClient statsAPIClient;

    std::set<ScheduledInterval> fullSchedule;

    auto getCombinedIntervals(const std::vector<Datacenter> &data)
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
