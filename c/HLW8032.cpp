#include "HLW8032.h"
#include <cstdio>  // For printf

HLW8032::HLW8032(int rxPin)
{
    this->rxPin = rxPin;
    this->serialHandle = -1;
}

void HLW8032::begin(const char *serialPort)
{
    pinMode(rxPin, OUTPUT);
    digitalWrite(rxPin, LOW);
    delay(10);
    this->serialHandle = serialOpen(serialPort, 4800);
    if (this->serialHandle == -1)
    {
        // Handle error
    }
    digitalWrite(rxPin, HIGH);

    VF = VolR1 / (VolR2 * 1000.0);
    CF = 1.0 / (CurrentRF * 1000.0);
}

void HLW8032::SerialReadLoop()
{
    if (serialDataAvail(this->serialHandle) > 0)
    {
        delay(55);
        int dataLen = serialDataAvail(this->serialHandle);

        if (dataLen != 24)
        {
            serialFlush(this->serialHandle);
            return;
        }

        for (int i = 0; i < dataLen; ++i)
        {
            SerialTemps[i] = serialGetchar(this->serialHandle);
            printf("Byte %d: 0x%02X\n", i, SerialTemps[i]); // Print each byte as it is read
        }

        if (SerialTemps[1] != 0x5A || !Checksum())
        {
            return;
        }

        VolPar = (static_cast<uint32_t>(SerialTemps[2]) << 16) +
                 (static_cast<uint32_t>(SerialTemps[3]) << 8) + SerialTemps[4];

        if (SerialTemps[20] & 0x40)
        {
            VolData = (static_cast<uint32_t>(SerialTemps[5]) << 16) +
                      (static_cast<uint32_t>(SerialTemps[6]) << 8) + SerialTemps[7];
        }

        CurrentPar = (static_cast<uint32_t>(SerialTemps[8]) << 16) +
                     (static_cast<uint32_t>(SerialTemps[9]) << 8) + SerialTemps[10];

        if (SerialTemps[20] & 0x20)
        {
            CurrentData = (static_cast<uint32_t>(SerialTemps[11]) << 16) +
                          (static_cast<uint32_t>(SerialTemps[12]) << 8) + SerialTemps[13];
        }

        PowerPar = (static_cast<uint32_t>(SerialTemps[14]) << 16) +
                   (static_cast<uint32_t>(SerialTemps[15]) << 8) + SerialTemps[16];

        if (SerialTemps[20] & 0x10)
        {
            PowerData = (static_cast<uint32_t>(SerialTemps[17]) << 16) +
                        (static_cast<uint32_t>(SerialTemps[18]) << 8) + SerialTemps[19];
        }

        PF = (static_cast<uint32_t>(SerialTemps[21]) << 8) + SerialTemps[22];

        if (SerialTemps[20] & 0x80)
        {
            PFData++;
        }
    }
}

float HLW8032::GetVol()
{
    return GetVolAnalog() * VF;
}

float HLW8032::GetVolAnalog()
{
    return static_cast<float>(VolPar) / VolData;
}

float HLW8032::GetCurrent()
{
    return GetCurrentAnalog() * CF;
}

float HLW8032::GetCurrentAnalog()
{
    return static_cast<float>(CurrentPar) / CurrentData;
}

float HLW8032::GetActivePower()
{
    return (static_cast<float>(PowerPar) / PowerData) * VF * CF;
}

float HLW8032::GetInspectingPower()
{
    return GetVol() * GetCurrent();
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

bool HLW8032::Checksum()
{
    uint8_t check = 0;
    for (int i = 2; i <= 22; ++i)
    {
        check += SerialTemps[i];
    }
    printf("Calculated checksum: %02x, Expected: %02x\n", check, SerialTemps[23]);
    return check == SerialTemps[23];
}
