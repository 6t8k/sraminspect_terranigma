sraminspect\_terranigma
======================

This is a Python script that lets you modify variables inside SNES game "Terranigma"'s SRAM, where the savegame data is stored.

It works with every PAL version of the game:

SNSP-AQTP-EUR  
SNSP-AQTP-AUS  
SNSP-AQTF-FRA  
SNSP-AQTD-NOE  
SNSP-AQTS-ESP

It does not work with the Japanese Version of the game, 天地創造 (Tenchi Sōzō), as the latter uses a different character set. In its current form, *sraminspect\_terranigma* will not translate these characters correctly between the game and output to/input from the user.

You need Python 3, there are no other dependencies.

Basic usage
----------

```sraminspect_terranigma.py path/to/your/terranigma_srm_file.srm```

Viewing and changing the content of variables should be self-explanatory; it is currently only implemented as a guided dialog on the command line.

Currently, command-line arguments (other than the input file path) that would allow for a more automated process, are not implemented.

Limitations
-----------

- Currently, the only supported variable is the savegame slot name. Others could be added easily provided their locations inside the SRAM are known.

