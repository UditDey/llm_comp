#!/usr/bin/env python3
"""
SiliconCompiler build script for Echo Cache topology (2x Omega MINs).

Expects echo.v and echo.sdc in the working directory.
Run gen.py first to produce them.

Usage:
    python3 build_echo.py
    python3 build_echo.py --pin-constraints

Pin placement (when --pin-constraints is set):
    LEFT edge  ("read-port side"):
        - ctrl_in:  addresses entering the control network
        - xfer_out: data exiting the transfer network
    RIGHT edge ("bank side"):
        - ctrl_out: addresses reaching the banks
        - xfer_in:  data entering the transfer network from banks
    Select lines: unconstrained
"""

import argparse
from siliconcompiler import ASIC, Design
from siliconcompiler.targets import skywater130_demo

# Must match the N, W used in gen.py
N = 32
W = 8


def main():
    parser = argparse.ArgumentParser(description="Build Echo Cache topology with SiliconCompiler")
    parser.add_argument("--pin-constraints", action="store_true",
                        help="Constrain data pins to die edges matching Echo Cache layout")
    args = parser.parse_args()

    design = Design("echo")
    design.set_topmodule("echo", fileset="rtl")
    design.add_file("echo.v", fileset="rtl")
    design.add_file("echo.sdc", fileset="sdc")

    project = ASIC(design)
    project.add_fileset(["rtl", "sdc"])
    skywater130_demo(project)

    # ----------------------------------------------------------------
    # Pin constraints
    #
    # Side encoding (clockwise from lower-left):
    #   1 = left, 2 = bottom, 3 = right, 4 = top
    #
    # Keypath: ('constraint', 'pin', <name>, 'side'|'order')
    # ----------------------------------------------------------------

    if args.pin_constraints:
        order = 0

        # LEFT edge: ctrl_in (addresses from read-ports)
        for i in range(N):
            for b in range(W):
                name = f"ctrl_in_{i}[{b}]"
                project.set('constraint', 'pin', name, 'side', 1)
                project.set('constraint', 'pin', name, 'order', order)
                order += 1

        # LEFT edge: xfer_out (data to read-ports)
        for i in range(N):
            for b in range(W):
                name = f"xfer_out_{i}[{b}]"
                project.set('constraint', 'pin', name, 'side', 1)
                project.set('constraint', 'pin', name, 'order', order)
                order += 1

        order = 0

        # RIGHT edge: ctrl_out (addresses to banks)
        for i in range(N):
            for b in range(W):
                name = f"ctrl_out_{i}[{b}]"
                project.set('constraint', 'pin', name, 'side', 3)
                project.set('constraint', 'pin', name, 'order', order)
                order += 1

        # RIGHT edge: xfer_in (data from banks)
        for i in range(N):
            for b in range(W):
                name = f"xfer_in_{i}[{b}]"
                project.set('constraint', 'pin', name, 'side', 3)
                project.set('constraint', 'pin', name, 'order', order)
                order += 1

    project.option.set_remote(True)
    project.run()
    project.summary()
    project.show()


if __name__ == "__main__":
    main()
