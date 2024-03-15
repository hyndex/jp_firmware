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

void HLW8032::SerialReadLoop()
{
    char buf[24];

    if (serialOpen)
    {
        int count = gpioSerialRead(rxPin, buf, sizeof(buf));

        // log
        printf("count: %d\n", count);

        // read rest and ignore
        if (count != 24)
        {
            int x = gpioSerialRead(rxPin, buf, sizeof(buf));
            return;
        }

        // read full 24 bytes
        for (int i = 0; i < 24; i++)
        {
            SerialTemps[i] = buf[i];
        }

// check reg
        if (SerialTemps[1] != 0x5A) // 标记识别,如果不是就抛弃
		{
			while (SerialID->read() >= 0)
			{
			}
			return;
		}

		if (Checksum() == false) // 校验测试，如果错误就抛弃
		{
			// Serial.println("crc error");
			return;
		}
    }
}

bool HLW8032::Checksum()
{
    uint8_t sum = 0;
    for (int i = 2; i < 23; ++i)
    { // Starting from byte 2 as per protocol
        sum += SerialTemps[i];
    }
    sum = ~sum; // Invert the sum as part of checksum calculation
    sum += 1;   // Add 1 to the inverted sum, assuming two's complement
    bool isValid = (sum == SerialTemps[23]);

    if (isValid)
    {
        printf("Checksum Valid\n");
    }
    else
    {
        printf("Checksum Invalid\n");
    }

    return isValid;
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

float HLW8032::GetPowerFactor()
{
    return GetActivePower() / GetInspectingPower();
}

uint16_t HLW8032::GetPF()
{
    return PF;
}

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
