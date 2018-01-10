import binascii, struct, array, os
import numpy as np

def txt_to_bin(text, encoding='utf-8', errors='surrogatepass'):
    bits = bin(int(binascii.hexlify(text.encode(encoding, errors)), 16))[2:]
    return bits.zfill(8 * ((len(bits) + 7) // 8))

def bin_to_txt(bits, encoding='utf-8', errors='surrogatepass'):
    n = int(bits, 2)
    return int2bytes(n).decode(encoding, errors)

def int2bytes(i):
    hex_string = '%x' % i
    n = len(hex_string)
    return binascii.unhexlify(hex_string.zfill(n + (n & 1)))

def binary(num):
    return ''.join(bin(ord(c)).replace('0b', '').rjust(8, '0') \
                   for c in struct.pack('!f', num))


def bin_digiw(valz, filename):
    ''' This function converts a list of values from the digitizer into 2-byte
    binary strings to write to a file.
    Input:
    1) vals = list of integer values (i.e. [-14382, -13291, ..., -25693])
    in the range of -32767 to +32767 (15 bits + 1 sign bit)
    2) filename = path to file output
    Output: an array containing all the binary values for these integers broken
    up into bytes.
    Other functions: this function also writes the binary array to a file before
    returning it. The returned array does not have to be stored. It's just
    returned in case we need it one day.
    '''

    # Create the empty binary array and populate with integers
    binary_array = array.array('B')
    binary_array = np.frombuffer(valz, dtype = np.dtype('i2'))

    # Open the file in binary write mode and write
    f = file(filename, 'w+b')
    binary_array.tofile(f)
    f.close()

    return binary_array

def bin_digir(filename):
    ''' This function reads in a file of binary numbers written by bin_digiw
    (above) and converts them to integers readable by Python.

    Input:
    1) filename = path to desired file
    Output: an array containing all the integer values for these bytes
    corresponding to output from digitizer. These can be converted into voltages
    if the range of the digitizer is known.
    '''

    f = file(filename, 'rb')

    # Read in byte by byte
    binary_array = np.fromfile(f, dtype = np.dtype('i2'))
    f.close()
    
    return binary_array
