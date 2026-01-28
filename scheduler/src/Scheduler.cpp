#include <JobRequest.hpp>
#include <PredictionApi.hpp>
#include <Scheduler.hpp>

using namespace std;
using namespace drogon;

auto Scheduler::getCombinedIntervals(
    std::map<long long, std::vector<PredictedDatacenterInformation>> &data)
    -> std::multiset<PredictedDatacenterInformation> {
    multiset<PredictedDatacenterInformation> intervals;

    for (const auto &predictions : views::values(data)) {
        for (const auto &prediction : predictions)
            intervals.insert(prediction);
    }
    return intervals;
}

auto Scheduler::schedule(PredictedDatacenterInformation &interval,
                         JobRequest &job) -> double {

    auto durationSeconds =
        static_cast<double>(interval.lengthOfInterval.count());

    double maxWorkInInterval =
        (interval.datacenterInfo.maxLoad - interval.currentLoad) *
        durationSeconds;

    if (maxWorkInInterval >= job.workload_amount) {
        double temp = job.workload_amount;
        job.workload_amount = 0;
        return temp / durationSeconds; /// this is the additional load
    }
    job.workload_amount -= maxWorkInInterval;
    return maxWorkInInterval / durationSeconds;
}

auto Scheduler::calculateSchedule(JobRequest job) -> Task<SchedulingImpact> {

    auto data = co_await predictionApi.getData();

    auto intervals = getCombinedIntervals(data);

    double co2emissions = 0;
    double totalEnergy = 0;

    fullSchedule.clear();

    while (intervals.size() > 0 && job.workload_amount > 0) {
        auto interval = *intervals.begin();
        intervals.erase(intervals.begin());

        if (interval.timestamp > job.latest_finish ||
            interval.timestamp < job.earliest_start) {
            continue;
        }

        double additionalLoad = schedule(interval, job);
        auto durationSeconds =
            static_cast<double>(interval.lengthOfInterval.count());
        double energy = additionalLoad * durationSeconds;
        totalEnergy += energy;

        co2emissions += (interval.currentGreenness * energy) / KWH;

        fullSchedule.emplace(interval.timestamp, job.jobId,
                             interval.datacenterInfo.name, additionalLoad,
                             additionalLoad + interval.currentLoad);
    }

    const auto carbon_intensity =
        (totalEnergy > 0) ? (co2emissions * KWH / totalEnergy) : 0;
    const auto impact = SchedulingImpact{
        .carbon_intensity = carbon_intensity,
        .total_emissions = co2emissions,
        .sci = carbon_intensity, // for now they're the same
    };

    co_return impact;
}

void Scheduler::show() const {
    for (const auto &interval : fullSchedule) {
        interval.show();
    }
}
