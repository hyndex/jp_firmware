#ifndef HLW8032_H
#define HLW8032_H

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
    ~HLW8032();

private:
    bool Checksum();
    void processData();
    uint8_t readByteFromRXPin();

    int rxPin;
    bool serialOpen; // Declare the serialOpen variable here
    uint8_t SerialTemps[24];  // Serial data buffer

    float VF;
    float CF;

    uint32_t VolPar = 0;
    uint32_t CurrentPar = 0;
    uint32_t PowerPar = 0;
    uint32_t CurrentData = 0;
    uint32_t VolData = 0;
    uint32_t PowerData = 0;
    uint16_t PF = 0;
    uint32_t PFData = 0;

    uint32_t VolR1 = 1880000;
    uint32_t VolR2 = 1000;
    float CurrentRF = 0.001;
};

#endif // HLW8032_H
