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

    // Calculate the voltage and current factors based on the provided values
    float Rt = (4 * 470000) + 1000; // Total resistance in the voltage divider circuit (4 * 470kΩ + 1kΩ)
    float Rv = 1000;                // Resistance of the resistor connected to the voltage input pin (VP)
    Kv = Rt / Rv;                   // Voltage coefficient

    float Rs = 0.001; // Resistance of the shunt resistor (1mΩ)
    Ki = 1 / Rs;      // Current coefficient

    Kp = 1.0; // Power coefficient (may need adjustment based on circuit design)
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
        // for (int i = 0; i < 24; i++)
        // {
        //     printf("%02X, ", SerialTemps[i]);
        // }
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
        // printf("\n\ncount: %d Checksum Valid\n", ++validcount);
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

    EnergyData = (SerialTemps[22] << 8) | SerialTemps[23];

    float voltage = VolData != 0 ? (static_cast<float>(VolPar) * Kv) / (VolData * 1000) : 0;
    float current = CurrentData != 0 ? (static_cast<float>(CurrentPar) * Ki) / (CurrentData * 1000) : 0;
    float power = voltage * current;


    float energy = static_cast<float>(EnergyData) * Ke;

    // Get the current time
    auto now = std::chrono::system_clock::now();
    auto now_time_t = std::chrono::system_clock::to_time_t(now);
    auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;

    // Format the timestamp
    std::stringstream timestamp;
    timestamp << std::put_time(std::localtime(&now_time_t), "%Y-%m-%d %H:%M:%S");
    timestamp << '.' << std::setfill('0') << std::setw(3) << now_ms.count();

    // Construct the JSON string
    std::stringstream json;
    json << "{";
    json << "\"timestamp\": \"" << timestamp.str() << "\", ";
    json << "\"gpio\": " << rxPin << ", ";
    json << "\"voltage\": " << voltage << ", ";
    json << "\"current\": " << current << ", ";
    json << "\"power\": " << power << ", ";
    json << "\"energy\": " << energy;
    json << "}";

    // Write the JSON string to the file
    if (meterFile.is_open()) {
        meterFile << json.str() << std::endl;
    }    
    printf("GPIO: %d, Voltage: %.2f V, Current: %.2f A, Power: %.2f W, Energy: %.2f Wh\n", rxPin ,voltage, current, power, energy);
}

float HLW8032::GetVol()
{
    return static_cast<float>(VolPar) / VolData * VF;
}

float HLW8032::GetEnergy()
{
    return static_cast<float>(EnergyData) * Ke;
}

float HLW8032::GetVolAnalog()
{
    return static_cast<float>(VolPar) / VolData;
}

float HLW8032::GetCurrent()
{
    return (static_cast<float>(PowerPar) / PowerData) * VF * CF;
}

float HLW8032::GetInspectingPower()
{
    return GetVol() * GetCurrent();
}

float HLW8032::GetActivePower()
{
    if (SerialTemps[20] & 0x10)
    {
        if ((SerialTemps[0] & 0xF2) == 0xF2)
        {
            return 0;
        }
        return (static_cast<float>(PowerPar) / PowerData) * VF * CF;
    }
    return 0;
}

float HLW8032::GetPowerFactor()
{
    return GetActivePower() / GetInspectingPower();
}

uint16_t HLW8032::GetPF()
{
    return PF;
}

uint32_t HLW8032::GetPFAll()
{
    return (PFData * 65536) + PF;
}

float HLW8032::GetKWh()
{
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