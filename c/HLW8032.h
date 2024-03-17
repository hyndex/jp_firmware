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

private:
    void ReadBytes(std::vector<unsigned char>& buffer, int count);
    bool Checksum();
    void processData();

    int rxPin;
    bool serialOpen;
    uint8_t SerialTemps[24];
    uint32_t VolPar, CurrentPar, PowerPar, CurrentData, VolData, PowerData;
    uint16_t PF;
    uint32_t PFData;
    float VF, CF;
    std::ofstream meterFile;
};

#endif // HLW8032_H
