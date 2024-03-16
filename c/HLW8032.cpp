#include "HLW8032.h"
#include <pigpio.h>
#include <cstdio>
#include <cstdint>
#include <cmath>

HLW8032::HLW8032(int rxPin) : rxPin(rxPin), serialOpen(false) {}

int validcount = 0;

// void HLW8032::begin()
// {
//     if (gpioInitialise() < 0)
//     {
//         fprintf(stderr, "Failed to initialize pigpio\n");
//         return;
//     }

//     // Open GPIO for serial reading
//     if (gpioSerialReadOpen(rxPin, 4800, 8) == 0)
//     {
//         serialOpen = true;
//     }
//     else
//     {
//         fprintf(stderr, "Failed to open GPIO for serial reading\n");
//         return;
//     }

//     VF = VolR1 / (VolR2 * 1000.0);   // Voltage factor calculation
//     CF = 1.0 / (CurrentRF * 1000.0); // Current factor calculation
// }

void HLW8032::begin()
{
    if (gpioInitialise() < 0)
    {
        fprintf(stderr, "Failed to initialize pigpio\n");
        return;
    }

    // Open GPIO for serial reading
    if (gpioSerialReadOpen(rxPin, 4800, 8) == 0)
    {
        serialOpen = true;
    }
    else
    {
        fprintf(stderr, "Failed to open GPIO for serial reading\n");
        return;
    }

    // Calculate the voltage and current factors based on the provided values
    float Rt = (4 * 470000) + 1000; // Total resistance in the voltage divider circuit (4 * 470kΩ + 1kΩ)
    float Rv = 1000;                // Resistance of the resistor connected to the voltage input pin (VP)
    Kv = Rt / Rv;                   // Voltage coefficient

    float Rs = 0.001; // Resistance of the shunt resistor (1mΩ)
    Ki = 1 / Rs;      // Current coefficient

    // You may need to adjust Kp based on your circuit design
    Kp = 1.0; // Power coefficient
}

unsigned char HLW8032::ReadByte()
{

    unsigned char buf[1];
    while (1)
    {
        time_sleep(0.002933);
        int count = gpioSerialRead(rxPin, buf, 1);
        if (count)
        {
            unsigned char val = buf[0];
            return val;
        }
    }
}

void HLW8032::SerialReadLoop()
{
    unsigned char buf[1];

    if (serialOpen)
    {
        unsigned char firstByte = ReadByte();
        unsigned char secondByte = ReadByte();

        if (secondByte != 0x5A)
        {
            while (secondByte != 0x5A)
            {
                firstByte = secondByte;
                secondByte = ReadByte();
            };
        }

        // populate SerialTemps
        SerialTemps[0] = firstByte;
        SerialTemps[1] = secondByte;

        // read and populate rest of the bytes
        for (int i = 2; i < 24; i++)
        {
            SerialTemps[i] = (unsigned int)(ReadByte() & 0xFF);
        }

        // time_sleep(0.05);

        if (Checksum() == false) // 校验测试，如果错误就抛弃
        {

            return;
        }
        else
        {
            for (int i = 0; i < 24; i++)
            {
                printf("%02X, ", SerialTemps[i]);
            }
            processData();
        }
    }
}

// bool HLW8032::Checksum()
// {
//     uint8_t sum = 0;
//     for (int i = 2; i < 23; ++i)
//     { // Starting from byte 2 as per protocol
//         sum += SerialTemps[i];
//     }
//     sum = ~sum; // Invert the sum as part of checksum calculation
//     sum += 1;   // Add 1 to the inverted sum, assuming two's complement
//     bool isValid = (sum == SerialTemps[23]);

//     printf("sum %08b, ", sum & 0xFF);
//     printf("SerialTemps[23] %08b, ", SerialTemps[23] & 0xFF);

//     if (isValid)
//     {
//         printf("Checksum Valid\n");
//     }
//     else
//     {
//         printf("Checksum Invalid\n");
//     }

//     return isValid;
// }

bool HLW8032::Checksum()
{
    uint8_t check = 0;
    for (uint8_t a = 2; a <= 22; a++)
    {
        check = check + (uint8_t)SerialTemps[a];
    }

    if (check == (uint8_t)SerialTemps[23])
    {
        printf("\n\ncount: %d Checksum Valid\n", ++validcount);
        return true;
    }
    else
    {
        return false;
    }
}

// void HLW8032::processData()
// {

//     if (!Checksum())
//     {
//         return; // Checksum failed, do not process data
//     }
//     // Process the received bytes to extract electrical parameters
//     VolPar = (SerialTemps[2] << 16) | (SerialTemps[3] << 8) | SerialTemps[4];
//     CurrentPar = (SerialTemps[8] << 16) | (SerialTemps[9] << 8) | SerialTemps[10];
//     PowerPar = (SerialTemps[14] << 16) | (SerialTemps[15] << 8) | SerialTemps[16];
//     PF = (SerialTemps[21] << 8) | SerialTemps[22];

//     if (SerialTemps[20] & 0x40)
//     {
//         VolData = (SerialTemps[5] << 16) | (SerialTemps[6] << 8) | SerialTemps[7];
//     }
//     if (SerialTemps[20] & 0x20)
//     {
//         CurrentData = (SerialTemps[11] << 16) | (SerialTemps[12] << 8) | SerialTemps[13];
//     }
//     if (SerialTemps[20] & 0x10)
//     {
//         PowerData = (SerialTemps[17] << 16) | (SerialTemps[18] << 8) | SerialTemps[19];
//     }
//     if (SerialTemps[20] & 0x80)
//     {
//         PFData++;
//     }
//     float voltage = (static_cast<float>(VolPar) * Kv) / (VolData * 1000); // Adjusted formula for voltage
//     float current = (static_cast<float>(CurrentPar) * Ki) / (CurrentData * 100); // Adjusted formula for current
//     float power = (voltage * current * Kp) / PowerPar;                   // Correct formula for power

//     printf("Voltage: %.2f V, Current: %.2f A, Power: %.2f W\n", voltage, current, power);
// }

void HLW8032::processData()
{
    if (!Checksum())
    {
        return; // Checksum failed, do not process data
    }
    // Process the received bytes to extract electrical parameters
    VolPar = (SerialTemps[2] << 16) | (SerialTemps[3] << 8) | SerialTemps[4];
    CurrentPar = (SerialTemps[8] << 16) | (SerialTemps[9] << 8) | SerialTemps[10];
    PowerPar = (SerialTemps[14] << 16) | (SerialTemps[15] << 8) | SerialTemps[16];
    PF = (SerialTemps[21] << 8) | SerialTemps[22];

    if (SerialTemps[20] & 0x40)
    {
        VolData = (SerialTemps[5] << 16) | (SerialTemps[6] << 8) | SerialTemps[7];
    }
    if (SerialTemps[20] & 0x20)
    {
        CurrentData = (SerialTemps[11] << 16) | (SerialTemps[12] << 8) | SerialTemps[13];
    }
    if (SerialTemps[20] & 0x10)
    {
        PowerData = (SerialTemps[17] << 16) | (SerialTemps[18] << 8) | SerialTemps[19];
    }
    if (SerialTemps[20] & 0x80)
    {
        PFData++;
    }

    // Assuming EnergyData is stored in bytes 22 and 23 (adjust as needed)
    EnergyData = (SerialTemps[22] << 8) | SerialTemps[23];

    float voltage = (static_cast<float>(VolPar) * Kv) / (VolData * 1000); // Adjusted formula for voltage
    float current = (static_cast<float>(CurrentPar) * Ki) / (CurrentData * 1000); // Adjusted formula for current
    float power = voltage * current; // Simplified formula for power
    float energy = static_cast<float>(EnergyData) * Ke; // Formula for energy

    printf("Voltage: %.2f V, Current: %.2f A, Power: %.2f W, Energy: %.2f Wh\n", voltage, current, power, energy);
}


float HLW8032::GetVol()
{
    // Calculate and return the voltage
    return static_cast<float>(VolPar) / VolData * VF;
}

float HLW8032::GetEnergy()
{
    // Calculate and return the energy
    return static_cast<float>(EnergyData) * Ke;
}


float HLW8032::GetVolAnalog()
{
    return static_cast<float>(VolPar) / VolData;
}

float HLW8032::GetCurrent()
{
    // Calculate and return the power
    return (static_cast<float>(PowerPar) / PowerData) * VF * CF;
}

float HLW8032::GetInspectingPower()
{
    return GetVol() * GetCurrent();
}

float HLW8032::GetActivePower()
{
    if ((SerialTemps[20] & 0x10))
    { // Power valid
        if ((SerialTemps[0] & 0xF2) == 0xF2)
        { // Power cycle exceeds range
            return 0;
        }
        else
        {
            float FPowerPar = PowerPar;
            float FPowerData = PowerData;
            // float Power = ((float)PowerPar/(float)PowerData) * VF * CF;  // 求有功功率
            float Power = (FPowerPar / FPowerData) * VF * CF; // 求有功功率
            return Power;
        }
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

HLW8032::~HLW8032()
{
    if (serialOpen)
    {
        gpioSerialReadClose(rxPin);
    }
    gpioTerminate();
}
