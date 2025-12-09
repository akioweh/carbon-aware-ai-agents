#include <PredictionApi.hpp>

using namespace std;

vector<PredictedDatacenterInformation>
makeUpPredictionData(DatacenterSpecificInformation datacenterSpecificInformation)
{
    long long time = 13;
    long long greennees = 90;
    int load = 0;
    vector<PredictedDatacenterInformation> predictions;
    for (int i = 0; i < 100; i++)
    {
        predictions.push_back(PredictedDatacenterInformation(time + i, (load + i * 17) % 100,
                                                             (greennees + i * 13) % 400,
                                                             datacenterSpecificInformation));
    }
    return predictions;
}

map<int, vector<PredictedDatacenterInformation>> getData()
{
    DatacenterSpecificInformation datacenterA =
        DatacenterSpecificInformation(100, "Amsterdam", "AmsterdamDC", "Europe", 1);

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