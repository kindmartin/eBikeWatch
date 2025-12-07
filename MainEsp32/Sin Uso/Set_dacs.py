import accel_dac_tools as dac, HW
i2c = HW.make_i2c()
code0 = dac.dac_read_code(i2c, dac.DAC0_ADDR)
code1 = dac.dac_read_code(i2c, dac.DAC1_ADDR)
print(code0, code1, dac.dac_read_volts(i2c, dac.DAC0_ADDR), dac.dac_read_volts(i2c, dac.DAC1_ADDR))


import accel_dac_tools as dac

# Throttle (DAC0) to 1.80 V, Brake (DAC1) to 0.90 V
dac.write_volts(1.80, addr=dac.DAC0_ADDR)  # throttle
dac.write_volts(0.90, addr=dac.DAC1_ADDR)  # brake

# Or in one shot:
dac.set_both_volts(1.50, 1.30)