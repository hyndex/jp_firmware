#include "HLW8032.h"
#include <pigpio.h>
#include <cstdio>
#include <chrono>
#include <iomanip>
#include <sstream>

HLW8032::HLW8032(int rxPin) : rxPin(rxPin), serialOpen(false) {
    std::string filename = "/dev/shm/" + std::to_string(rxPin) + "_meter.txt";
    meterFile.open(filename, std::ios::out);
}

void HLW8032::begin() {
    if (gpioSerialReadOpen(rxPin, 4800, 8)) {
        fprintf(stderr, "Failed to open GPIO for serial reading\n");
        return;
    }
    serialOpen = true;
    VF = 1881.0;
    CF = 1000.0;
}

void HLW8032::ReadBytes(std::vector<unsigned char>& buffer, int count) {
    buffer.resize(count);
    int bytesRead = 0;
    while (bytesRead < count) {
        int result = gpioSerialRead(rxPin, buffer.data() + bytesRead, count - bytesRead);
        if (result > 0) {
            bytesRead += result;
        }
    }
}

void HLW8032::SerialReadLoop() {
    if (!serialOpen) {
        return;
    }

    std::vector<unsigned char> buffer;
    ReadBytes(buffer, 24); // Read 24 bytes at once

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

void HLW8032::processData() {
    if (!Checksum()) {
        return;
    }

    VolPar = (SerialTemps[2] << 16) | (SerialTemps[3] << 8) | SerialTemps[4];
    CurrentPar = (SerialTemps[8] << 16) | (SerialTemps[9] << 8) | SerialTemps[10];
    PowerPar = (SerialTemps[14] << 16) | (SerialTemps[15] << 8) | SerialTemps[16];
    PF = (SerialTemps[21] << 8) | SerialTemps[22];

    VolData = (SerialTemps[20] & 0x40) ? (SerialTemps[5] << 16) | (SerialTemps[6] << 8) | SerialTemps[7] : 1; // Avoid division by zero
    CurrentData = (SerialTemps[20] & 0x20) ? (SerialTemps[11] << 16) | (SerialTemps[12] << 8) | SerialTemps[13] : 1; // Avoid division by zero
    PowerData = (SerialTemps[20] & 0x10) ? (SerialTemps[17] << 16) | (SerialTemps[18] << 8) | SerialTemps[19] : 1; // Avoid division by zero
    if (SerialTemps[20] & 0x80) PFData++;

    float voltage = ((static_cast<float>(VolPar) / VolData) * VF) / 1000.0; // Voltage in volts
    float current = ((static_cast<float>(CurrentPar) / CurrentData) * CF) / 1000.0; // Current in amps
    float power = ((static_cast<float>(PowerPar) / PowerData) * VF * CF) / 1000.0; // Power in watts

    float powerFactor = (voltage * current > 0) ? power / (voltage * current) : 0;

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
    json << "\"powerFactor\": " << powerFactor;
    json << "}";

    // Write the JSON string to the file, replacing old content
    if (meterFile.is_open()) {
        meterFile.seekp(0); // Move the file pointer to the beginning
        meterFile << json.str() << std::endl;
        meterFile.flush(); // Ensure the data is written to the file
    }

    printf("GPIO: %d, Voltage: %.2f V, Current: %.2f A, Power: %.2f W, Power Factor: %.2f\n", rxPin, voltage, current, power, powerFactor);
}


HLW8032::~HLW8032() {
    if (serialOpen) {
        gpioSerialReadClose(rxPin);
    }
    if (meterFile.is_open()) {
        meterFile.close();
    }
}
