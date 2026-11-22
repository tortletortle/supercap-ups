# LTC3350 portable firmware driver

This is a platform-independent C11 driver prototype. It is deliberately not tied to the CH32V003 SDK yet; the board layer supplies SMBus Read Word and Write Word callbacks.

## Implemented

- Verify that the hardware is configured for four series capacitors by reading NUM_CAPS.
- Program VSHUNT to 2.60 V.
- Program per-cell CAP_UV and CAP_OV alarm thresholds to 1.00 V and 2.60 V.
- Enable the capacitor UV/OV alarm mask.
- Read individual capacitor voltages in millivolts.
- Read charger/alarm status and clear latched alarms.
- Verify the configuration registers after writing.

## Bus contract

- 7-bit LTC3350 address: 0x09. A raw 8-bit address byte is 0x12 for write or 0x13 for read; most MCU I²C APIs want the 7-bit value 0x09.
- Register addresses are SMBus command bytes.
- Word data is transferred low byte first.
- The callback must issue a repeated-start for Read Word if required by the MCU peripheral.

Do not confuse the 7-bit device address 0x09 with register subaddress 0x09, which is a separate LTC3350 register.

## Default 4S configuration

| Register | Address | Value | Meaning |
|---|---:|---:|---|
| VSHUNT | 0x06 | 0x3759 | 2.60 V shunt threshold |
| CAP_UV_LVL | 0x07 | 0x154A | 1.00 V per-cell undervoltage alarm |
| CAP_OV_LVL | 0x08 | 0x3759 | 2.60 V per-cell overvoltage alarm |
| MSK_ALARMS | 0x01 | 0x0003 | Enable capacitor UV and OV alarms |
| NUM_CAPS | 0x1A | expected low bits = 3 | Four series capacitors |

The voltage code scale is 183.5 µV/LSB. Per-cell voltage ADC registers are 0x20–0x23.

## Startup and safety

The IC's power-up default VSHUNT is 2.70 V. This driver writes 2.60 V after the MCU can communicate. If 2.60 V is a mandatory limit from the instant charging begins, the hardware must hold the charger input disabled until configuration is complete; otherwise the initial interval uses the IC's 2.70 V default.

CAP_UV/CAP_OV are ADC-based alarm thresholds, not independent fast hardware disconnects. The ADC scans multiple channels; a given cell is revisited roughly every 18 ms. Keep the independent group UVLO. If a hard per-cell discharge cutoff is required, add a separate hardware path.

SMBALERT uses the SMBus Alert Response Address mechanism. This prototype does not yet implement the ARA transaction; the board layer must add it if the design relies on SMBALERT interrupt deassertion. Polling ALARM_REG remains available.

The four-cell selection pins must be strapped for four capacitors as specified in the data sheet. The driver checks NUM_CAPS before changing configuration.

## Host test

~~~bash
gcc -std=c11 -Wall -Wextra -Werror -pedantic \
  firmware/ltc3350/ltc3350.c firmware/ltc3350/test_ltc3350.c \
  -o /tmp/test_ltc3350
/tmp/test_ltc3350
~~~

Expected output: LTC3350 driver tests: 5/5 passed.

No CH32V003-specific I²C adapter or on-hardware test has been completed.
