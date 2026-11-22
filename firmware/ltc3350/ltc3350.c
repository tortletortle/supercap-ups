#include "ltc3350.h"

static ltc3350_result_t read_word(ltc3350_device_t *device,
                                  uint8_t reg,
                                  uint16_t *value)
{
    if ((device == 0) || (value == 0) || (device->read_word == 0)) {
        return LTC3350_ERR_ARGUMENT;
    }
    if (device->read_word(device->context, device->address_7bit, reg, value) != 0) {
        return LTC3350_ERR_BUS;
    }
    return LTC3350_OK;
}

static ltc3350_result_t write_word(ltc3350_device_t *device,
                                   uint8_t reg,
                                   uint16_t value)
{
    if ((device == 0) || (device->write_word == 0)) {
        return LTC3350_ERR_ARGUMENT;
    }
    if (device->write_word(device->context, device->address_7bit, reg, value) != 0) {
        return LTC3350_ERR_BUS;
    }
    return LTC3350_OK;
}

uint16_t ltc3350_voltage_mv_to_code(uint16_t millivolts)
{
    /* 183.5 uV/LSB = 367/2 uV/LSB; round to nearest code. */
    const uint32_t microvolts = (uint32_t)millivolts * 1000u;
    return (uint16_t)((2u * microvolts + 183u) / 367u);
}

void ltc3350_config_default_4s(ltc3350_config_t *config)
{
    if (config == 0) {
        return;
    }
    config->vshunt_code = LTC3350_VSHUNT_2V600_CODE;
    config->cap_uv_code = LTC3350_CAP_UV_1V000_CODE;
    config->cap_ov_code = LTC3350_CAP_OV_2V600_CODE;
    config->alarm_mask = LTC3350_ALARM_MASK_4S;
}

ltc3350_result_t ltc3350_configure(ltc3350_device_t *device,
                                   const ltc3350_config_t *config)
{
    uint16_t num_caps = 0u;
    uint16_t readback = 0u;
    ltc3350_result_t result;

    if ((device == 0) || (config == 0) ||
        (device->read_word == 0) || (device->write_word == 0)) {
        return LTC3350_ERR_ARGUMENT;
    }

    result = read_word(device, LTC3350_REG_NUM_CAPS, &num_caps);
    if (result != LTC3350_OK) {
        return result;
    }
    if ((num_caps & 0x0003u) != LTC3350_NUM_CAPS_4S) {
        return LTC3350_ERR_CELL_COUNT;
    }

    result = write_word(device, LTC3350_REG_VSHUNT, config->vshunt_code);
    if (result != LTC3350_OK) return result;

    result = write_word(device, LTC3350_REG_CAP_UV_LVL, config->cap_uv_code);
    if (result != LTC3350_OK) return result;

    result = write_word(device, LTC3350_REG_CAP_OV_LVL, config->cap_ov_code);
    if (result != LTC3350_OK) return result;

    result = write_word(device, LTC3350_REG_MSK_ALARMS, config->alarm_mask);
    if (result != LTC3350_OK) return result;

    result = read_word(device, LTC3350_REG_VSHUNT, &readback);
    if ((result != LTC3350_OK) || (readback != config->vshunt_code)) {
        return (result == LTC3350_OK) ? LTC3350_ERR_VERIFY : result;
    }

    result = read_word(device, LTC3350_REG_CAP_UV_LVL, &readback);
    if ((result != LTC3350_OK) || (readback != config->cap_uv_code)) {
        return (result == LTC3350_OK) ? LTC3350_ERR_VERIFY : result;
    }

    result = read_word(device, LTC3350_REG_CAP_OV_LVL, &readback);
    if ((result != LTC3350_OK) || (readback != config->cap_ov_code)) {
        return (result == LTC3350_OK) ? LTC3350_ERR_VERIFY : result;
    }

    result = read_word(device, LTC3350_REG_MSK_ALARMS, &readback);
    if ((result != LTC3350_OK) || (readback != config->alarm_mask)) {
        return (result == LTC3350_OK) ? LTC3350_ERR_VERIFY : result;
    }

    return LTC3350_OK;
}

ltc3350_result_t ltc3350_read_cell_voltage_mv(ltc3350_device_t *device,
                                              uint8_t cell_index,
                                              uint16_t *millivolts)
{
    uint16_t raw_word = 0u;
    int32_t raw_signed;
    uint32_t mv;
    ltc3350_result_t result;

    if ((device == 0) || (millivolts == 0) || (cell_index >= 4u)) {
        return LTC3350_ERR_ARGUMENT;
    }

    result = read_word(device,
                       (uint8_t)(LTC3350_REG_MEAS_VCAP1 + cell_index),
                       &raw_word);
    if (result != LTC3350_OK) {
        return result;
    }

    raw_signed = (int16_t)raw_word;
    if (raw_signed < 0) {
        return LTC3350_ERR_VERIFY;
    }

    /* 183.5 uV/LSB = 0.1835 mV/LSB; return nearest integer mV. */
    mv = ((uint32_t)raw_signed * 367u + 1000u) / 2000u;
    if (mv > 5000u) {
        return LTC3350_ERR_VERIFY;
    }
    *millivolts = (uint16_t)mv;
    return LTC3350_OK;
}

ltc3350_result_t ltc3350_read_status(ltc3350_device_t *device,
                                     ltc3350_status_t *status)
{
    ltc3350_result_t result;

    if ((device == 0) || (status == 0)) {
        return LTC3350_ERR_ARGUMENT;
    }

    result = read_word(device, LTC3350_REG_CHRG_STATUS, &status->charger_status);
    if (result != LTC3350_OK) {
        return result;
    }
    return read_word(device, LTC3350_REG_ALARM_REG, &status->alarm_status);
}

ltc3350_result_t ltc3350_clear_alarms(ltc3350_device_t *device,
                                      uint16_t alarm_mask)
{
    return write_word(device, LTC3350_REG_CLR_ALARMS, alarm_mask);
}
