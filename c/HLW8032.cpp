#include "HLW8032.h"
#include <pigpio.h>
#include <cstdio>
#include <cstdint>
#include <cmath>

HLW8032::HLW8032(int rxPin) : rxPin(rxPin), serialOpen(false) {}

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

    VF = VolR1 / (VolR2 * 1000.0);   // Voltage factor calculation
    CF = 1.0 / (CurrentRF * 1000.0); // Current factor calculation
}

unsigned char HLW8032::ReadByte()
{

    unsigned char buf[1];
    while (1)
    {
        time_sleep(0.003);
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
            // printf("\n Missed");
            while (secondByte != 0x5A)
            {
                firstByte = secondByte;
                secondByte = ReadByte();
                // printf(". ");
            };
            // printf("\n");
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
        // print 24 bytes
        for (int i = 0; i < 24; i++)
        {
            printf("%02X, ", SerialTemps[i]);
            // printf("status = 0x%02X\n", (unsigned int)( SerialTemps[i] & 0xFF));
        }

        if (Checksum() == false) // 校验测试，如果错误就抛弃
        {
            return;
        }
        else
        {
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

const char *bit_rep[16] = {
    [0] = "0000",
    [1] = "0001",
    [2] = "0010",
    [3] = "0011",
    [4] = "0100",
    [5] = "0101",
    [6] = "0110",
    [7] = "0111",
    [8] = "1000",
    [9] = "1001",
    [10] = "1010",
    [11] = "1011",
    [12] = "1100",
    [13] = "1101",
    [14] = "1110",
    [15] = "1111",
};

void print_byte(uint8_t byte)
{
    printf("%s%s", bit_rep[byte >> 4], bit_rep[byte & 0x0F]);
}

bool HLW8032::Checksum()
{
    uint8_t check = 0;
    for (uint8_t a = 2; a <= 22; a++)
    {
        check = check + (uint8_t)SerialTemps[a];
    }
    printf("Check %02X, ", check & 0xFF);
    printf("SerialTemps[23] %02X, ", SerialTemps[23] & 0xFF);

    printf("\nCheck: ");
    print_byte(check);
    printf("\nSerialTemps: ");
    print_byte(SerialTemps[23]);

    if (check == (uint8_t)SerialTemps[23])
    {
        // 校验通过
        printf("Checksum Valid\n");
        return true;
    }
    else
    {
        printf("Checksum Invalid\n");
        return false; // 校验不通过
    }
}

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

    float voltage = static_cast<float>(VolPar) * VF;                    // Apply correct formula here
    float current = static_cast<float>(CurrentPar) * CF;                // Apply correct formula here
    float power = (static_cast<float>(PowerPar) / PowerData) * VF * CF; // Apply correct formula here

    printf("Voltage: %.2f V, Current: %.2f A, Power: %.2f W\n", voltage, current, power);
}

float HLW8032::GetVol()
{
    // Calculate and return the voltage
    return static_cast<float>(VolPar) / VolData * VF;
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
