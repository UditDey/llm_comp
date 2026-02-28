# Topology-only PnR Experiment

This directory contains code for the topology-only crossbar vs echo interconnect PnR test. This uses `siliconcompiler` for PnR, targeting the `SKY130` process.

### `rtl_gen.py`
Called as:
```
./rtl_gen.py N W 
```
This generates the two Verilog files: `crossbar.v` and `echo.v`, with `N` ports, each with a data width `W`.

### `build_echo.py` and `build_crossbar.py`
Use `siliconcompiler` to run PnR on the generated RTL files for `SKY130`, and prints relevant metrics.

Run with `--pin-constraints` to constrain pin placement: for crossbar input pins are placed on the left edge and output pins are placed on the bottom, and for echo the input pins are placed on the left and outputs on the right.
