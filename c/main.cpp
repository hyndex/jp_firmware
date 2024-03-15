#include "HLW8032.h"
#include <stdio.h>

int main() {
    HLW8032 hlw8032(25); // GPIO pin 25
    hlw8032.begin();

    while (true) {
        hlw8032.SerialReadLoop();
        // float voltage = hlw8032.GetVol();
        // float current = hlw8032.GetCurrent();
        // float power = hlw8032.GetActivePower();
        // printf("Voltage: %.2f V, Current: %.2f A, Power: %.2f W\n", voltage, current, power);

        // gpioDelay(1000000); // Delay for 1 second
    }

    return 0;
}
