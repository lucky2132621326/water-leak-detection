#include "vibration_sensor.h"
#include "config.h"
#include <Adafruit_Sensor.h>
#include <arduinoFFT.h>

static double vReal[VIBRATION_SAMPLE_COUNT];
static double vImag[VIBRATION_SAMPLE_COUNT];

VibrationSensor::VibrationSensor() : ready(false) {}

void VibrationSensor::begin() {
    ready = mpu.begin(0x68, &Wire);
    if (!ready) {
        Serial.println("[MPU6050] WARNING: sensor not found on I2C bus — acoustic channel will report unavailable");
        return;
    }
    mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    // ~260 Hz DLPF bandwidth to avoid aliasing at 500 Hz sample rate (spec 5.3).
    mpu.setFilterBandwidth(MPU6050_BAND_260_HZ);
}

VibrationSample VibrationSensor::sampleBurst() {
    VibrationSample result = {false, 0.0f, 0.0f, 0.0f, 0.0f};
    if (!ready) return result;

    const unsigned long periodUs = 1000000UL / VIBRATION_SAMPLE_RATE_HZ;
    sensors_event_t accel, gyro, temp;
    double sumSq = 0.0;

    for (int i = 0; i < VIBRATION_SAMPLE_COUNT; i++) {
        unsigned long sampleStart = micros();
        mpu.getEvent(&accel, &gyro, &temp);
        // Vector magnitude minus 1g gravity — leaves just the vibration
        // component regardless of how the sensor is oriented on the pipe.
        float mag = sqrtf(accel.acceleration.x * accel.acceleration.x
                           + accel.acceleration.y * accel.acceleration.y
                           + accel.acceleration.z * accel.acceleration.z) - 9.80665f;
        vReal[i] = mag;
        vImag[i] = 0.0;
        sumSq += (double)mag * (double)mag;

        while (micros() - sampleStart < periodUs) {
            // Busy-wait to hold the sample rate steady — this burst is
            // already meant to be the one blocking operation in the loop.
        }
    }

    ArduinoFFT<double> FFT(vReal, vImag, VIBRATION_SAMPLE_COUNT, (double)VIBRATION_SAMPLE_RATE_HZ);
    FFT.windowing(FFTWindow::Hamming, FFTDirection::Forward);
    FFT.compute(FFTDirection::Forward);
    FFT.complexToMagnitude();

    const double binHz = (double)VIBRATION_SAMPLE_RATE_HZ / VIBRATION_SAMPLE_COUNT;
    double lowSum = 0, midSum = 0, highSum = 0;
    int lowN = 0, midN = 0, highN = 0;

    // Bin 0 is DC (sensor tilt/orientation), skip it — not vibration.
    for (int i = 1; i < VIBRATION_SAMPLE_COUNT / 2; i++) {
        double freqHz = i * binHz;
        double mag = vReal[i];
        if (freqHz >= 10.0 && freqHz < 50.0) { lowSum += mag; lowN++; }
        else if (freqHz >= 50.0 && freqHz < 150.0) { midSum += mag; midN++; }
        else if (freqHz >= 150.0 && freqHz <= 250.0) { highSum += mag; highN++; }
    }

    result.valid = true;
    result.rms = (float)sqrt(sumSq / VIBRATION_SAMPLE_COUNT);
    result.band_low = lowN ? (float)(lowSum / lowN) : 0.0f;
    result.band_mid = midN ? (float)(midSum / midN) : 0.0f;
    result.band_high = highN ? (float)(highSum / highN) : 0.0f;
    return result;
}
