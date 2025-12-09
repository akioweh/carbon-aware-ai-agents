#ifndef PREDICTION_API
#define PREDICTION_API

#include<map>
#include<vector>
#include<PredictedDatacenterInformation.hpp>

class PredictionApi
{
    public:
    std::map<int,std::vector<PredictedDatacenterInformation>> getData();
};

#endif