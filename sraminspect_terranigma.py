#!/bin/python3

"""
Terranigma SRAM format, high-level:

+    0                          1000
0    _______________________________________________________
     | Slack                                               |
100  |_____________________________________________________|
     | Slot 1                   | Mirrored slot 1          |
5FA  |_____________________________________________________|
     | Checksum slot 1          | Mirrored checksum slot 1 |
5FE  |_____________________________________________________|
     | Slack                                               |
600  |_____________________________________________________|
     | Slot 2                   | Mirrored slot 2          |
AFA  |_____________________________________________________|
     | Checksum slot 2          | Mirrored checksum slot 2 |
AFE  |_____________________________________________________|
     | Slack                                               |
B00  |_____________________________________________________|
     | Slot 3                   | Mirrored slot 3          |
FFA  |_____________________________________________________|
     | Checksum slot 3          | Mirrored checksum slot 3 |
FFE  |_____________________________________________________|
     | ???                                                 |
     |_____________________________________________________|

Terranigma is a HiROM game, so the SRAM is mapped to $30:6000 in RAM.

The game always saves the savegame data to both the normal "active" slot,
and a hidden "mirrored" slot.

For each active slot, the file select screen checks if the checksums matches
its content. If it does, the slot, including its checksum, is copied over
their mirrored counterparts. If it does not, the coresponding mirrored slot
and checksum are copied over their active counterparts. If the checksum of the
mirrored slot does not match as well, the game regards the data contained in
the slot as broken and will behave as if the slot were blank.
"""

import collections
import os
import sys

ENDIANNESS = 'little'
SRM_SIZE = 0x2000
MIRR_COUNT = 0x2
MIRR_SLACK = 0x100
MIRR_OFFSET = 0x1000
SLOT_COUNT = 0x3
SLOT_OFFSET = 0x500
SLOT_SIZE = 0x4F9
CHKSUM_IV = 0x5236
CHKSUM_SIZE = 0x4
OUT_FNAME_FMT = "{}.changed.srm"

CHAR_LUT = {
    0x20: ' ',
    0x21: 'A',
    0x22: 'B',
    0x23: 'C',
    0x24: 'D',
    0x25: 'E',
    0x26: 'F',
    0x27: 'G',
    0x28: 'H',
    0x29: 'I',
    0x2A: 'J',
    0x2B: 'K',
    0x2C: 'L',
    0x2D: 'M',
    0x2E: 'N',
    0x2F: 'O',
    0x30: 'P',
    0x31: 'Q',
    0x32: 'R',
    0x33: 'S',
    0x34: 'T',
    0x35: 'U',
    0x36: 'V',
    0x37: 'W',
    0x38: 'X',
    0x39: 'Y',
    0x3A: 'Z',  # 0x3B..0x40 ?
    0x41: 'a',
    0x42: 'b',
    0x43: 'c',
    0x44: 'd',
    0x45: 'e',
    0x46: 'f',
    0x47: 'g',
    0x48: 'h',
    0x49: 'i',
    0x4A: 'j',
    0x4B: 'k',
    0x4C: 'l',
    0x4D: 'm',
    0x4E: 'n',
    0x4F: 'o',
    0x50: 'p',
    0x51: 'q',
    0x52: 'r',
    0x53: 's',
    0x54: 't',
    0x55: 'u',
    0x56: 'v',
    0x57: 'w',
    0x58: 'x',
    0x59: 'y',
    0x5A: 'z',
}
CHAR_LUT_REV = dict(zip(CHAR_LUT.values(), CHAR_LUT.keys()))


def terra_atob(a):
    return CHAR_LUT_REV.get(a, 0x20)


def terra_stob(s):
    return (bytes(terra_atob(x) for x in s[0:5]) + b'\xD4').ljust(6, b'\x00')


def terra_btos(b):
    end = None
    try:
        end = b.index(0xD4)
    except ValueError:
        pass
    if end is None:
        return ''

    # If the default name ("Ark") is not changed when creating a new savegame,
    # the game additionally puts a 0xD1 before the terminating 0xD4,
    # which is not a visible character in-game.
    tmp = b[0:end].rstrip(b'\xD1')
    return ''.join(CHAR_LUT.get(x, '?') for x in tmp)


SLOT_VARS = collections.OrderedDict([
    ("player_name", (0x10, 0x6, terra_btos, terra_stob)),
    ("player_name_alt", (0x1C, 0x6, terra_btos, terra_stob)),
])


def slot_offset(mirror, slot):
    return MIRR_OFFSET * mirror + MIRR_SLACK + SLOT_OFFSET * slot


def calc_checksum(data, mirror, slot):
    chksum1 = chksum2 = CHKSUM_IV
    word = 0

    cur_addr = addr_orig = slot_offset(mirror, slot)

    while True:
        if cur_addr - addr_orig > SLOT_SIZE:
            break

        word = int.from_bytes(data[cur_addr:cur_addr + 2], ENDIANNESS)

        chksum1 = (word + chksum1) % 0x10000
        chksum2 ^= word

        cur_addr += 2

    return bytes(chksum1.to_bytes(2, ENDIANNESS) +
                 chksum2.to_bytes(2, ENDIANNESS))


def read_checksum(data, mirror, slot):
    offset = slot_offset(mirror, slot) + SLOT_SIZE + 1
    return data[offset:offset + CHKSUM_SIZE]


def write_checksum(data, mirror, slot, new_checksum):
    offset = slot_offset(mirror, slot) + SLOT_SIZE + 1
    data[offset:offset + CHKSUM_SIZE] = new_checksum
    return data


def read_slot(data, mirror, slot):
    values = {}
    offset = slot_offset(mirror, slot)

    for key, val in SLOT_VARS.items():
        values[key] = val[2](data[offset + val[0]:offset + val[0] + val[1]])

    return values


def update_slot(data, update_dict, mirror, slot):
    offset = slot_offset(mirror, slot)

    for key, val in update_dict.items():
        update_start = offset + SLOT_VARS[key][0]
        update_end = update_start + SLOT_VARS[key][1]
        data[update_start:update_end] = SLOT_VARS[key][3](val)

    return data


def slot_is_uninitialized(data, mirror, slot):
    offset = slot_offset(mirror, slot)
    test_words = data[offset:offset + 4]
    return test_words[2:4] != b'\x01\x00' and test_words[0:2] == test_words[2:4]


def read_sram_meta(data):
    sram_meta = {}

    for mirror_idx in range(MIRR_COUNT):
        for slot_idx in range(SLOT_COUNT):
            if slot_is_uninitialized(data, mirror_idx, slot_idx):
                sram_meta[(mirror_idx, slot_idx)] = None
                continue

            _read_checksum = read_checksum(data, mirror_idx, slot_idx)
            _calc_checksum = calc_checksum(data, mirror_idx, slot_idx)
            sram_meta[(mirror_idx, slot_idx)] = (
                _read_checksum,
                _calc_checksum,
                read_slot(data, mirror_idx, slot_idx)[
                    "player_name"] if _read_checksum == _calc_checksum else None
            )

    return sram_meta


def display_sram_meta(sram_meta):
    print("/".ljust(8), end="")
    for slot_idx in range(SLOT_COUNT):
        print("Slot {}".format(slot_idx + 1).ljust(18), end="")
    print()
    for mirror_idx in range(MIRR_COUNT):
        print(("active" if mirror_idx == 0 else "mirror").ljust(8), end="")
        for slot_idx in range(SLOT_COUNT):
            slot_meta = sram_meta[(mirror_idx, slot_idx)]
            if slot_meta is None:
                print("(uninitialized)".ljust(18), end="")
            else:
                print(
                    "'{}' ({})".format(
                        '' if slot_meta[2] is None else slot_meta[2],
                        "damaged" if slot_meta[2] is None else "ok").ljust(18),
                    end="")
        print()
    print()


def ask_slot_to_change(sram_meta):
    while True:
        slot_to_change = input(
            "Please provide the savegame number to change (1-3): ")
        try:
            slot_to_change = int(slot_to_change) - 1
        except ValueError:
            print("Invalid value. Please provide an integer.")
            continue

        if slot_to_change not in range(SLOT_COUNT):
            print("Invalid savegame number.")
            continue

        if sram_meta[(0, slot_to_change)] is None:
            print("Chosen slot is uninitialized and therefore cannot be used.")
            continue

        # Determine which physical slot to change.
        # Rationale: see the SRAM layout described at the top of this file.
        mirror_to_change = 0
        if sram_meta[(mirror_to_change, slot_to_change)][2] is None:
            if sram_meta[(1, slot_to_change)][2] is None:
                print("Chosen slot is damaged and therefore cannot be used.")
                continue

            mirror_to_change = 1
        break

    return mirror_to_change, slot_to_change


def ask_vars_to_change(data, mirror_to_change, slot_to_change):
    vars_to_change = {}
    slot_values = read_slot(data, mirror_to_change, slot_to_change)
    print("Changeable variables:")
    for i, key in enumerate(SLOT_VARS):
        print("{}: '{}',".format(i, key).ljust(30) +
              " current value: '{}'".format(slot_values[key]))

    while True:
        while True:
            var_to_change = input("Please provide the number of the variable to change "
                                  "(hit just enter if no more variables should be changed): ")
            if not var_to_change:
                var_to_change = -1

            try:
                var_to_change = int(var_to_change)
            except ValueError:
                print("Invalid value. Please provide an integer.")
                continue

            if -1 <= var_to_change <= len(SLOT_VARS):
                break

            print("This variable does not exist.")

        if var_to_change == -1:
            break

        var_name_to_change = list(SLOT_VARS.keys())[var_to_change]
        new_value = input("Please provide the new value: ")
        vars_to_change[var_name_to_change] = new_value

    return vars_to_change


def main():
    data = None

    if len(sys.argv) < 2 or not os.path.isfile(
            sys.argv[1]) or os.path.getsize(sys.argv[1]) != SRM_SIZE:
        print(
            "Please provide a Terranigma .srm file as an argument.",
            file=sys.stderr)
        sys.exit(1)

    try:
        with open(sys.argv[1], 'rb') as f:
            data = bytearray(f.read())
    except OSError as err:
        print("Could not open '{}': {}".format(sys.argv[1], err))
        return

    sram_meta = read_sram_meta(data)
    display_sram_meta(sram_meta)
    mirror_to_change, slot_to_change = ask_slot_to_change(sram_meta)
    vars_to_change = ask_vars_to_change(data, mirror_to_change, slot_to_change)

    if not vars_to_change:
        print("No variables changed, nothing to do.")
        return

    out_fname = OUT_FNAME_FMT.format(
        os.path.basename(
            sys.argv[1].rstrip(".srm")))
    out_dir = os.path.dirname(os.path.abspath(sys.argv[1]))
    out_path = os.path.join(out_dir, out_fname)
    user_ok = input(
        "OK and write new .srm file to {}? (y/n) ".format(out_path))
    user_ok = user_ok.lower().startswith('y')
    if not user_ok:
        return

    print("Updating savegame data...")
    data = update_slot(data, vars_to_change, mirror_to_change, slot_to_change)

    print("Updating checksum...")
    new_checksum = calc_checksum(data, mirror_to_change, slot_to_change)
    data = write_checksum(data, mirror_to_change, slot_to_change, new_checksum)

    print("Writing file...")
    try_again = True
    while try_again:
        try:
            with open(out_path, 'xb') as f:
                f.write(data)
        except OSError as err:
            print("Could not write the file '{}': {}".format(out_path, err))
            try_again = input("Try again? (y/n) ").lower().startswith('y')
        else:
            print("File written to '{}'.".format(out_fname))
            try_again = False


if __name__ == "__main__":
    main()
