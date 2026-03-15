#ifndef HARDWARE_SPECS_CONTROLLER
#define HARDWARE_SPECS_CONTROLLER

#include <drogon/HttpController.h>
#include <drogon/HttpResponse.h>
namespace scheduler::controllers {

class HardwareSpecsController
    : public drogon::HttpController<HardwareSpecsController> {
  public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(HardwareSpecsController::getTypesOfGpus,
                  "/api/hardwareSpecs/gpus", drogon::Get);
    METHOD_LIST_END

    [[nodiscard]] auto getTypesOfGpus(drogon::HttpRequestPtr /*req*/) const
        -> drogon::Task<drogon::HttpResponsePtr>;
};
} // namespace scheduler::controllers

#endif