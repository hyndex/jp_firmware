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

    // Set the voltage and current factors based on the provided values
    VF = 1880000.0 / 1000.0; // Voltage divider Upstream resistors 470K*4  1880K / Downstream resistor 1K
    CF = 1.0 / (0.1 * 1000.0); // 1 / (CurrentRF * 1000.0)
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

    // Output the data
    printf("Voltage: %.2f V, Current: %.2f A, Power: %.2f W\n", GetVol(), GetCurrent(), GetActivePower());
}

float HLW8032::GetVol()
{
    return VolData != 0 ? (static_cast<float>(VolPar) / VolData) * VF : 0;
}

float HLW8032::GetCurrent()
{
    return CurrentData != 0 ? (static_cast<float>(CurrentPar) / CurrentData) * CF : 0;
}

float HLW8032::GetActivePower()
{
    return (PowerData != 0) ? (static_cast<float>(PowerPar) / PowerData) * VF * CF : 0;
}

float HLW8032::GetKWh()
{
    // Adjust this formula based on how you calculate energy in the first script
    float PFcnt = (1.0 / PowerPar) * (1.0 / (CF * VF)) * 1e9 * 3600;
    return GetPFAll() / PFcnt;
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
