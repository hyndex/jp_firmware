#include "HLW8032.h"
#include <pigpio.h>
#include <cstdio>
#include <chrono>
#include <iomanip>
#include <sstream>

HLW8032::HLW8032(int rxPin) : rxPin(rxPin), serialOpen(false) {
    // Open a file in /dev/shm for writing meter readings
    std::string filename = "/dev/shm/" + std::to_string(rxPin) + "_meter.txt";
    meterFile.open(filename, std::ios::out);
}

void HLW8032::begin() {
    if (!gpioInitialise()) {
        fprintf(stderr, "Failed to initialize pigpio\n");
        return;
    }

    if (gpioSerialReadOpen(rxPin, 4800, 8)) {
        fprintf(stderr, "Failed to open GPIO for serial reading\n");
        return;
    }

    serialOpen = true;

    // Set the voltage and current coefficients based on your resistor values
    VF = 1881.0; // Voltage coefficient based on your voltage divider resistors
    CF = 10.0;   // Current coefficient based on your shunt resistor (0.1Ω)
}

unsigned char HLW8032::ReadByte() {
    unsigned char buf[1];
    while (true) {
        time_sleep(0.002933);
        if (gpioSerialRead(rxPin, buf, 1)) {
            return buf[0];
        }
    }
}

void HLW8032::SerialReadLoop() {
    if (!serialOpen) {
        return;
    }

    unsigned char firstByte = ReadByte();
    unsigned char secondByte = ReadByte();

    while (secondByte != 0x5A) {
        firstByte = secondByte;
        secondByte = ReadByte();
    }

    SerialTemps[0] = firstByte;
    SerialTemps[1] = secondByte;

    for (int i = 2; i < 24; i++) {
        SerialTemps[i] = ReadByte() & 0xFF;
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

    // Apply scaling factors
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
    gpioTerminate();
    // Close the file
    if (meterFile.is_open()) {
        meterFile.close();
    }
}
