#include "HLW8032.h"
#include <cstdio>  // For printf

int main() {
    wiringPiSetup(); // Initialize wiringPi
    HLW8032 hlw8032(25); // Create an instance of HLW8032 with RX pin 25
    hlw8032.begin("/dev/ttyS0"); // Begin serial communication on serial port ttyS0

    while (true) {
        hlw8032.SerialReadLoop(); // Read and process data from HLW8032
        float voltage = hlw8032.GetVol();
        float current = hlw8032.GetCurrent();
        float power = hlw8032.GetActivePower();

        // Print the readings
        printf("Voltage: %.2f V, Current: %.2f A, Power: %.2f W\n", voltage, current, power);

        delay(1000); // Wait for 1 second before reading again
    }

    return 0;
}
