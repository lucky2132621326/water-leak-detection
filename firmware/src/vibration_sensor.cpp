#include "vibration_sensor.h"
#include "config.h"

#include <Wire.h>
#include <math.h>

// MPU6050 registers
static const uint8_t MPU_ADDR       = 0x68;
static const uint8_t REG_PWR_MGMT_1 = 0x6B;
static const uint8_t REG_CONFIG     = 0x1A;
static const uint8_t REG_ACCEL_CFG  = 0x1C;
static const uint8_t REG_ACCEL_XOUT = 0x3B;

// DLPF setting 0x02 gives ~260 Hz accelerometer bandwidth. This matters: we
// sample at 500 Hz, so Nyquist is 250 Hz. Without the filter, vibration above
// that folds back down INTO the 50-150 Hz leak band and would be indistinguishable
// from a leak.
static const uint8_t DLPF_260HZ     = 0x02;
// ±2g. The pipe-wall accelerations we care about are small; a wider range would
// throw away resolution where the whole signal lives.
static const uint8_t ACCEL_RANGE_2G = 0x00;
static const float   ACCEL_LSB_PER_G = 16384.0f;

static void writeReg(uint8_t reg, uint8_t value) {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(reg);
    Wire.write(value);
    Wire.endTransmission();
}

bool VibrationSensor::begin() {
    Wire.beginTransmission(MPU_ADDR);
    if (Wire.endTransmission() != 0) {
        present = false;
        return false;
    }
    writeReg(REG_PWR_MGMT_1, 0x00);      // wake
    delay(50);
    writeReg(REG_CONFIG, DLPF_260HZ);    // anti-alias — see note above
    writeReg(REG_ACCEL_CFG, ACCEL_RANGE_2G);
    present = true;
    piezo   = detectPiezo();
    return true;
}

bool VibrationSensor::detectPiezo() {
    // A fitted disc, with its 1M bleed resistor to ground, rests near zero and
    // shows small movement. An unconnected pin floats and reads high and erratic.
    // Sampling the spread rather than the level is what separates the two.
    uint32_t minV = 4095, maxV = 0;
    for (int i = 0; i < 64; i++) {
        uint16_t v = analogRead(PIN_PIEZO);
        if (v < minV) minV = v;
        if (v > maxV) maxV = v;
        delayMicroseconds(200);
    }
    const uint32_t spread = maxV - minV;
    // A floating ADC pin swings wildly across the range; a terminated one does not.
    return (minV < 500) && (spread < 2000);
}

void VibrationSensor::readAccelBurst(float* buffer, size_t count) {
    // Fixed-interval sampling. Jitter here would smear the spectrum and blur
    // the band edges the whole method depends on.
    const uint32_t periodUs = 1000000UL / VIB_SAMPLE_RATE_HZ;
    uint32_t next = micros();

    for (size_t i = 0; i < count; i++) {
        while ((int32_t)(micros() - next) < 0) { /* spin to the sample instant */ }
        next += periodUs;

        Wire.beginTransmission(MPU_ADDR);
        Wire.write(REG_ACCEL_XOUT);
        Wire.endTransmission(false);
        Wire.requestFrom(MPU_ADDR, (uint8_t)6);

        int16_t ax = (Wire.read() << 8) | Wire.read();
        int16_t ay = (Wire.read() << 8) | Wire.read();
        int16_t az = (Wire.read() << 8) | Wire.read();

        // Magnitude, so the reading does not depend on how the sensor happens to
        // be oriented on the pipe. Gravity is removed by the DC subtraction below.
        buffer[i] = sqrtf((float)ax * ax + (float)ay * ay + (float)az * az) / ACCEL_LSB_PER_G;
    }
}

void VibrationSensor::computeBands(const float* buffer, size_t count, VibrationSample& out) {
    // Remove DC (gravity plus any mounting bias) before the transform. Left in,
    // it would dominate the low band and swamp everything else.
    float mean = 0.0f;
    for (size_t i = 0; i < count; i++) mean += buffer[i];
    mean /= (float)count;

    float sumSq = 0.0f;
    for (size_t i = 0; i < count; i++) {
        const float v = buffer[i] - mean;
        sumSq += v * v;
    }
    out.rms = sqrtf(sumSq / (float)count);

    // Goertzel per frequency bin rather than a full FFT. We need three band
    // sums, not a spectrum, and Goertzel costs no buffer and no twiddle table —
    // which matters on a board that is also servicing three pulse interrupts.
    const float binHz = (float)VIB_SAMPLE_RATE_HZ / (float)count;
    float low = 0.0f, mid = 0.0f, high = 0.0f;

    for (int bin = 1; bin < (int)(count / 2); bin++) {
        const float freq = bin * binHz;
        if (freq < VIB_BAND_LOW_HZ || freq > VIB_BAND_HIGH_HZ) continue;

        const float w = 2.0f * (float)M_PI * bin / (float)count;
        const float coeff = 2.0f * cosf(w);
        float s0 = 0.0f, s1 = 0.0f, s2 = 0.0f;
        for (size_t i = 0; i < count; i++) {
            s0 = (buffer[i] - mean) + coeff * s1 - s2;
            s2 = s1;
            s1 = s0;
        }
        const float power = sqrtf(s1 * s1 + s2 * s2 - coeff * s1 * s2) / (count / 2.0f);

        if (freq < VIB_BAND_MID_LO_HZ)       low  += power;
        else if (freq <= VIB_BAND_MID_HI_HZ) mid  += power;
        else                                 high += power;
    }

    out.bandLow  = low;
    out.bandMid  = mid;
    out.bandHigh = high;
}

void VibrationSensor::readPiezo(VibrationSample& out) {
    const size_t count = (PIEZO_SAMPLE_RATE_HZ * PIEZO_SAMPLE_MS) / 1000;
    const uint32_t periodUs = 1000000UL / PIEZO_SAMPLE_RATE_HZ;

    // Streaming accumulators: 500 samples of float would be 2 KB of stack on top
    // of the 2 KB the accelerometer burst already holds.
    float mean = 0.0f, sumSq = 0.0f;
    float weightedFreq = 0.0f, totalMag = 0.0f;
    float prev = 0.0f;
    uint32_t next = micros();

    for (size_t i = 0; i < count; i++) {
        while ((int32_t)(micros() - next) < 0) {}
        next += periodUs;

        const float v = analogRead(PIN_PIEZO) / 4095.0f;
        mean += v / (float)count;
        sumSq += v * v;

        // Zero-crossing-weighted centroid: a cheap stand-in for a spectral
        // centroid. The absolute number is not meaningful on its own — the
        // backend only uses whether it RISES, which a leak jet makes it do.
        if (i > 0) {
            const float delta = fabsf(v - prev);
            weightedFreq += delta * (float)PIEZO_SAMPLE_RATE_HZ * 0.5f;
            totalMag += delta;
        }
        prev = v;
    }

    out.hasPiezo = true;
    out.piezoRms = sqrtf(sumSq / (float)count) - mean;
    out.piezoCentroid = (totalMag > 1e-6f) ? (weightedFreq / totalMag) : 0.0f;
}

VibrationSample VibrationSensor::read() {
    VibrationSample out;
    if (!present) return out;   // hasAccelerometer stays false — the backend
                                // marks the channel inactive rather than quiet

    static float buffer[VIB_SAMPLE_COUNT];
    readAccelBurst(buffer, VIB_SAMPLE_COUNT);
    computeBands(buffer, VIB_SAMPLE_COUNT, out);
    out.hasAccelerometer = true;

    if (piezo) readPiezo(out);
    return out;
}
