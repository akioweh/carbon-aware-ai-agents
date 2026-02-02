#include <JobRequest.hpp>
#include <Scheduler.hpp>
#include <StatsAPIClient.hpp>

using namespace std;
using namespace drogon;

auto Scheduler::getCombinedIntervals(const vector<Datacenter> &data)
    -> multiset<PredictedDatacenterInformation> {
    multiset<PredictedDatacenterInformation> intervals;

    for (const auto &dc : data) {
        const auto hasher = hash<string>{};
        const auto dcId = static_cast<long long>(hasher(dc.name));
        DatacenterSpecificInformation dcInfo(dc.maxLoad, dc.id, dc.name,
                                             "not defined yet", dcId);

        if (dc.timeSeries.size() < 2)
            continue;

        auto duration = dc.timeSeries[1].timestamp - dc.timeSeries[0].timestamp;
        auto lengthOfInterval =
            chrono::duration_cast<chrono::seconds>(duration);

        for (const auto &slot : dc.timeSeries) {
            intervals.emplace(slot.timestamp, lengthOfInterval,
                              slot.predictedLoad, slot.predictedGreenness,
                              dcInfo);
        }
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

    auto data = co_await statsAPIClient.getAllDatacenters();

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
