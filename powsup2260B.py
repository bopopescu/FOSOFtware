# Functions to control DC power supply PSW2026B from Keithley or GWINSTEK
# ver 1.0
# 2017-09-27

# To use the power supply one needs to install the USB driver for it from
# https://goo.gl/UTD1j3

import visa

class PS2026B:

    def __init__(self, resource_address, resource_manager):
        self.ps = resource_manager.open_resource(resource_address, read_termination='\n', write_termination='\n')

        self.max_current = self.get_max_current_level()
        self.min_current = self.get_min_current_level()

        self.max_voltage = self.get_max_voltage_level()
        self.min_voltage = self.get_min_voltage_level()

        self.max_OCP_level = self.get_max_OCP_level()
        self.min_OCP_level = self.get_min_OCP_level()

        self.max_OVP_level = self.get_max_OVP_level()
        self.min_OVP_level = self.get_min_OVP_level()

        self.max_rIn = self.get_max_rInOhm()
        self.min_rIn = self.get_min_rInOhm()

        # Set number of bytes read from the device in a single run
        self.ps.chunk_size = 10240 # 10 kB

        self.set_beeper_state("ON")
        self.set_bleeder_state("ON")
        self.set_output_on_delay(0)
        self.set_output_off_delay(0)
        self.set_trip_protection(state=False)
        self.set_output_PON_state(state=False)

    def get_id(self):
        return self.ps.query("*IDN?")

    def set_display_text(self, text=''):
        self.ps.write("DISPlay:WINDow:TEXT:DATA " +"'"+ text + "'")

    def query_display_text(self):
        return self.ps.query("DISPlay:WINDow:TEXT:DATA?")

    def remove_displayed_text(self):
        self.ps.write("DISPlay:WINDow:TEXT:CLEar")

    def clear_protection(self):
        ''' Clears OVP, OCP, OTP protections circuits
        '''
        self.ps.write("OUTPut:PROTection:CLEar")


    def protection_status(self):
        ''' Queries the status of the protection circuits (OVP, OCP, OTP)
        '''
        return self.ps.query("OUTPut:PROTection:TRIPped?")


    def set_output_mode(self, mode):
        ''' Sets the output mode of the power supply

        :mode:  "CVHS" = CV high speed priority
                "CCHS" = CC high speed priority
                "CVLS" = CV slew rate priority
                "CCLS" = CC slew rate priority
        CV = constant voltage
        CC = constant current
        '''
        self.ps.write("OUTPut:MODE " + mode)

    def query_output_mode(self):
        output_mode_dict = {"0":"CVHS", "1":"CCHS", "2":"CVLS", "3":"CCLS"}
        output_mode = self.ps.query("OUTPut:MODE?")
        return output_mode_dict[output_mode]

    def set_beeper_state(self, state="ON"):
        self.ps.write("SYSTem:CONFigure:BEEPer:STATe " + state)

    def query_beeper_state(self):
        beeper_state_dict = {"1":"ON", "0":"OFF"}
        beeper_state = self.ps.query("SYSTem:CONFigure:BEEPer:STATe?")
        return beeper_state_dict[beeper_state]

    def set_bleeder_state(self, state="ON", query=False):
        ''' Sets the state of the bleeder resistor that is connected in parallel with the output terminals of the power supply

        :state: "ON"    = Enabled
                "OFF"   = disabled
                "AUTO"  = The bleeder resistor is turned on when the output is turned off and turned off when the output is disabled.

        The bleeder resistor is needed to dissipate power accumulated in the power supply capacitors after the power is turned off.
        '''
        self.ps.write("SYSTem:CONFigure:BLEeder:STATe " + state)


    def query_bleeder_state(self):
        bleeder_state_dict = {"0":"OFF", "1":"ON", "2":"AUTO"}
        bleeder_state = self.ps.query("SYSTem:CONFigure:BLEeder:STATe?")
        return bleeder_state_dict[bleeder_state]

    def set_output_state(self, state="OFF"):
        ''' Enable or disable output of the power supply
        '''
        self.ps.write("OUTPut:STATe:IMMEdiate " + state)

    def query_output_state(self):
        output_state_dict = {"1":"ON", "0":"OFF"}
        output_state = self.ps.query("OUTPut:STATe:IMMEdiate?")
        return output_state_dict[output_state]

    def measure_current(self):
        ''' Returns measured average current in amps
        '''
        return float(self.ps.query("MEASure:SCALar:CURRent:DC?"))


    def measure_voltage(self):
        ''' Returns measured average voltage in volts
        '''
        return float(self.ps.query("MEASure:SCALar:VOLTage:DC?"))


    def measure_power(self):
        ''' Returns measured average power in watts
        '''
        return float(self.ps.query("MEASure:SCALar:POWer:DC?"))


    def set_output_on_delay(self, delay=0):
        ''' Sets the output ON delay of the power supply

            :delay: float between 0 and 99.99 seconds.
        '''
        self.ps.write("OUTPut:DELay:ON " + str(delay))

    def query_output_on_delay(self):
        return float(self.ps.query("OUTPut:DELay:ON?"))

    def set_output_off_delay(self, delay=0):
        ''' Sets the output OFF delay of the power supply

            :delay: float between 0 and 99.99 seconds.
        '''
        self.ps.write("OUTPut:DELay:OFF " + str(delay))

    def query_output_off_delay(self):
        return float(self.ps.query("OUTPut:DELay:OFF?"))

    def get_max_current_level(self):
        return float(self.ps.query("SOURce:CURRent:LEVel:IMMediate:AMPLitude? MAX"))


    def get_min_current_level(self):
        return float(self.ps.query("SOURce:CURRent:LEVel:IMMediate:AMPLitude? MIN"))


    def set_current_level(self, current=0):
        if current >= self.min_current and current <= self.max_current:
            self.ps.write("SOURce:CURRent:LEVel:IMMediate:AMPLitude " + str(current))
        else:
            print("Current setting is outside the allowed range!")

    def query_current_level(self):
        return float(self.ps.query("SOURce:CURRent:LEVel:IMMediate:AMPLitude?"))


    def get_min_OCP_level(self):
        return float(self.ps.query("SOURce:CURRent:PROTection:LEVel? MIN"))

    def get_max_OCP_level(self):
        return float(self.ps.query("SOURce:CURRent:PROTection:LEVel? MAX"))


    def set_OCP_level(self, level_OCP=0):
        if level_OCP >= self.min_OCP_level and level_OCP <= self.max_OCP_level:
            self.ps.write("SOURce:CURRent:PROTection:LEVel " + str(level_OCP))
        else:
            print("OCP level is outside the allowed range!")

    def query_OCP_level(self):
        return float(self.ps.query("SOURce:CURRent:PROTection:LEVel?"))


    def set_OCP_state(self, state="ON"):
        self.ps.write("SOURce:CURRent:PROTection:STATe " + state)

    def query_OCP_state(self):
        state_OCP_dict = {"0":"OFF", "1":"ON"}
        state_OCP = self.ps.query("SOURce:CURRent:PROTection:STATe?")
        return state_OCP_dict[state_OCP]


    def get_max_voltage_level(self):
        return float(self.ps.query("SOURce:VOLTage:LEVel:IMMediate:AMPLitude? MAX"))

    def get_min_voltage_level(self):
        return float(self.ps.query("SOURce:VOLTage:LEVel:IMMediate:AMPLitude? MIN"))


    def set_voltage_level(self, voltage=0):
        if voltage >= self.min_voltage and voltage <= self.max_voltage:
            self.ps.write("SOURce:VOLTage:LEVel:IMMediate:AMPLitude " + str(voltage))
        else:
            print("Voltage setting is outside the allowed range!")

    def query_voltage_level(self):
        return float(self.ps.query("SOURce:VOLTage:LEVel:IMMediate:AMPLitude?"))


    def get_min_OVP_level(self):
        return float(self.ps.query("SOURce:VOLTage:PROTection:LEVel? MIN"))

    def get_max_OVP_level(self):
        return float(self.ps.query("SOURce:VOLTage:PROTection:LEVel? MAX"))


    def set_OVP_level(self, level_OVP=0):
        if level_OVP >= self.min_OVP_level and level_OVP <= self.max_OVP_level:
            self.ps.write("SOURce:VOLTage:PROTection:LEVel " + str(level_OVP))
        else:
            print("OVP level is outside the allowed range!")

    def query_OVP_level(self):
        return float(self.ps.query("SOURce:VOLTage:PROTection:LEVel?"))


    def get_min_rInOhm(self):
        ''' Returns minimum internal resistance of the power supply in Ohms
        '''
        return float(self.ps.query("SOURce:RESistance:LEVel:IMMediate:AMPLitude? MIN"))

    def get_max_rInOhm(self):
        ''' Returns maximum internal resistance of the power supply in Ohms
        '''
        return float(self.ps.query("SOURce:RESistance:LEVel:IMMediate:AMPLitude? MAX"))


    def set_rIn(self, rInOhm=0):
        ''' Sets internal resistance of the power supply in Ohms
        '''
        if rInOhm >= self.min_rIn and rInOhm <= self.max_rIn:
            self.ps.write("SOURce:RESistance:LEVel:IMMediate:AMPLitude " + str(rInOhm))
        else:
            print("The internal resistance is outside the allowed range!")

    def query_rIn(self):
        return float(self.ps.query("SOURce:RESistance:LEVel:IMMediate:AMPLitude?"))

    def set_trip_protection(self, state=False):
        ''' Set the state (bool) of the power switch if the OCP or OVP is tripped.
        '''
        self.ps.write("SYSTem:CONFigure:BTRip:PROTection " + str(int(state)))

    def query_trip_protection(self):
        return bool(int(self.ps.query("SYSTem:CONFigure:BTRip:PROTection?")))

    def set_output_PON_state(self, state=False):
        ''' Sets (with bool) if the unit will have its output ON or OFF at power-up.
        '''
        self.ps.write("SYSTem:CONFigure:OUTPut:PON:STATe " + str(int(state)))

    def query_output_PON_state(self):
        return bool(int(self.ps.query("SYSTem:CONFigure:OUTPut:PON:STATe?")))

    def get_error(self):
        """Receive last error in the error queue of the instrument

        """
        return self.ps.query("SYSTem:ERRor?")

    def close(self):
        self.ps.close()
        print("")
#%%
#rm = visa.ResourceManager()
#rm.list_resources()
#ps = PS2026B("COM3", rm)
#%%
#print(ps.get_id())
#print(ps.query_beeper_state())
#print(ps.query_bleeder_state())
#print(ps.query_output_on_delay())
#print(ps.query_output_off_delay))
#print(ps.query_OCP_level())
#print(ps.query_OCP_state())
#print(ps.query_rIn())
#print(ps.query_OVP_level())
#%%
#ps.set_output_mode("CVHS")
#ps.query_output_mode()
#%%
#ps.set_output_state("OFF")
#%%
#ps.query_trip_protection()
#ps.get_error()
#%%
#print(ps.query_output_PON_state())
#ps.close()
