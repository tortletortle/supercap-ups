#include "ltc3350.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint16_t registers[256];
    unsigned write_count;
    uint8_t last_write_reg;
    uint16_t last_write_value;
    int fail_read;
    int fail_write;
} fake_bus_t;

static int fake_write_word(void *context, uint8_t address, uint8_t command, uint16_t value)
{
    fake_bus_t *bus = (fake_bus_t *)context;
    assert(address == LTC3350_I2C_ADDR_7BIT);
    if (bus->fail_write) return -1;
    if (command == LTC3350_REG_CLR_ALARMS) {
        bus->registers[LTC3350_REG_ALARM_REG] &= (uint16_t)~value;
    } else {
        bus->registers[command] = value;
    }
    bus->write_count++;
    bus->last_write_reg = command;
    bus->last_write_value = value;
    return 0;
}

static int fake_read_word(void *context, uint8_t address, uint8_t command, uint16_t *value)
{
    fake_bus_t *bus = (fake_bus_t *)context;
    assert(address == LTC3350_I2C_ADDR_7BIT);
    if (bus->fail_read) return -1;
    *value = bus->registers[command];
    return 0;
}

static ltc3350_device_t make_device(fake_bus_t *bus)
{
    ltc3350_device_t device;
    device.context = bus;
    device.write_word = fake_write_word;
    device.read_word = fake_read_word;
    device.address_7bit = LTC3350_I2C_ADDR_7BIT;
    return device;
}

static void test_configures_4s(void)
{
    fake_bus_t bus;
    ltc3350_device_t device;
    ltc3350_config_t config;

    memset(&bus, 0, sizeof(bus));
    bus.registers[LTC3350_REG_NUM_CAPS] = 3u;
    device = make_device(&bus);
    ltc3350_config_default_4s(&config);

    assert(ltc3350_configure(&device, &config) == LTC3350_OK);
    assert(bus.registers[LTC3350_REG_VSHUNT] == 0x3759u);
    assert(bus.registers[LTC3350_REG_CAP_UV_LVL] == 0x154Au);
    assert(bus.registers[LTC3350_REG_CAP_OV_LVL] == 0x3759u);
    assert(bus.registers[LTC3350_REG_MSK_ALARMS] == 0x0003u);
    assert(bus.write_count == 4u);
}

static void test_rejects_wrong_cell_count(void)
{
    fake_bus_t bus;
    ltc3350_device_t device;
    ltc3350_config_t config;

    memset(&bus, 0, sizeof(bus));
    bus.registers[LTC3350_REG_NUM_CAPS] = 2u;
    device = make_device(&bus);
    ltc3350_config_default_4s(&config);

    assert(ltc3350_configure(&device, &config) == LTC3350_ERR_CELL_COUNT);
    assert(bus.write_count == 0u);
}

static void test_cell_voltage_conversion(void)
{
    fake_bus_t bus;
    ltc3350_device_t device;
    uint16_t mv = 0u;
    uint16_t code = ltc3350_voltage_mv_to_code(2500u);

    memset(&bus, 0, sizeof(bus));
    device = make_device(&bus);
    bus.registers[LTC3350_REG_MEAS_VCAP3] = code;

    assert(ltc3350_read_cell_voltage_mv(&device, 2u, &mv) == LTC3350_OK);
    assert(mv >= 2499u && mv <= 2501u);
}

static void test_status_and_alarm_clear(void)
{
    fake_bus_t bus;
    ltc3350_device_t device;
    ltc3350_status_t status;

    memset(&bus, 0, sizeof(bus));
    device = make_device(&bus);
    bus.registers[LTC3350_REG_CHRG_STATUS] = 0x0043u;
    bus.registers[LTC3350_REG_ALARM_REG] = 0x0001u;

    assert(ltc3350_read_status(&device, &status) == LTC3350_OK);
    assert(status.charger_status == 0x0043u);
    assert(status.alarm_status == 0x0001u);
    assert(ltc3350_clear_alarms(&device, 0x0001u) == LTC3350_OK);
    assert(bus.registers[LTC3350_REG_ALARM_REG] == 0x0000u);
}

static void test_bus_error_propagates(void)
{
    fake_bus_t bus;
    ltc3350_device_t device;
    uint16_t mv = 0u;

    memset(&bus, 0, sizeof(bus));
    device = make_device(&bus);
    bus.fail_read = 1;

    assert(ltc3350_read_cell_voltage_mv(&device, 0u, &mv) == LTC3350_ERR_BUS);
}

int main(void)
{
    test_configures_4s();
    test_rejects_wrong_cell_count();
    test_cell_voltage_conversion();
    test_status_and_alarm_clear();
    test_bus_error_propagates();
    puts("LTC3350 driver tests: 5/5 passed");
    return 0;
}
