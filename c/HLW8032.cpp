#include "HLW8032.h"
#include <pigpio.h>
#include <cstdio>
#include <cstdint>
#include <cmath>

HLW8032::HLW8032(int rxPin) : rxPin(rxPin) {}

void HLW8032::begin() {
    if (gpioInitialise() < 0) {
        fprintf(stderr, "Failed to initialize pigpio\n");
        return;
    }
    gpioSetMode(rxPin, PI_INPUT);
    gpioSetPullUpDown(rxPin, PI_PUD_UP);

    VF = VolR1 / (VolR2 * 1000.0);
    CF = 1.0 / (CurrentRF * 1000.0);
}

uint8_t HLW8032::readByteFromRXPin() {
    uint8_t result = 0;
    const int bitDelay = 1000000 / 4800;

    while (gpioRead(rxPin) == PI_HIGH);

    gpioDelay(bitDelay / 2);

    for (int i = 0; i < 8; i++) {
        gpioDelay(bitDelay);
        result |= (gpioRead(rxPin) << i);
    }

    gpioDelay(bitDelay);
    return result;
}

void HLW8032::SerialReadLoop() {
    for (int i = 0; i < 24; ++i) {
        SerialTemps[i] = readByteFromRXPin();
        printf("Byte %d: 0x%02X\n", i, SerialTemps[i]);
    }

    if (!Checksum()) {
        printf("Checksum error\n");
        return;
    }

    processData();
}

bool HLW8032::Checksum() {
    uint8_t sum = 0;
    for (int i = 2; i < 23; ++i) {
        sum += SerialTemps[i];
    }
    return (sum == SerialTemps[23]);
}

void HLW8032::processData() {
    // Process the received bytes to extract electrical parameters
    VolPar = (SerialTemps[2] << 16) | (SerialTemps[3] << 8) | SerialTemps[4];
    CurrentPar = (SerialTemps[8] << 16) | (SerialTemps[9] << 8) | SerialTemps[10];
    PowerPar = (SerialTemps[14] << 16) | (SerialTemps[15] << 8) | SerialTemps[16];
    PF = (SerialTemps[21] << 8) | SerialTemps[22];

    if (SerialTemps[20] & 0x40) {
        VolData = (SerialTemps[5] << 16) | (SerialTemps[6] << 8) | SerialTemps[7];
    }
    if (SerialTemps[20] & 0x20) {
        CurrentData = (SerialTemps[11] << 16) | (SerialTemps[12] << 8) | SerialTemps[13];
    }
    if (SerialTemps[20] & 0x10) {
        PowerData = (SerialTemps[17] << 16) | (SerialTemps[18] << 8) | SerialTemps[19];
    }
    if (SerialTemps[20] & 0x80) {
        PFData++;
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


HLW8032::~HLW8032() {
    gpioTerminate();
}
