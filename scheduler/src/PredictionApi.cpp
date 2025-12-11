#include <PredictionApi.hpp>

using namespace std;

auto makeUpPredictionData(
    const DatacenterSpecificInformation &datacenterSpecificInformation)
    -> vector<PredictedDatacenterInformation> {
    long long greennees = 90;
    int load = 13;
    vector<PredictedDatacenterInformation> predictions;
    predictions.reserve(100);
    for (int i = 0; i < 100; i++) {
        predictions.emplace_back(i * 5, 5, (load + i * 17) % 100,
                                 (greennees + i * 13) % 400,
                                 datacenterSpecificInformation);
    }
    return predictions;
}

auto PredictionApi::getData()
    -> map<int, vector<PredictedDatacenterInformation>> {
    DatacenterSpecificInformation datacenterA = DatacenterSpecificInformation(
        100, "Amsterdam", "AmsterdamDC", "Europe", 1);

    DatacenterSpecificInformation datacenterB =
        DatacenterSpecificInformation(100, "Hamburg", "HamburgDC", "Europe", 2);

    DatacenterSpecificInformation datacenterC =
        DatacenterSpecificInformation(100, "London", "LondonDC", "Europe", 3);

    map<int, vector<PredictedDatacenterInformation>> data;

    data[datacenterA.datacenterId] = makeUpPredictionData(datacenterA);
    data[datacenterB.datacenterId] = makeUpPredictionData(datacenterB);
    data[datacenterC.datacenterId] = makeUpPredictionData(datacenterC);

    return data;
}
