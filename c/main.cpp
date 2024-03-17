#include "HLW8032.h"
#include <pigpio.h>
#include <iostream>
#include <thread>

void readMeter(HLW8032& meter) {
    meter.begin();
    while (true) {
        meter.SerialReadLoop();
        std::this_thread::sleep_for(std::chrono::milliseconds(10)); // Reduced sleep duration
    }
}

int main() {
    if (gpioInitialise() < 0) {
        std::cerr << "Failed to initialize pigpio\n";
        return -1;
    }

    HLW8032 meter1(25); // GPIO pin 25 for meter 1
    HLW8032 meter2(12); // GPIO pin 12 for meter 2
    HLW8032 meter3(21); // GPIO pin 21 for meter 3

    std::thread thread1(readMeter, std::ref(meter1));
    std::thread thread2(readMeter, std::ref(meter2));
    std::thread thread3(readMeter, std::ref(meter3));

    thread1.join();
    thread2.join();
    thread3.join();

    gpioTerminate();
    return 0;
}
