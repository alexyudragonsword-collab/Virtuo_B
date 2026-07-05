# Netlist Semantic Cleanup Reference

## Goal

Turn generated Spectre/SPICE decks into clean reference netlists that an analog
designer can read, modify, and simulate. The output should separate:

- `netlist/dut/`: reusable DUT cells and DUT wrappers.
- `netlist/tb/`: testbench scaffolds, supplies, clocks, stimulus, probes.
- `netlist/runs/`: concrete run decks, sweeps, corners, Monte Carlo, PSS/PNoise.
- `netlist/va/`: Verilog-A helpers when needed.

Use the comparator-characterization reference layout as the target style:
`cmp_under_test_*` selects the DUT variant, `tb_*` files instantiate
`cmp_under_test`, and `runs/*` configure individual experiments.

## Role of the Model

Netlist cleanup is a semantic curation task. The model should inspect the
circuit, decide the intended abstraction boundary, and then write a clean
source artifact. Do not let a script blindly rewrite the netlist and call that
the final answer.

Use deterministic checks only after the semantic pass, to catch:

- MOS instance parameters that still look layout-derived.
- Random node names that still need semantic review.
- Generic instance names that hide circuit function.
- DUT files that still contain testbench or run-deck content.

## What to Keep

For MOS devices in clean schematic/reference netlists, keep only structural
identity and drawn geometry:

```spectre
mn_input_vinp_main (sense_n VINP tail_src VSS) nch_ulvt_mac l=30n w=16u multi=1 nf=32
```

Default MOS keep-list:

- `l`
- `w`
- `nf`
- `fingers`
- `m`
- `multi`

Keep additional parameters only when they are intentionally part of the
schematic design contract. Examples: `stack`, `seg`, `nfin`, or project-local
layout choices that a designer would manually draw.

## What to Remove

Remove layout extraction side effects from curated reference decks:

- diffusion/perimeter parasitics: `ad`, `as`, `pd`, `ps`
- source/drain resistance annotations: `nrd`, `nrs`
- LOD/WPE/STI/proximity terms: `sa`, `sb`, `sca`, `scb`, `scc`, `spa`, `sap`,
  `sapb`, `spba`, `spmt`, `spomt`, `spmb`, `spomb`
- DFM/extraction flags and simulator-generated proximity tails
- raw PEX mesh resistors/caps unless the task is explicitly a parasitic study

This is intentionally different from geometry-preserving post-layout modeling.
If the task requires post-layout-equivalent behavior, keep the extraction deck
or use a dedicated parasitic-reduction flow instead of deleting second-order
terms.

## DUT/Testbench Split

Use this split for a reusable analog reference:

```text
netlist/
  dut/
    cmp_strongarm.scs
    cmp_under_test_plain.scs
    cmp_under_test_offset_trim.scs
  tb/
    tb_cmp_offset_search.scs
    tb_cmp_pss_pnoise.scs
  runs/
    offset_plain.scs
    pss_pnoise_plain.scs
  va/
    va_offset_search.va
```

Rules:

- A DUT file defines only subckts and internal passive/device elements.
- A DUT wrapper exposes a stable `cmp_under_test` or `<block>_under_test`
  interface when multiple variants exist.
- A testbench file instantiates the wrapper and owns supplies, clocks, stimulus,
  loads, probes, and measurement helper blocks.
- A run file owns parameter values, model includes, corner/Monte Carlo setup,
  save directives, and analysis statements.
- Do not leave a monolithic ADE point netlist as the final clean artifact.

## Semantic Naming

Every meaningful node and every meaningful instance should have a name that
communicates circuit function. Do not leave random tool names when the function
is knowable.

Good node names:

- `VINP`, `VINN`, `VOUTP`, `VOUTN`
- `CLK`, `CLK_EVAL`, `CLK_RESET`
- `sense_p`, `sense_n`
- `tail_src`
- `latch_p`, `latch_n`
- `bias_n`, `bias_p`
- `trim_os<0>`, `trim_os<1>`

Good instance names:

- `mn_input_vinp_main`
- `mn_tail_clk`
- `mp_precharge_sense_p`
- `mp_latch_lm_pullup`
- `x_cmp_plain`
- `x_offset_search`

Names that need cleanup or review:

- `net1`, `net2`, `_net23`
- numeric nodes such as `17`, `2839`
- extraction mesh names such as `N_<net>_<inst>_d`
- `c_123_n`, `mesh_42`, `noxref_*`
- generic instances like `M0`, `M1`, `I42`, `X123`

Rename only with evidence from schematic context, labels, pin names, waveform
expressions, subckt ports, or local graph neighborhood. If a node remains
ambiguous, use a local review note rather than inventing a semantic name.

## Semantic Cleanup Checklist

1. Copy the raw netlist into an archive or `raw/` folder.
2. Identify DUT boundary, testbench scope, and run-deck scope.
3. Build a semantic rename map for nodes and instances from circuit evidence.
4. Write the DUT file with only subckt definitions and internal devices.
5. Write the testbench file with supplies, clocks, stimulus, loads, probes, and
   wrapper instantiation.
6. Write run files with model includes, parameters, corners, saves, and
   analyses.
7. Remove MOS tail parameters in the curated artifact, keeping only true drawn
   geometry unless an extra parameter is intentionally part of the design.
8. Run `scripts/check_spectre_netlist.py` to find residual mechanical issues.
9. Resolve reported issues semantically or document why each remaining issue is
   intentional.
10. Run Spectre syntax/smoke validation if Cadence is available.

## Example Before/After

Generated MOS line:

```spectre
M21 (VO1P VINPN VBN VSS) nch_ulvt_mac l=30n w=2u multi=1 nf=8 sd=100n ad=1e-13 as=1.125e-13 pd=2.8u ps=3.4u nrd=0.273611 nrs=0.273611 sa=295.835n sb=295.835n spmt=1.11111e+15 dfm_flag=0
```

Clean reference line:

```spectre
mn_input_vinp_stage1 (vo1_p vinp_n vbias_n VSS) nch_ulvt_mac l=30n w=2u multi=1 nf=8
```

The second line is not just parameter-pruned: names have been made semantic.
That semantic pass requires circuit context.
