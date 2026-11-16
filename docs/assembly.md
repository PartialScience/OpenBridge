# Assembly and BOM notes

The schematic is the source of truth. [bom.csv](bom.csv) is generated for **one board assembly**, including the detachable GDT strips and off-board hardware. Mounting holes and mouse-bite features are excluded from purchasing quantities. Wire and insulation rows represent one assembly lot, not a specified length.

## Hardware

The [Hardware schematic](../Hardware.kicad_sch) includes:

| Use | Parts per board |
| --- | --- |
| Heatsink | 1 × Wakefield 511-6M |
| IGBT electrical/thermal isolation | 8 × Parker Chomerics 60-11-D401-1671 pads; 8 × Keystone 3049 shoulder washers |
| IGBT mounting | 8 × generic #4-40 screws |
| Board mounting | 4 × RAF M0592-3-N spacers, 3 mm long; 4 × generic M3 screws |
| GDT cables | 6 × Molex 22-01-2027 housings; 12 × 08-50-0114 contacts |
| GDT board interconnects | 8 × Wurth 61300211121 male headers; 8 × 61300211821 socket headers; 4 × Molex 171856-0002 headers |
| Output connections, J1/J2 | 2 each of M5 screws, flat washers and ring terminals |
| DC-input connections, H1/H2 | 2 each of M4 bolts, nuts and ring terminals; 4 flat washers |
| Build-dependent materials | GDT winding/lead wire, power wire and insulating sleeving, each as one assembly lot |

Fastener lengths, head styles, materials, locking methods, wire gauges and lengths are unspecified. Select them for the actual assembly. The J1/J2 REDCUBE terminals have M5 blind threads only 4 mm deep: account for the lug/washer stack and avoid bottoming the screws. The heatsink model represents the undrilled 511-6M extrusion; drilling and tapping for the board/IGBTs are assembly operations and are not modeled.

T1/T2 specify two TDK B64290L0659X065 **bare cores**, not finished transformers. Turns, ratio, winding phasing and insulation are unspecified because they depend on the coil and driver. The six cable housings allow four secondary connections and two primary connections; the primary-side mating hardware belongs to the external driver.

## Design checks and previews

The BOM audit checks purchasing metadata, unique references, footprint assignments and schematic-to-PCB UUID links. Generic entries deliberately use `Manufacturer = Generic` and `MPN = Unspecified`. This checks listed assembly coverage; it does not validate a complete coil design or certify electrical/thermal performance.

Run KiCad ERC and DRC on the current design before fabrication. Review electrical and layout findings, unconnected items, and schematic-to-PCB parity. Validate the assembled bridge for the intended driver, supply, cooling and coil load.

The preview generator removes J12–J23, MB1–MB16, strip copper, strip edges and the remaining attachment stub from a temporary copy, then closes the four attachment seams. It verifies one connected contour and runs KiCad's outline checks to reject gaps and self-intersections before rendering. It does not relocate the strips into an assembled position or render wiring/fasteners. If those parts or attachment points move, update the explicit strip regions, stub edges and seams in [render-config.json](../scripts/render-config.json).

Only the 3D preview uses the chosen solder-mask color and detached-board geometry. The saved PCB and its fabrication outputs retain their original settings and full panel layout.
