# v 0.1
import sys, copy
sys.path.insert(0,r'C:\\Google Drive\\code\\')
#sys.path.append(r'\\LAMBSHIFT-PC\Google Drive\code\instrument control')
import numpy as np
import u3, u6
import LabJackPython
import visa
import powsup2260B
import time

#%%
class Travisty(Exception):
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        return repr(self.msg)
#%%
# Over current protection = current limit for the coils' power supplies
OCP_setting = 30 #[A]

# Over voltage protection = voltage limit for the coils' power supplies
OVP_setting = 15 #[V]

# Maximum allowed current flowing through the coils. Magnetic fields requiring larger current than this will not be set.
max_current = 25 #[A]

# Our choice of axes x,y, and z is such that the offset B field (Earth's B field) has negative components along each one of these axes.
# "Offset B field [G]" is the parameter specifying offset magnetic field that needs to be cancelled out along the given direction. This offset B field is the result of the Earth's magnetic field + presence of magnetic materials around the experiment. This number can be both positive and negative.
# "Offset current [A]" is the parameter defining the current needed to cancel out the external magnetic field (Earth's B field) in the given direction, assuming that the coils are in "Positive" configuration (explained below)
# "Coil configuration" parameter stands for direction in which the given coil is applying the field. If, for instance, the coil applied the field along the x-axis, then, depending on which wire end of the coil is connected to the positive terminal of the power supply, the magnetic field will be generated collinear to the x-axis = Positive or in the opposite direction = Negative. This will obviously limit the range of magnetic fields that can be generated along the given axis, since the power supplies cannot apply negative current. However, this limitation is mitigated by usage of electromechanial array (2 x SPDT switches) that reverses the current direction flowing through a given set of coils.

# Offset B field components along the experiment axes [Gauss]. These have been determined from the known B field conversion factors [G/A] of the coils and also from measuring at what current from the given set of coils the respective magnetic field component was as close to zero as possible, considering the resolution of the respective power supply.
offset_B_field_dictionary = {'x': -0.03186, 'y': -0.308632}

# Current components of the net B field in the experiment. The coils are located in such a way that between the waveguides the net field has components given by this dictionary.
total_B_field_dictionary = copy.deepcopy(offset_B_field_dictionary)

# Dictionary of axes and corresponding sets of coils.
# 'Main coils' = set of coils that is used to generate required B field component.
# 'Auxiliary coils' = if present then used to cancel out the offset B field and also to provide additional B field scan range, when the current limit for 'Main coils' is exceeded.
B_field_component_dictionary = {
    'x': {
        'Main coils': 'Middle side coils',
        'Auxiliary coils':'NA'},
    'y': {
        'Main coils': 'Top and Bottom auxiliary coils',
        'Auxiliary coils':'Top and Bottom coils'}
    }

# "B field conversion factor [G/A]":experimentally verified magnetic field to current conversion factor. It tells us what magnetic field we generate by the given coil for set current flowing through the coil. Positive number means that the coil is wired in such a way that it generates positive B field along the given axis and vice versa.
# "Generated B field [G]": B field that gets generated by the respective coil.
# B field conversion factor [G/A]": the sign of this coefficient is given in such a way that if the current reversing switch is present then it had not been engaged. If the sign is positive, then when the switch is not engaged then the current flowing through the coils produces positive field along the given axis and vice versa.
coils_settings_dictionary = {
    'Middle side coils':
        {'Power supply COM port': 59,
        'Maximum allowed current [A]': max_current,
        "B field conversion factor [G/A]": 0.0531,
        "Generated B field [G]": 0,
        "Current flowing [A]": 0,
        "Current reversing switch present?": True,
        "LabJack relay control FIO channel": 6},

    'Top and Bottom coils':
        {'Power supply COM port': 60,
        'Maximum allowed current [A]': max_current,
        "Generated B field [G]": 0,
        "Current flowing [A]": 0,
        "Current reversing switch present?": False, # no switch is installed
        "B field conversion factor [G/A]": 0.0892,
        "LabJack relay control FIO channel": "NA"},

    # These coils have no offset current, because the external B field along y-axis has been cancelled by the Top and Bottom coils.
    'Top and Bottom auxiliary coils':
        {'Power supply COM port': 61,
        'Maximum allowed current [A]': max_current,
        "Generated B field [G]": 0,
        "Current flowing [A]": 0,
        "Current reversing switch present?": True,
        "B field conversion factor [G/A]": -0.0895,
        "LabJack relay control FIO channel": 5}
                     }

# This is to store the initial configuration - to bring the relay to its initial state at the end of the program use.
coils_settings_dictionary_initial = coils_settings_dictionary

# %%
class BFieldControl():
    def __init__(self, rm):
        self.total_B_field_dictionary = copy.deepcopy(total_B_field_dictionary)
        self.coils_settings_dictionary = copy.deepcopy(coils_settings_dictionary)
        self.max_generated_B_field_dictionary = {'x': self.get_B_field_range('x'), 'y': self.get_B_field_range('y')}


        # Power supplies for the B field generating coils
        self.middle_side_coils_supply_com_port = "COM"+str(self.coils_settings_dictionary['Middle side coils']['Power supply COM port'])

        self.middle_side_coils_supply = powsup2260B.PS2026B(self.middle_side_coils_supply_com_port, rm)

        self.top_bottom_coils_supply_com_port = "COM"+str(self.coils_settings_dictionary['Top and Bottom coils']['Power supply COM port'])

        self.top_bottom_coils_supply = powsup2260B.PS2026B(self.top_bottom_coils_supply_com_port, rm)

        self.top_bottom_aux_coils_supply_com_port = "COM"+str(self.coils_settings_dictionary['Top and Bottom auxiliary coils']['Power supply COM port'])

        self.top_bottom_aux_coils_supply = powsup2260B.PS2026B(self.top_bottom_aux_coils_supply_com_port, rm)

        # Dictionary containing the handles to the power supplies for the coils
        self.coils_power_supply_dictionary = {
                            'Middle side coils': self.middle_side_coils_supply,
                            'Top and Bottom coils': self.top_bottom_coils_supply,
                            'Top and Bottom auxiliary coils': self.top_bottom_aux_coils_supply
                            }

        # Labjack for controlling the relays
        self.u6_relay_handle = u6.U6(autoOpen = False)
        self.u6_relay_handle.open(serial = 360012014)

        print('Labjack for current switching relays:'),
        print(self.u6_relay_handle)

        # Initialize the power supplies
        for key, ps_handle in self.coils_power_supply_dictionary.iteritems():
            max_allowed_current = self.coils_settings_dictionary[key]['Maximum allowed current [A]']
            id_read = ps_handle.get_id()

            ps_handle.set_OCP_level(OCP_setting)
            ps_handle.set_OVP_level(OVP_setting)
            ps_handle.set_OCP_state("ON")

            OCP_read = ps_handle.query_OCP_level()
            OVP_read = ps_handle.query_OVP_level()

            # Bleeder resistor is necessary to handle the possible reverse current going into the power supply.
            bleeder_state_read = ps_handle.query_bleeder_state()

            ps_handle.set_output_mode("CCHS")

            # Check if the power supply is set to output too high of a current. Also check if the power supply output is ON or OFF. If it is OFF then apply the current in a gradual manner.

            current_level_to_output = ps_handle.query_current_level()
            print(current_level_to_output)
            if current_level_to_output > max_allowed_current:
                raise Travisty("WARNING!!! Power supply is set to output more than the maximum allowed current!")
            else:
                if ps_handle.query_output_state() == "OFF":
                    ps_handle.set_current_level(0)
                    ps_handle.set_output_state("ON")
                    self.apply_current(ps_handle, current_level_to_output)

            print(key + " power supply: " + id_read + "\nOCP [A]: " + str(OCP_read) + "\nOVP [V]: " + str(OVP_read) + "\nBleeder resistor state: " + str(bleeder_state_read))

        self.update_total_B_field()

        # Cancel Earth's B field
        self.set_B_field(0, "y")
        self.set_B_field(0, "x")


    def get_coils_parameters_for_B_field(self, B_field_value, axis):
        '''
        For calculating current needed to be supplied by the power supply to generate given magnetic field value along a given axis, as well as whether the current reversal is required.

        It is assumed that the Auxiliary coils are used to cancel out the offset B field, whereas Main coils are used to apply the required external B field. If there are no Auxiliary coils then Main coils are used for both the offset field cancellation and net B field setting. One can consider that if we reach the current limit on one power supply, for example, for y-axis ("Main coils"), then we can engage another set of coils ("Auxiliary coils") to get to higher field. Since we always want to be able to set the B field to both positive and negative values, each set of coils needs to have the current reversing switch. For this method we assume that the generated B field by the Main coils is the maximum field that is allowed by the current level limit that can flow through the Main coils. One could think of seemingly better way of doing that: to supply current by both coils in such a way that the total heat loss produced by both coils is minimized. This method could be used even when we are not exceeding the current limit for the Main coils. This sounds good, however the danger is that two coils do not have the same B field gradient as a function of axial distance along the experiment axis inside the waveguides. Thus even though we will be producing the right field between the waveguides, the fractional gradient of the field at that point will not necessarily be exactly the same, the net B field and its gradient at other points will also not be the same as compared to when we apply the field only by Main coils.

        After some thought, I decided that it is not a good idea to use Auxiliary coils as the additional B field booster when the first method for setting the current on the coils is used: one needs to keep track of whether the current limit for given axis had been reached before, so that the Auxiliary coils had to get enabled and then make sure that the Auxiliary field gets turned off whenever the Main coils can supply enough current to generate the required field on its own. Thus I think that the heat loss minimization method is much better, becuase no checks like that are required, but for this I need to be sure that the different B field fractional gradients due to these coils will not introduce any significant systematics into the experiment.

        :B_filed_value: is in Gauss - can be positive, negative or zero
        :axis: "x" or "y"

        '''

        # Dictionary to store the output parameters for the coils
        # "Change in B field [G]": change in B field generated by the coils compared to the previous generated B field value
        coils_settings_needed_dictionary = {
            "Main coils": {
            "Current [A]": 0,
            "Current reversal required?": False,
            "Generated B field [G]": 0,
            "Change in B field [G]": 0}}

        main_coils_settings = self.coils_settings_dictionary[B_field_component_dictionary[axis]["Main coils"]]
        main_coils_generated_B_field = main_coils_settings["Generated B field [G]"]

        total_B_field_component = self.total_B_field_dictionary[axis]


        B_to_current_conversion_factor_main_coils = main_coils_settings["B field conversion factor [G/A]"]

        if not(B_field_value == 0 and B_field_component_dictionary[axis]['Auxiliary coils'] != 'NA'):

            # Required B field needed to be generated by the coils in order to have the needed net B field in the experiment region.
            # To calculate this needed B field we use the expression that if
            # B2 = the net B field that we need to have in the experiment,
            # B1 = the net B field that we currently have,
            # B1C1 and B1C2 = fields generated by Main and Auxiliary coils respectively,
            # B2C1 and B2C2 = fields that are needed to be generated by the coil to have B2 field,
            # B0 = offset B field,
            # B1 = B1C1 + B1C2 + B0, B2 = B2C1 + B2C2 + B0,
            # then B2-B1 = (B2C1-B1C1) + (B2C2-B1C2). We assume that we want all of the additional needed B field to be generated by the Main coils, thus B2C2=B1C2. This gives us that B2C1 = B2-B1 + B1C1.

            B_field_to_generate_main_coils = (B_field_value-total_B_field_component) + main_coils_generated_B_field


            coils_settings_needed_dictionary["Main coils"]["Generated B field [G]"] = B_field_to_generate_main_coils

            coils_settings_needed_dictionary["Main coils"]["Change in B field [G]"] = B_field_to_generate_main_coils - main_coils_generated_B_field

            # Current that needs to flow through the "Main coils" in order to generate the required B field in the experiment region.
            current_needed_main_coils = B_field_to_generate_main_coils/B_to_current_conversion_factor_main_coils

            # When the Auxiliary coils are present and the required net B field component is zero, then we want to use Auxiliary coils to cancel out the external offset field.

            # The current needed has to be positive. If we obtain negative number, then we need to reverse the current flowing through the coils. Thus we need to engage the current reversing switch. This is also equivalent to changing the sign of the current-to-B field conversion factor.

            if current_needed_main_coils < 0:
                print("Main coils current needed is negative. Current reversal is required.")
                coils_settings_needed_dictionary["Main coils"]["Current reversal required?"] = True
                B_to_current_conversion_factor_main_coils = -1 * B_to_current_conversion_factor_main_coils
                current_needed_main_coils = -1 * current_needed_main_coils
            else:
                print("Main coils current needed is positive. Current reversal is not required")

            coils_settings_needed_dictionary["Main coils"]["Current [A]"] = current_needed_main_coils

            # Checking if the required current is larger than the maximum allowed current flowing through the Main coils

            if current_needed_main_coils > main_coils_settings['Maximum allowed current [A]']:
                raise Travisty("WARNING!!! Required current (" + str(current_needed_main_coils) + " A) exceeds the maximum allowed current for this set of coils.")
        else:
            print("The requested B field is zero. It is assumed that the external offset field is getting cancelled out by Auxiliary coils.")
            # We do not want to have any current from the Main coils for cancellation of the offset B field, if the Auxiliary coils are present
            current_needed_main_coils = 0

            # We also want to make sure that the sign of the current-to-B field conversion factor is the same as it was in the beginning of the class instance creation = i.e., in the state when the current reversing switch had not been engaged.
            if B_to_current_conversion_factor_main_coils != coils_settings_dictionary_initial[B_field_component_dictionary[axis]["Main coils"]]["B field conversion factor [G/A]"]:
                coils_settings_needed_dictionary["Main coils"]["Current reversal required?"] = True

            coils_settings_needed_dictionary["Auxiliary coils"] = {"Current [A]": 0, "Current reversal required?": False}

            auxiliary_coils_settings = self.coils_settings_dictionary[B_field_component_dictionary[axis]["Auxiliary coils"]]

            auxiliary_coils_generated_B_field = auxiliary_coils_settings["Generated B field [G]"]

            # B2-B1 = (B2C1-B1C1) + (B2C2-B1C2), thus
            # B2C2 = B2-B1 - (B2C1-B1C1) + B1C2, where B2C1 = 0 that needs to be generated by the Main coils.
            B_field_to_generate_auxiliary_coils = (B_field_value-total_B_field_component) - (current_needed_main_coils-main_coils_generated_B_field) + auxiliary_coils_generated_B_field

            coils_settings_needed_dictionary["Auxiliary coils"]["Generated B field [G]"] = B_field_to_generate_auxiliary_coils

            coils_settings_needed_dictionary["Auxiliary coils"]["Change in B field [G]"] = B_field_to_generate_auxiliary_coils - auxiliary_coils_generated_B_field

            B_to_current_conversion_factor_auxiliary_coils = auxiliary_coils_settings["B field conversion factor [G/A]"]

            # Current that needs to flow through the Auxiliary coils in order to generate the required B field in the experiment region.
            current_needed_auxiliary_coils = B_field_to_generate_auxiliary_coils/B_to_current_conversion_factor_auxiliary_coils

            if current_needed_auxiliary_coils < 0:
                print("Auxiliary coils current needed is negative. Current reversal is required.")
                coils_settings_needed_dictionary["Auxiliary coils"]["Current reversal required?"] = True
                B_to_current_conversion_factor_auxiliary_coils = -1 * B_to_current_conversion_factor_auxiliary_coils
                current_needed_auxiliary_coils = -1 * current_needed_auxiliary_coils
            else:
                print("Auxiliary coils current needed is positive. Current reversal is not required")

            coils_settings_needed_dictionary["Main coils"]["Generated B field [G]"] = 0
            coils_settings_needed_dictionary["Main coils"]["Change in B field [G]"] = 0 - main_coils_generated_B_field
            coils_settings_needed_dictionary["Main coils"]["Current [A]"] = current_needed_main_coils
            coils_settings_needed_dictionary["Auxiliary coils"]["Current [A]"] = current_needed_auxiliary_coils

            if current_needed_auxiliary_coils > auxiliary_coils_settings['Maximum allowed current [A]']:
                raise Travisty("WARNING!!! Required current (" + str(current_needed_auxiliary_coils) + " A) exceeds the maximum allowed current for this set of coils.")

        return coils_settings_needed_dictionary

    def apply_current(self, powsup_handle, current):
        '''
        Apply current to power supply in a somewhat continuous way by slowly changing the current in 2A steps with 0.25s in between from the initial current to the final current. This is done to protect the power supply from possible reverse current due to inductive load. This is especially important if the bleeder resistor is disabled.

        :powsup_handle: handle to the power supply
        :current: current in amperes
        '''
        current_read = powsup_handle.measure_current()
        num_steps = int(abs(current-current_read))/2+2
        current_rn = np.linspace(start = current_read, stop = current, num = num_steps)
        for current_set in current_rn:
            powsup_handle.set_current_level(current_set)
            time.sleep(0.25)

    def reverse_current_direction(self, axis, coils_type):
        '''
        Reverses the current direction

        :axis: "x" or "y"
        :coils_type: "Main coils" or "Auxiliary coils"
        '''

        coils_settings = self.coils_settings_dictionary[B_field_component_dictionary[axis][coils_type]]
        coil_power_supply_relay_fio_pin = coils_settings["LabJack relay control FIO channel"]
        print(coil_power_supply_relay_fio_pin)

        # To switch the direction we need to apply digital pulse to the relay
        # Set the output to HIGH
        self.u6_relay_handle.getFeedback(u6.BitStateWrite(coil_power_supply_relay_fio_pin,1))
        time.sleep(0.1)
        #Set the output to LOW
        self.u6_relay_handle.getFeedback(u6.BitStateWrite(coil_power_supply_relay_fio_pin,0))

        coils_settings["B field conversion factor [G/A]"] = -1*coils_settings["B field conversion factor [G/A]"]
        self.coils_settings_dictionary[B_field_component_dictionary[axis][coils_type]] = coils_settings


    def set_B_field(self, B_field_value, axis):
        '''
        Applies the required magnetic field along the specified direction. This code takes care of current switching, if needed. The total field in the experiment region gets updated as well.

        :B_field_value: B field value [Gauss] to apply. Can be positive or negative
        :axis: "x" or "y"
        '''

        coils_parameters_for_B_field_dictionary = self.get_coils_parameters_for_B_field(B_field_value, axis)
        for coils_type, coils_params in coils_parameters_for_B_field_dictionary.iteritems():
            coils_name = B_field_component_dictionary[axis][coils_type]
            power_supply_to_use = self.coils_power_supply_dictionary[coils_name]
            current_needed = coils_params["Current [A]"]
            if coils_params["Current reversal required?"] == True:
                # Before switching the current direction the current through the coils is set to 0 to eliminate inductive kick.
                self.apply_current(power_supply_to_use, 0)
                self.reverse_current_direction(axis, coils_type)
                time.sleep(0.5)

            self.apply_current(power_supply_to_use, current_needed)
            self.coils_settings_dictionary[coils_name]["Generated B field [G]"] = coils_params["Generated B field [G]"]

            # Update the value for the total magnetic field between the waveguides
            self.total_B_field_dictionary[axis] = self.total_B_field_dictionary[axis] + coils_params["Change in B field [G]"]

    def get_B_field_range(self, axis):
        '''
        Gives ABSOLUTE value of the maximum B field that can be generated by Main coils and Auxiliary coils (if present) along the given axis.

        :axis: "x" or "y"
        '''
        coils_B_field_max_dictionary = {}
        for coils_type, coils_name in B_field_component_dictionary[axis].iteritems():
            if coils_name != "NA":
                coils_B_field_conversion_factor =  abs(self.coils_settings_dictionary[coils_name]["B field conversion factor [G/A]"])
                coils_B_field_max_value = self.coils_settings_dictionary[coils_name]['Maximum allowed current [A]']*coils_B_field_conversion_factor
            else:
                coils_B_field_max_value = "NA"

            coils_B_field_max_dictionary[coils_type] = coils_B_field_max_value
        return coils_B_field_max_dictionary

    def update_total_B_field(self):
        '''
        Updates the total_B_field_dictionary by measuring current flowing through the coils.

        It is assumed that the sign of the B field conversion factor for the respective coils is correct.
        '''
        total_B_field_updated_dictionary = copy.deepcopy(offset_B_field_dictionary)
        for axis, value in self.total_B_field_dictionary.iteritems():
            for coils_type, coils_name in B_field_component_dictionary[axis].iteritems():
                if coils_name != "NA":
                    coils_settings = self.coils_settings_dictionary[coils_name]
                    coils_B_field_conversion_factor = coils_settings["B field conversion factor [G/A]"]
                    pow_supply_handle = self.coils_power_supply_dictionary[coils_name]

                    current_measured = pow_supply_handle.measure_current()
                    coils_settings["Current flowing [A]"] = current_measured
                    coils_generated_B_field = coils_B_field_conversion_factor * current_measured
                    coils_settings["Generated B field [G]"] = coils_generated_B_field
                    total_B_field_updated_dictionary[axis] = total_B_field_updated_dictionary[axis] + coils_settings["Generated B field [G]"]

        self.total_B_field_dictionary = copy.deepcopy(total_B_field_updated_dictionary)

    def get_total_B_field(self):
        '''
        Returns the total B field (in Gauss) that is at the point between the waveguides
        '''
        # We return the deep copy of the dictionary to prevent the user unintentionally changing the self. dictionary
        return copy.deepcopy(self.total_B_field_dictionary)

    def close(self):
        ''' Closes all connections to power supplies and the LabJack and ensures
        that the relays are all set to their default position since there is
        no way to check.
        '''

        self.set_B_field(0.0,"x")
        self.set_B_field(0.0,"y")

        for ps in self.coils_power_supply_dictionary.keys():
            self.coils_power_supply_dictionary[ps].close()
            print(ps + " closed.")

        self.u6_relay_handle.close()
        LabJackPython.Close()
        print("U6 closed.")

if __name__ == "__main__":
    rm = visa.ResourceManager()
    b_field_control = BFieldControl(rm)
    tot=b_field_control.get_total_B_field()
    print(tot)
    b_field_control.set_B_field(0.2, "x")
    b_field_control.set_B_field(0.2, "y")
    print(b_field_control.total_B_field_dictionary)
    print(b_field_control.coils_settings_dictionary)
