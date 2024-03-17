#include "HLW8032.h"
#include <pigpio.h>
#include <iostream>

void readMeter(HLW8032& meter) {
    meter.begin();
    while (true) {
        meter.SerialReadLoop();
        // std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
}

int main() {
    if (gpioInitialise() < 0) {
        std::cerr << "Failed to initialize pigpio\n";
        return -1;
    }
    HLW8032 meter2(12);

    readMeter(meter2);

    gpioTerminate();
    return 0;
}
