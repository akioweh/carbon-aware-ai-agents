#include <PredictionApi.hpp>

using namespace std;

vector<PredictedDatacenterInformation>
makeUpPredictionData(DatacenterSpecificInformation datacenterSpecificInformation)
{
    long long time = 0;
    int load = 0;
    vector<PredictedDatacenterInformation> predictions;
    for (int i = 0; i < 100; i++)
    {
        predictions.push_back(PredictedDatacenterInformation(time + i, (load + i * 17) % 100,
                                                             datacenterSpecificInformation));
    }
    return predictions;
}

map<int,vector<PredictedDatacenterInformation>> getData()
{
    DatacenterSpecificInformation datacenterA =
    DatacenterSpecificInformation(100, 1, "Amsterdam", "AmsterdamDC", "Europe");

    DatacenterSpecificInformation datacenterB =
        DatacenterSpecificInformation(100, 2, "Hamburg", "HamburgDC", "Europe");

    DatacenterSpecificInformation datacenterC =
        DatacenterSpecificInformation(100, 3, "London", "LondonDC", "Europe");

    
    map<int,vector<PredictedDatacenterInformation>> data; 

    data[datacenterA.getDatacenterId()] = makeUpPredictionData(datacenterA) ;
    data[datacenterB.getDatacenterId()] = makeUpPredictionData(datacenterB) ;
    data[datacenterC.getDatacenterId()] = makeUpPredictionData(datacenterC) ;

    return data;
}