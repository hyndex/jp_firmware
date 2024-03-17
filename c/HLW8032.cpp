#include "HLW8032.h"
#include <pigpio.h>
#include <cstdio>
#include <cstdint>
#include <cmath>
#include <fstream> // Include for file I/O
#include <chrono>
#include <iomanip>
// #include "json.hpp" // or <nlohmann/json.hpp> depending on your setup

HLW8032::HLW8032(int rxPin) : rxPin(rxPin), serialOpen(false), validcount(0) {
    // Open a file in /dev/shm for writing meter readings
    std::string filename = "/dev/shm/" + std::to_string(rxPin) + "_meter.txt";
    meterFile.open(filename, std::ios::out);
}

void HLW8032::begin()
{
    if (!gpioInitialise())
    {
        fprintf(stderr, "Failed to initialize pigpio\n");
        return;
    }

    if (gpioSerialReadOpen(rxPin, 4800, 8))
    {
        fprintf(stderr, "Failed to open GPIO for serial reading\n");
        return;
    }

    serialOpen = true;

    // Set the voltage and current coefficients based on your resistor values
    VF = 1881.0; // Voltage coefficient based on your voltage divider resistors
    CF = 10.0;   // Current coefficient based on your shunt resistor (0.1Ω)
}

unsigned char HLW8032::ReadByte()
{
    unsigned char buf[1];
    while (true)
    {
        time_sleep(0.002933);
        if (gpioSerialRead(rxPin, buf, 1))
        {
            return buf[0];
        }
    }
}

void HLW8032::SerialReadLoop()
{
    if (!serialOpen)
    {
        return;
    }

    unsigned char firstByte = ReadByte();
    unsigned char secondByte = ReadByte();

    while (secondByte != 0x5A)
    {
        firstByte = secondByte;
        secondByte = ReadByte();
    }

    SerialTemps[0] = firstByte;
    SerialTemps[1] = secondByte;

    for (int i = 2; i < 24; i++)
    {
        SerialTemps[i] = ReadByte() & 0xFF;
    }

    if (Checksum())
    {
        processData();
    }
}

bool HLW8032::Checksum()
{
    uint8_t check = 0;
    for (int i = 2; i <= 22; i++)
    {
        check += SerialTemps[i];
    }

    if (check == SerialTemps[23])
    {
        return true;
    }
    return false;
}

void HLW8032::processData()
{
    if (!Checksum())
    {
        return;
    }

    VolPar = (SerialTemps[2] << 16) | (SerialTemps[3] << 8) | SerialTemps[4];
    CurrentPar = (SerialTemps[8] << 16) | (SerialTemps[9] << 8) | SerialTemps[10];
    PowerPar = (SerialTemps[14] << 16) | (SerialTemps[15] << 8) | SerialTemps[16];
    PF = (SerialTemps[21] << 8) | SerialTemps[22];

    VolData = (SerialTemps[20] & 0x40) ? (SerialTemps[5] << 16) | (SerialTemps[6] << 8) | SerialTemps[7] : 0;
    CurrentData = (SerialTemps[20] & 0x20) ? (SerialTemps[11] << 16) | (SerialTemps[12] << 8) | SerialTemps[13] : 0;
    PowerData = (SerialTemps[20] & 0x10) ? (SerialTemps[17] << 16) | (SerialTemps[18] << 8) | SerialTemps[19] : 0;
    if (SerialTemps[20] & 0x80) PFData++;

    float voltage = VolData != 0 ? (static_cast<float>(VolPar) / VolData) * VF : 0;
    float current = CurrentData != 0 ? (static_cast<float>(CurrentPar) / CurrentData) * CF : 0;
    float power = (PowerData != 0) ? (static_cast<float>(PowerPar) / PowerData) * VF * CF : 0;
    float powerFactor = power / (voltage * current);

    printf("GPIO: %d, Voltage: %.2f V, Current: %.2f A, Power: %.2f W, Power Factor: %.2f\n", rxPin, voltage, current, power, powerFactor);
}

HLW8032::~HLW8032() {
    if (serialOpen) {
        gpioSerialReadClose(rxPin);
    }
    gpioTerminate();
    // Close the file
    if (meterFile.is_open()) {
        meterFile.close();
    }
}
