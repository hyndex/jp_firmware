#ifndef HLW8032_H
#define HLW8032_H
#include <cstdint>

class HLW8032 {
public:
    HLW8032(int rxPin);
    void begin();
    unsigned char ReadByte();
    void SerialReadLoop();
    float GetVol();
    float GetVolAnalog();
    float GetCurrent();
    float GetCurrentAnalog();
    float GetActivePower();
    float GetInspectingPower();
    float GetPowerFactor();
    uint16_t GetPF();
    uint32_t GetPFAll();
    float GetKWh();
    float GetEnergy();
    ~HLW8032();

private:
    bool Checksum();
    void processData();

    int rxPin;
    bool serialOpen;
    uint8_t SerialTemps[24];
    uint32_t VolPar, CurrentPar, PowerPar, CurrentData, VolData, PowerData, EnergyData;
    uint16_t PF;
    uint32_t PFData;
    float VF, CF, Kv, Ki, Kp, Ke;
    int validcount;
};

#endif // HLW8032_H
