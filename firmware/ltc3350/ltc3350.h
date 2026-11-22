#ifndef LTC3350_H
#define LTC3350_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LTC3350_I2C_ADDR_7BIT       0x09u

#define LTC3350_REG_CLR_ALARMS      0x00u
#define LTC3350_REG_MSK_ALARMS      0x01u
#define LTC3350_REG_VSHUNT          0x06u
#define LTC3350_REG_CAP_UV_LVL      0x07u
#define LTC3350_REG_CAP_OV_LVL      0x08u
#define LTC3350_REG_NUM_CAPS        0x1Au
#define LTC3350_REG_CHRG_STATUS     0x1Bu
#define LTC3350_REG_ALARM_REG       0x1Du
#define LTC3350_REG_MEAS_VCAP1      0x20u
#define LTC3350_REG_MEAS_VCAP2      0x21u
#define LTC3350_REG_MEAS_VCAP3      0x22u
#define LTC3350_REG_MEAS_VCAP4      0x23u

#define LTC3350_NUM_CAPS_4S         3u
#define LTC3350_ALARM_CAP_UV        (1u << 0)
#define LTC3350_ALARM_CAP_OV        (1u << 1)
#define LTC3350_ALARM_MASK_4S       (LTC3350_ALARM_CAP_UV | LTC3350_ALARM_CAP_OV)

/* 183.5 uV/LSB for VSHUNT, CAP_UV, CAP_OV and per-cell voltage ADCs. */
#define LTC3350_VSHUNT_2V600_CODE   0x3759u
#define LTC3350_CAP_UV_1V000_CODE   0x154Au
#define LTC3350_CAP_OV_2V600_CODE   0x3759u

typedef enum {
    LTC3350_OK = 0,
    LTC3350_ERR_ARGUMENT = -1,
    LTC3350_ERR_BUS = -2,
    LTC3350_ERR_CELL_COUNT = -3,
    LTC3350_ERR_VERIFY = -4
} ltc3350_result_t;

/*
 * The callbacks must implement SMBus Read Word / Write Word semantics.
 * The device address is the 7-bit address (0x09); the register is the
 * SMBus command code. SMBus word data is transferred low byte first.
 */
typedef int (*ltc3350_write_word_fn)(
    void *context, uint8_t address_7bit, uint8_t command, uint16_t value);

typedef int (*ltc3350_read_word_fn)(
    void *context, uint8_t address_7bit, uint8_t command, uint16_t *value);

typedef struct {
    void *context;
    ltc3350_write_word_fn write_word;
    ltc3350_read_word_fn read_word;
    uint8_t address_7bit;
} ltc3350_device_t;

typedef struct {
    uint16_t vshunt_code;
    uint16_t cap_uv_code;
    uint16_t cap_ov_code;
    uint16_t alarm_mask;
} ltc3350_config_t;

typedef struct {
    uint16_t charger_status;
    uint16_t alarm_status;
} ltc3350_status_t;

void ltc3350_config_default_4s(ltc3350_config_t *config);
ltc3350_result_t ltc3350_configure(ltc3350_device_t *device,
                                   const ltc3350_config_t *config);
ltc3350_result_t ltc3350_read_cell_voltage_mv(ltc3350_device_t *device,
                                              uint8_t cell_index,
                                              uint16_t *millivolts);
ltc3350_result_t ltc3350_read_status(ltc3350_device_t *device,
                                     ltc3350_status_t *status);
ltc3350_result_t ltc3350_clear_alarms(ltc3350_device_t *device,
                                      uint16_t alarm_mask);
uint16_t ltc3350_voltage_mv_to_code(uint16_t millivolts);

#ifdef __cplusplus
}
#endif

#endif
