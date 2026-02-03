#ifndef SCHEDULER
#define SCHEDULER
#pragma once

#include <JobRequest.hpp>
#include <PredictionApi.hpp>
#include <ScheduleForDatacenter.hpp>
#include <Serializable.hpp>
#include <map>
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

    PredictionApi predictionApi;

    std::map<long long, ScheduleForDatacenter>
        fullSchedule; // datacenterId -> schedule

    auto getCombinedIntervals(
        std::map<long long, std::vector<PredictedDatacenterInformation>> &data)
        -> std::multiset<PredictedDatacenterInformation>;

    auto schedule(PredictedDatacenterInformation &interval, JobRequest &job)
        -> double;

  public:
    auto calculateSchedule(JobRequest job) -> drogon::Task<SchedulingImpact>;
    void show() const;
    [[nodiscard]] auto getSchedule() const
        -> const std::map<long long, ScheduleForDatacenter> & {
        return fullSchedule;
    }
};

#endif
