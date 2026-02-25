#!/usr/bin/env python3
"""
Generate structural Verilog netlists for crossbar and Echo Cache topologies.

Each design is built entirely from explicit mux2 instances - no behavioral code,
no generate blocks, no ternary operators. Just instances and wires.

The Echo Cache uses two Omega MINs: a control network (addresses flow from
read-ports to banks) and a transfer network (data flows from banks to read-ports).

Usage:
    python3 gen.py <N> [W]
    
    N: Number of ports (must be power of 2)
    W: Data width in bits (default: 8)

Outputs:
    crossbar.v   - Crossbar topology netlist
    echo.v       - Echo Cache topology netlist (2x Omega MINs)
    crossbar.sdc - Timing constraints for crossbar
    echo.sdc     - Timing constraints for echo
"""

import math
import sys


def gen_mux2(W):
    """Generate a simple W-bit 2:1 mux module."""
    return f"""\
(* keep_hierarchy = "yes" *)
module mux2 (
    input  wire [{W-1}:0] a,
    input  wire [{W-1}:0] b,
    input  wire        sel,
    output wire [{W-1}:0] out
);
    assign out = sel ? b : a;
endmodule
"""


def gen_crossbar(N, W):
    """
    Generate a crossbar netlist.
    
    Structure: Each of N outputs gets a balanced binary mux tree selecting
    from N inputs. Each tree has log2(N) stages and N-1 mux2 instances.
    
    Total mux2 instances: N * (N - 1)
    """
    STAGES = int(math.log2(N))
    assert 2 ** STAGES == N, f"N={N} must be a power of 2"

    lines = []

    # Mux2 module
    lines.append(gen_mux2(W))

    # Module header
    lines.append(f"module crossbar (")

    # Build port list
    ports = []
    for i in range(N):
        ports.append(f"    input  wire [{W-1}:0] data_in_{i}")
    for i in range(N):
        ports.append(f"    output wire [{W-1}:0] data_out_{i}")
    for j in range(N):
        for s in range(STAGES):
            ports.append(f"    input  wire sel_{j}_{s}")

    lines.append(",\n".join(ports))
    lines.append(");")
    lines.append("")

    # For each output, build a mux tree
    for j in range(N):
        lines.append(f"    // ---- Mux tree for output {j} ----")

        # Track wires at each level
        # Level 0 inputs are the N data inputs
        prev_wires = [f"data_in_{i}" for i in range(N)]

        for s in range(STAGES):
            n_muxes = len(prev_wires) // 2
            curr_wires = []

            for m in range(n_muxes):
                if s == STAGES - 1:
                    assert n_muxes == 1
                    out_name = f"data_out_{j}"
                else:
                    out_name = f"t_{j}_s{s}_m{m}"
                    lines.append(f"    wire [{W-1}:0] {out_name};")

                lines.append(
                    f"    mux2 u_xbar_o{j}_s{s}_m{m} ("
                    f".a({prev_wires[2*m]}), "
                    f".b({prev_wires[2*m+1]}), "
                    f".sel(sel_{j}_{s}), "
                    f".out({out_name}));"
                )
                curr_wires.append(out_name)

            prev_wires = curr_wires
            lines.append("")

    lines.append("endmodule")
    return "\n".join(lines)


def perfect_shuffle(i, bits):
    """Left-rotate the 'bits'-bit representation of i by 1 position."""
    return ((i << 1) | (i >> (bits - 1))) & ((1 << bits) - 1)


def gen_omega_stages(N, W, STAGES, prefix):
    """
    Generate one Omega network as inline Verilog (wires + mux2 instances).
    
    Returns (lines, in_port_names, out_port_names, sel_port_names)
    where port names are the top-level port names for this network.
    """
    lines = []
    in_ports = [f"{prefix}_in_{i}" for i in range(N)]
    out_ports = [f"{prefix}_out_{i}" for i in range(N)]
    sel_ports = []

    for s in range(STAGES):
        for k in range(N // 2):
            sel_ports.append(f"{prefix}_sel_{s}_{k}_lo")
            sel_ports.append(f"{prefix}_sel_{s}_{k}_hi")

    # Declare inter-stage wires
    for s in range(STAGES):
        for i in range(N):
            lines.append(f"    wire [{W-1}:0] {prefix}_stg{s}_out_{i};")
    lines.append("")

    # Build each stage
    for s in range(STAGES):
        lines.append(f"    // ---- {prefix}: Stage {s} ----")

        if s == 0:
            in_wires = [f"{prefix}_in_{i}" for i in range(N)]
        else:
            in_wires = [None] * N
            for i in range(N):
                dest = perfect_shuffle(i, STAGES)
                in_wires[dest] = f"{prefix}_stg{s-1}_out_{i}"

        for k in range(N // 2):
            wire_a = in_wires[2 * k]
            wire_b = in_wires[2 * k + 1]
            out_lo = f"{prefix}_stg{s}_out_{2 * k}"
            out_hi = f"{prefix}_stg{s}_out_{2 * k + 1}"

            lines.append(
                f"    mux2 u_{prefix}_s{s}_sw{k}_lo ("
                f".a({wire_a}), "
                f".b({wire_b}), "
                f".sel({prefix}_sel_{s}_{k}_lo), "
                f".out({out_lo}));"
            )
            lines.append(
                f"    mux2 u_{prefix}_s{s}_sw{k}_hi ("
                f".a({wire_a}), "
                f".b({wire_b}), "
                f".sel({prefix}_sel_{s}_{k}_hi), "
                f".out({out_hi}));"
            )

        lines.append("")

    # Output assignments
    lines.append(f"    // ---- {prefix}: Output assignments ----")
    last = STAGES - 1
    for i in range(N):
        lines.append(f"    assign {prefix}_out_{i} = {prefix}_stg{last}_out_{i};")
    lines.append("")

    return lines, in_ports, out_ports, sel_ports


def gen_echo(N, W):
    """
    Generate an Echo Cache netlist with two Omega MINs.
    
    Control network (ctrl): addresses flow from read-ports (left) to banks (right)
    Transfer network (xfer): data flows from banks (right) to read-ports (left)
    
    Total mux2 instances: 2 * N * log2(N)
    """
    STAGES = int(math.log2(N))
    assert 2 ** STAGES == N, f"N={N} must be a power of 2"

    lines = []

    # Mux2 module
    lines.append(gen_mux2(W))

    # Generate both networks' internal logic
    ctrl_lines, ctrl_in, ctrl_out, ctrl_sel = gen_omega_stages(N, W, STAGES, "ctrl")
    xfer_lines, xfer_in, xfer_out, xfer_sel = gen_omega_stages(N, W, STAGES, "xfer")

    # Module header
    lines.append(f"module echo (")

    ports = []

    # Control network: addresses from read-ports (left) to banks (right)
    for name in ctrl_in:
        ports.append(f"    input  wire [{W-1}:0] {name}")
    for name in ctrl_out:
        ports.append(f"    output wire [{W-1}:0] {name}")

    # Transfer network: data from banks (right) to read-ports (left)
    for name in xfer_in:
        ports.append(f"    input  wire [{W-1}:0] {name}")
    for name in xfer_out:
        ports.append(f"    output wire [{W-1}:0] {name}")

    # Select lines for both networks
    for name in ctrl_sel:
        ports.append(f"    input  wire {name}")
    for name in xfer_sel:
        ports.append(f"    input  wire {name}")

    lines.append(",\n".join(ports))
    lines.append(");")
    lines.append("")

    # Control network body
    lines.append("    // ========== Control Network (addresses: read-ports -> banks) ==========")
    lines.extend(ctrl_lines)

    # Transfer network body
    lines.append("    // ========== Transfer Network (data: banks -> read-ports) ==========")
    lines.extend(xfer_lines)

    lines.append("endmodule")
    return "\n".join(lines)


def gen_sdc(design_name):
    """Generate minimal SDC for a combinational design."""
    return f"""\
# Timing constraints for {design_name} (combinational)
create_clock -name virtual_clk -period 10.0
set_input_delay  -clock virtual_clk 0.0 [all_inputs]
set_output_delay -clock virtual_clk 0.0 [all_outputs]
"""


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    N = int(sys.argv[1])
    W = int(sys.argv[2]) if len(sys.argv) > 2 else 8

    STAGES = int(math.log2(N))
    if 2 ** STAGES != N:
        print(f"Error: N={N} is not a power of 2")
        sys.exit(1)

    print(f"Generating netlists for N={N}, W={W}")
    print(f"  Crossbar: {N} outputs x {N-1} mux2 each = {N*(N-1)} mux2 instances")
    print(f"  Echo:     2 x ({STAGES} stages x {N} mux2) = {2*N*STAGES} mux2 instances")

    with open("crossbar.v", "w") as f:
        f.write(gen_crossbar(N, W))
    print("  Wrote crossbar.v")

    with open("echo.v", "w") as f:
        f.write(gen_echo(N, W))
    print("  Wrote echo.v")

    for name in ("crossbar", "echo"):
        with open(f"{name}.sdc", "w") as f:
            f.write(gen_sdc(name))
        print(f"  Wrote {name}.sdc")

    print("Done.")


if __name__ == "__main__":
    main()
