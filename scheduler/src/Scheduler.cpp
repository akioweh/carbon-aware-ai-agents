#include <JobRequest.hpp>
#include <PredictionApi.hpp>
#include <ScheduleForDatacenter.hpp>
#include <Scheduler.hpp>

using namespace std;
using namespace drogon;

auto Scheduler::getCombinedIntervals(
    map<long long, vector<PredictedDatacenterInformation>> &data)
    -> multiset<PredictedDatacenterInformation> {
    multiset<PredictedDatacenterInformation> intervals;

    for (const auto &predictions : views::values(data)) {
        for (const auto &prediction : predictions)
            intervals.insert(prediction);
    }
    return intervals;
}

auto Scheduler::schedule(PredictedDatacenterInformation &interval,
                         JobRequest &job) -> double {
    double maxWorkInInterval =
        (interval.datacenterInfo.maxLoad - interval.currentLoad) *
        interval.lengthOfInterval;

    if (maxWorkInInterval >= job.work) {
        double temp = job.work;
        job.work = 0;
        return temp / interval.lengthOfInterval; /// this is the additional load
    }
    job.work -= maxWorkInInterval;
    return maxWorkInInterval / interval.lengthOfInterval;
}

auto Scheduler::calculateSchedule(JobRequest job) -> Task<double> {

    auto data = co_await predictionApi.getData();

    auto intervals = getCombinedIntervals(data);

    double co2emissions = 0;

    fullSchedule.clear();

    while (intervals.size() > 0 && job.work > 0) {
        auto interval = *intervals.begin();
        intervals.erase(intervals.begin());

        if (interval.timestamp > job.deadline) {
            continue;
        }

        double additionalLoad = schedule(interval, job);
        co2emissions += (interval.currentGreenness * additionalLoad *
                         interval.lengthOfInterval) /
                        KWH;

        if (!fullSchedule.contains(interval.datacenterInfo.datacenterId)) {
            auto scheduleForDC = ScheduleForDatacenter(interval.datacenterInfo);
            fullSchedule.emplace(interval.datacenterInfo.datacenterId,
                                 scheduleForDC);
        }

        auto scheduledInterval =
            ScheduledInterval(interval.timestamp, job.jobId, additionalLoad,
                              additionalLoad + interval.currentLoad);

        fullSchedule[interval.datacenterInfo.datacenterId].addInterval(
            scheduledInterval);
    }
    co_return co2emissions;
}

void Scheduler::show() const {
    for (auto [datacenterId, scheduleForDC] : fullSchedule) {
        scheduleForDC.show();
    }
}
