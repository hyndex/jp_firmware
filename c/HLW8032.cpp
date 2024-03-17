#include "HLW8032.h"
#include <pigpio.h>
#include <cstdio>
#include <cstdint>
#include <cmath>
#include <fstream>
#include <chrono>
#include <iomanip>
#include <vector>

HLW8032::HLW8032(int rxPin) : rxPin(rxPin), serialOpen(false), validcount(0) {
    // Open a file in /dev/shm for writing meter readings
    std::string filename = "/dev/shm/" + std::to_string(rxPin) + "_meter.txt";
    meterFile.open(filename, std::ios::out);
}

void HLW8032::begin() {
    if (gpioSerialReadOpen(rxPin, 4800, 8)) {
        fprintf(stderr, "Failed to open GPIO for serial reading\n");
        return;
    }

    serialOpen = true;

    // Calculate the voltage and current factors based on the provided values
    float Rt = (4 * 470000) + 1000;
    float Rv = 1000;
    Kv = Rt / Rv;

    float Rs = 0.001;
    Ki = 1 / Rs;

    Kp = 1.0;
}

void HLW8032::ReadBytes(std::vector<unsigned char>& buffer, int count) {
    buffer.resize(count);
    int bytesRead = 0;
    while (bytesRead < count) {
        int result = gpioSerialRead(rxPin, buffer.data() + bytesRead, count - bytesRead);
        if (result > 0) {
            bytesRead += result;
        } else {
            time_sleep(0.001);
        }
    }
}

void HLW8032::SerialReadLoop() {
    if (!serialOpen) {
        return;
    }

    std::vector<unsigned char> buffer;
    unsigned char byte;
    bool frameFound = false;

    // Continuously read bytes until the start of the frame is found
    while (!frameFound) {
        if (gpioSerialRead(rxPin, &byte, 1) > 0) {
            if (byte == 0x55) {
                // Potential start of frame, check next byte
                if (gpioSerialRead(rxPin, &byte, 1) > 0 && byte == 0x5A) {
                    // Start of frame found
                    buffer.push_back(0x55);
                    buffer.push_back(0x5A);
                    frameFound = true;
                }
            }
        } else {
            time_sleep(0.001); // Adjust sleep duration to match the baud rate
        }
    }

    // Read the remaining 22 bytes of the frame
    ReadBytes(buffer, 22);

    for (int i = 0; i < 24; ++i) {
        SerialTemps[i] = buffer[i];
    }

    if (Checksum()) {
        processData();
    }
}

bool HLW8032::Checksum() {
    uint8_t check = 0;
    for (int i = 2; i <= 22; i++) {
        check += SerialTemps[i];
    }

    return check == SerialTemps[23];
}


void HLW8032::processData()
{

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

    // Write the JSON string to the file, replacing old content
    if (meterFile.is_open()) {
        meterFile.seekp(0); // Move the file pointer to the beginning
        meterFile << json.str() << std::endl;
        meterFile.flush(); // Ensure the data is written to the file
    }
    printf("GPIO: %d, Voltage: %.2f V, Current: %.2f A, Power: %.2f W, Energy: %.2f Wh\n", rxPin ,voltage, current, power, energy);
}


float HLW8032::GetVol() {
    return static_cast<float>(VolPar) / VolData * Kv;
}

float HLW8032::GetEnergy() {
    return static_cast<float>(EnergyData) * Ke;
}

float HLW8032::GetVolAnalog() {
    return static_cast<float>(VolPar) / VolData;
}

float HLW8032::GetCurrent() {
    return (static_cast<float>(PowerPar) / PowerData) * Kv * Ki;
}

float HLW8032::GetInspectingPower() {
    return GetVol() * GetCurrent();
}

float HLW8032::GetActivePower() {
    if (SerialTemps[20] & 0x10) {
        if ((SerialTemps[0] & 0xF2) == 0xF2) {
            return 0;
        }
        return (static_cast<float>(PowerPar) / PowerData) * Kv * Ki;
    }
    return 0;
}

float HLW8032::GetPowerFactor() {
    return GetActivePower() / GetInspectingPower();
}

uint16_t HLW8032::GetPF() {
    return PF;
}

uint32_t HLW8032::GetPFAll() {
    return (PFData * 65536) + PF;
}

float HLW8032::GetKWh() {
    float PFcnt = (1.0 / PowerPar) * (1.0 / (Ki * Kv)) * 1e9 * 3600;
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
