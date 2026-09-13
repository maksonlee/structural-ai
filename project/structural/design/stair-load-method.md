# Stair gravity-transfer method

This is the diagnostic load path used by the building model. It does not provide
complete stair stiffness, RC reinforcement or anchorage design.

Flights carry gravity longitudinally to their lower/upper landing lines.
Transverse strips transfer those reactions to the west and shared side walls.
The ground landing also uses this assumed mechanism; soil support is not credited.
The monolithic final structure may transfer moments and brace the frame, which
requires separate design.

Source extrusion polygons determine flight volume and centroid. Concrete inside
the upper receiving slab is assigned to that slab once, using actual footprints
and voids. Live/finish load uses the clear horizontal projection. Landing self-weight
and area loads use the actual L-shaped footprint.

For weight W at coordinate c between a and b, reactions are W(b-c)/(b-a) and
W(c-a)/(b-a). Transverse transfer uses the same equilibrium. The nominal support
lines and physical centroids remain in the source-GUID ledger. Receiving
interpolation uses actual owned wall cells and preserves force and both
horizontal first moments. A point outside the receiving envelope is an error,
not permission to fill an opening or select a nearest node.

Permanent mass follows the released reactions with preserved total and horizontal
centroid. Vertical mass distribution, local stair vibration and rotational
inertia are not fully represented.

The office case uses 2.941995 kN/m2 stair live load and an explicit 1.50 kN/m2
synthetic finish allowance. These are recorded inputs, not proof of a complete
code load envelope. The [source register](../../../docs/sources.yaml) records the
review of 建築技術規則建築構造編 Articles 10-17 and the use-specific assumptions.

The architectural proposal has uniform 133.333 mm risers, 290 mm treads and an
L-shaped midlanding. Read [the architectural review](../../architect/outputs/architectural-review.md)
for actual dimensional screens and open egress/product questions.
[The local landing example](../outputs/deliverables/landing-strip.md) checks only
a selected direct-gravity strip; full flight/landing continuity and anchorage
remain open.
