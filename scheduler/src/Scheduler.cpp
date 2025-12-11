#include <JobRequest.hpp>
#include <PredictionApi.hpp>
#include <ScheduleForDatacenter.hpp>
#include <Scheduler.hpp>
#include <iostream>

using namespace std;

auto Scheduler::getCombinedIntervals(
    map<int, vector<PredictedDatacenterInformation>> &data)
    -> multiset<PredictedDatacenterInformation> {
    multiset<PredictedDatacenterInformation> intervals;

    for (const auto &[datacenterId, predictions] : data) {
        for (const auto &prediction : predictions) {
            intervals.insert(prediction);
        }
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

auto Scheduler::calculateSchedule(JobRequest job) -> double {
    auto data = predictionApi.getData();

    auto intervals = getCombinedIntervals(data);

    double co2emissions = 0;

    fullSchedule = map<int, ScheduleForDatacenter>();

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

        if (fullSchedule.count(interval.datacenterInfo.datacenterId) == 0) {
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

    return co2emissions;
}

void Scheduler::show() const {
    for (auto [datacenterId, scheduleForDC] : fullSchedule) {
        scheduleForDC.show();
    }
}

int main() {
    JobRequest job = JobRequest(127, "NORMAL", 1500.0, 1);
    Scheduler scheduler;
    cout << scheduler.calculateSchedule(job) << '\n';
    scheduler.show();
}
