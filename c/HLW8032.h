#ifndef HLW8032_H
#define HLW8032_H

#include <cstdint>
#include <fstream>
#include <vector>

class HLW8032 {
public:
    HLW8032(int rxPin);
    void begin();
    void SerialReadLoop();
    ~HLW8032();

    // Getters for various parameters
    float GetVol();
    float GetEnergy();
    float GetVolAnalog();
    float GetCurrent();
    float GetInspectingPower();
    float GetActivePower();
    float GetPowerFactor();
    uint16_t GetPF();
    uint32_t GetPFAll();
    float GetKWh();

private:
    void ReadBytes(std::vector<unsigned char>& buffer, int count);
    bool Checksum();
    void processData();

    int rxPin;
    bool serialOpen;
    uint8_t SerialTemps[24];
    uint32_t VolPar, CurrentPar, PowerPar, VolData, CurrentData, PowerData, EnergyData;
    uint16_t PF;
    uint32_t PFData;
    float Kv, Ki, Kp, Ke;
    std::ofstream meterFile;
    int validcount;
};

#endif // HLW8032_H
