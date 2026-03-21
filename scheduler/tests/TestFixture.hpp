#pragma once

#include "exceptions/ExceptionHandler.hpp"
#include <chrono>
#include <cstdlib>
#include <drogon/HttpClient.h>
#include <drogon/drogon.h>
#include <filesystem>
#include <iostream>
#include <thread>

struct SchedulerGlobalFixture {
    SchedulerGlobalFixture() {
        // Ensure clean state
        if (std::filesystem::exists("scheduler_test.db")) {
            std::filesystem::remove("scheduler_test.db");
        }

        // Load test config
        drogon::app().loadConfigFile("config.test.json");

        // Register Exception Handler
        scheduler::exceptions::registerExceptionHandler();

        // Start the app in a thread
        t = std::jthread([]() -> void { drogon::app().run(); });

        // Wait for server to start
        using namespace std::chrono_literals;
        auto start = std::chrono::steady_clock::now();
        while (!drogon::app().isRunning()) {
            if (std::chrono::steady_clock::now() - start > 10s) {
                throw std::runtime_error("Timeout waiting for Drogon to start");
            }
            std::this_thread::sleep_for(10ms);
        }

        // Seed some active datacenters in the stats API
        seedActiveDatacenters();
    }

    ~SchedulerGlobalFixture() { drogon::app().quit(); }

    static void seedActiveDatacenters() {
        // Find stats host from env or default
        std::string statsHost = "http://127.0.0.1:5000";
        if (const char *envHost = std::getenv("STATS_API_HOST")) {
            statsHost = envHost;
        }

        auto client = drogon::HttpClient::newHttpClient(statsHost);

        // Seed first 3 datacenters as active
        for (int i = 1; i <= 14; ++i) {
            auto req = drogon::HttpRequest::newHttpRequest();
            req->setMethod(drogon::Patch);
            req->setPath("/datacenters/Data-Center-" + std::to_string(i));

            Json::Value body;
            body["active"] = true;
            req->setBody(body.toStyledString());
            req->setContentTypeCode(drogon::CT_APPLICATION_JSON);

            auto respPair = client->sendRequest(req);
            if (respPair.first != drogon::ReqResult::Ok ||
                respPair.second->getStatusCode() != drogon::k200OK) {
                std::cerr << "Failed to seed Data-Center-" << i << " as active"
                          << std::endl;
            }
        }
    }

    std::jthread t;
};
