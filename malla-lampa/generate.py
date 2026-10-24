"""
Parametrisk vägglampa i "MALLA"-stil (rund nätskärm + räfflad väggbas).
Egen tolkning byggd från referensbilder – inte en kopia av originalfilerna.

Genererar filer för Bambu Lab A1 (byggyta 256 x 256 x 256 mm):

  3mf/bas.3mf                – väggbas med sockelhylla, kabelurtag och skruvhål
  3mf/skarm_nat_front.3mf    – skärm med nätmönster även på fronten
  3mf/skarm_hel_front.3mf    – skärm med hel (ljusspridande) front

Kör:  pip install manifold3d numpy
      python3 generate.py          # 3MF-filer
      python3 generate.py --stl    # även STL-filer i stl/

Alla mått i mm. Ändra parametrarna nedan för att anpassa.
"""

import math
import os
import struct
import zipfile

import numpy as np
from manifold3d import CrossSection, JoinType, Manifold, OpType

# ---------------------------------------------------------------------------
# Parametrar
# ---------------------------------------------------------------------------
SEG = 360                 # upplösning runt varvet

# Bas (väggdel)
BASE_PLATE_T = 4.0        # bakplattans tjocklek
BASE_H = 30.0             # basens totala höjd (från vägg)
RING_IN_R = 116.2         # ringens innerradie (skärmens krage går in här)
RING_T = 3.0              # ringens väggtjocklek
RIB_START = 6.0           # räfflor börjar på denna höjd
RIB_PITCH = 4.0           # avstånd mellan räfflor
RIB_DEPTH = 1.2           # räfflornas djup

SHELF_Y = -70.0           # sockelhyllans läge (mitt) under centrum
SHELF_T = 5.0             # hyllans tjocklek
SHELF_W = 70.0            # hyllans bredd
SHELF_DEPTH = 66.0        # hur långt ut från väggen hyllan når (z)
SOCKET_Z = 42.0           # sockelhålets centrum, avstånd från vägg
SOCKET_HOLE_D = 10.5      # M10-nippel (standard för E27/E14-socklar)

SCREW_D = 4.5             # skruvhål
SCREW_HEAD_D = 9.0        # försänkning
SCREW_HOLES = [(0.0, 55.0), (-60.0, -10.0), (60.0, -10.0)]

CABLE_NOTCH_W = 10.0      # kabelurtag i ringens nederkant
CABLE_NOTCH_H = 9.0
WALL_HOLE = (30.0, 18.0, -90.0)   # hål för infälld kabel: bredd, höjd, y

# Skärm
SHADE_T = 1.6             # väggtjocklek (4 linjer á 0,4 mm)
FRONT_T = 1.6             # frontens tjocklek
FIT_CLEARANCE = 0.25      # radiellt spel mellan krage och basring
CRUSH_RIBS = 8            # små klämlister på kragen för friktionspassning
CRUSH_RIB_R = 0.6
CRUSH_RIB_PROUD = 0.35    # hur mycket listen sticker ut

# Skärmens ytterprofil (z från fronten, r). Kragen läggs till ovanpå.
SHADE_PROFILE = [
    # z,    r,     interpolation till nästa punkt
    (0.0,  112.0, "lin"),
    (8.0,  118.0, "cos"),
    (27.0, 124.0, "cos"),
    (46.0, 118.5, "cos"),
    (65.0, 124.0, "cos"),
    (82.0, 118.0, "lin"),
    (85.0, None,  None),   # r = kragens ytterradie
]
COLLAR_H = 12.0           # hur långt kragen går in i basen

# Nätmönster (rutermönster med 45°-kanter -> skrivs utan support)
MESH_PITCH = 3.6          # mönstrets delning
MESH_HOLE_K = 0.56        # andel av delningen som är hål (strängbredd ~1,1 mm)
MESH_Z0 = 11.0            # nätet börjar här (från fronten)
MESH_Z1 = 79.0            # och slutar här
FRONT_MESH_R = 104.0      # nätets radie på fronten

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stl")
OUT_3MF = os.path.join(HERE, "3mf")


# ---------------------------------------------------------------------------
# Hjälpfunktioner
# ---------------------------------------------------------------------------
def revolve(points, segments=SEG):
    """Rotera en (r, z)-polygon runt Z-axeln."""
    return Manifold.revolve(CrossSection([points]), segments)


def box(x0, x1, y0, y1, z0, z1):
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def cyl(r, h, n=64):
    return Manifold.cylinder(h, r, r, n)


def diamond(a, b):
    return CrossSection([[(a, 0.0), (0.0, b), (-a, 0.0), (0.0, -b)]])


def write_stl(manifold, path):
    mesh = manifold.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3].astype(np.float32)
    t = np.asarray(mesh.tri_verts)
    tri = v[t]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    data = np.zeros(len(t), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    data["n"] = n
    data["v"] = tri
    with open(path, "wb") as f:
        f.write(b"MALLA-style wall lamp".ljust(80, b" "))
        f.write(struct.pack("<I", len(t)))
        f.write(data.tobytes())
    bb = manifold.bounding_box()
    size = [bb[i + 3] - bb[i] for i in range(3)]
    print(f"{os.path.basename(path)}: {len(t)} trianglar, "
          f"{size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm, "
          f"volym {manifold.volume() / 1000:.1f} cm³")


def write_3mf(manifold, path, name):
    """Minimal 3MF (zip-komprimerad, exakt indexerad mesh) – öppnas direkt i Bambu Studio."""
    mesh = manifold.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3]
    t = np.asarray(mesh.tri_verts)
    verts = "".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in v)
    tris = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in t)
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        f'<resources><object id="1" name="{name}" type="model"><mesh>'
        f"<vertices>{verts}</vertices><triangles>{tris}</triangles>"
        '</mesh></object></resources><build><item objectid="1"/></build></model>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)


# ---------------------------------------------------------------------------
# Skärmens profil
# ---------------------------------------------------------------------------
COLLAR_R_OUT = RING_IN_R - FIT_CLEARANCE
COLLAR_R_IN = COLLAR_R_OUT - SHADE_T
SHADE_BODY_H = SHADE_PROFILE[-1][0]
SHADE_H = SHADE_BODY_H + COLLAR_H


def shade_outer_r(z):
    pts = [(p[0], p[1] if p[1] is not None else COLLAR_R_OUT, p[2]) for p in SHADE_PROFILE]
    if z >= SHADE_BODY_H:
        return COLLAR_R_OUT
    for (z0, r0, mode), (z1, r1, _) in zip(pts, pts[1:]):
        if z0 <= z <= z1:
            u = (z - z0) / (z1 - z0)
            if mode == "cos":
                u = 0.5 - 0.5 * math.cos(math.pi * u)
            return r0 + (r1 - r0) * u
    return pts[0][1]


def shade_inner_r(z, dz=0.05):
    if z >= SHADE_BODY_H:
        return COLLAR_R_IN
    slope = (shade_outer_r(z + dz) - shade_outer_r(max(z - dz, 0))) / (2 * dz)
    return shade_outer_r(z) - SHADE_T * math.sqrt(1 + slope * slope)


def profile_samples(z_start):
    """Profilens z-värden: knutpunkterna plus ett jämnt rutnät som är förskjutet
    så att inga nätshål får hörn exakt på en facettkant (ger renare mesh)."""
    step = MESH_PITCH / 4
    first = MESH_Z0 + MESH_PITCH * MESH_HOLE_K / 2 + step / 2
    grid = first + step * np.arange(-int(first / step), int(SHADE_BODY_H / step) + 1)
    # bara knutar med knyck i profilen (cos-knutarna är mjuka och behövs inte)
    knots = [p[0] for i, p in enumerate(SHADE_PROFILE)
             if i == 0 or p[2] != "cos" or SHADE_PROFILE[i - 1][2] != "cos"]
    zs = np.concatenate([grid, knots, [z_start]])
    return np.unique(zs[(zs >= z_start) & (zs <= SHADE_BODY_H)])


def shade_shell():
    zs = np.unique(np.concatenate([profile_samples(0.0), [SHADE_H]]))
    outer = [(0.0, 0.0)] + [(shade_outer_r(z), z) for z in zs] + [(0.0, SHADE_H)]
    inner_z = np.unique(np.concatenate([profile_samples(FRONT_T), [SHADE_H + 1]]))
    inner = [(0.0, FRONT_T)] + [(shade_inner_r(z), z) for z in inner_z] + [(0.0, SHADE_H + 1)]
    # segment = 2 x antal nätkolumner så att facetterna linjerar med hålen
    seg = 2 * mesh_columns()
    return revolve(outer, seg) - revolve(inner, seg)


def crush_ribs():
    ribs = []
    z0 = SHADE_BODY_H + 1.5
    h = SHADE_H - z0 - 1.0
    for i in range(CRUSH_RIBS):
        a = 2 * math.pi * (i + 0.5) / CRUSH_RIBS
        r = COLLAR_R_OUT + CRUSH_RIB_PROUD - CRUSH_RIB_R
        ribs.append(cyl(CRUSH_RIB_R, h, 16).translate([r * math.cos(a), r * math.sin(a), z0]))
    return Manifold.compose(ribs)


def mesh_columns(r_mid=121.0):
    return int(round(2 * math.pi * r_mid / MESH_PITCH))


def side_mesh_holes():
    """Rutformade hål runt skärmens sida. Varannan rad förskjuten en halv delning."""
    cols = mesh_columns()
    a = b = MESH_PITCH * MESH_HOLE_K / 2
    # prisma längs -Y från r=105 till r=135 med rutan i XZ-planet
    prism = Manifold.extrude(diamond(a, b), 30.0).translate([0, 0, 105.0]).rotate([90, 0, 0])
    ring_a = Manifold.compose([prism.rotate([0, 0, 360.0 * i / cols]) for i in range(cols)])
    # vrid en kvarts facett så att hålens spetsar inte hamnar på facettkanterna
    ring_a = ring_a.rotate([0, 0, 360.0 / (8 * cols)])
    ring_b = ring_a.rotate([0, 0, 180.0 / cols])
    rows = []
    z = MESH_Z0 + b
    j = 0
    while z + b <= MESH_Z1:
        rows.append((ring_a if j % 2 == 0 else ring_b).translate([0, 0, z]))
        z += MESH_PITCH / 2
        j += 1
    print(f"  nät sida: {cols} kolumner x {len(rows)} rader = {cols * len(rows)} hål")
    return Manifold.compose(rows)


def front_mesh_holes():
    a = b = MESH_PITCH * MESH_HOLE_K / 2
    prism = Manifold.extrude(diamond(a, b), FRONT_T + 2).translate([0, 0, -1])
    holes = []
    n = int(FRONT_MESH_R / (MESH_PITCH / 2)) + 2
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            if (i + j) % 2:
                continue
            x, y = i * MESH_PITCH / 2, j * MESH_PITCH / 2
            if math.hypot(x, y) + a <= FRONT_MESH_R:
                holes.append(prism.translate([x, y, 0]))
    print(f"  nät front: {len(holes)} hål")
    return Manifold.compose(holes)


def make_shade(mesh_front):
    shell = shade_shell() + crush_ribs()
    cutters = [side_mesh_holes()]
    if mesh_front:
        cutters.append(front_mesh_holes())
    return Manifold.batch_boolean([shell] + cutters, OpType.Subtract)


# ---------------------------------------------------------------------------
# Bas
# ---------------------------------------------------------------------------
def base_ring_outer_r(z):
    r_out = RING_IN_R + RING_T
    if z < RIB_START:
        return r_out
    return r_out - RIB_DEPTH / 2 * (1 - math.cos(2 * math.pi * (z - RIB_START) / RIB_PITCH))


def make_base():
    zs = np.linspace(0, BASE_H, 121)
    profile = ([(0.0, 0.0)] + [(base_ring_outer_r(z), z) for z in zs]
               + [(RING_IN_R, BASE_H), (RING_IN_R, BASE_PLATE_T), (0.0, BASE_PLATE_T)])
    parts = [revolve(profile)]

    # Sockelhylla: vågrät när lampan sitter på väggen (y uppåt, z ut från väggen).
    sy0, sy1 = SHELF_Y - SHELF_T / 2, SHELF_Y + SHELF_T / 2
    z0 = BASE_PLATE_T - 0.5
    parts.append(box(-SHELF_W / 2, SHELF_W / 2, sy0, sy1, z0, SHELF_DEPTH))
    # Stödtrianglar under hyllan
    for x in (-SHELF_W / 2, SHELF_W / 2 - 4.0):
        pts = []
        for xx in (x, x + 4.0):
            pts += [(xx, sy0 + 0.5, z0), (xx, sy0 + 0.5, SHELF_DEPTH - 8.0),
                    (xx, SHELF_Y - 35.0, z0)]
        parts.append(Manifold.hull_points(pts))
    base = Manifold.batch_boolean(parts, OpType.Add)

    cut = []
    # Hål för sockelns M10-nippel (vertikalt när lampan hänger)
    cut.append(cyl(SOCKET_HOLE_D / 2, 40, 48).rotate([90, 0, 0]).translate([0, SHELF_Y + 20, SOCKET_Z]))
    # Kabelurtag i ringens nederkant (även genom plattan, så kabeln går längs väggen)
    cut.append(box(-CABLE_NOTCH_W / 2, CABLE_NOTCH_W / 2, -RING_IN_R - 10, -RING_IN_R + 8,
                   -1, CABLE_NOTCH_H))
    # Hål för infälld kabel/kopplingsdosa
    w, h, y = WALL_HOLE
    cut.append(Manifold.extrude(CrossSection.square([w - 8, h - 8], True).offset(4, JoinType.Round),
                                BASE_PLATE_T + 2).translate([0, y, -1]))
    # Spår för buntband (dragavlastning)
    for x in (-8.0, 8.0):
        cut.append(box(x - 1.25, x + 1.25, -106, -102, -1, BASE_PLATE_T + 1))
    # Försänkta skruvhål
    for x, y in SCREW_HOLES:
        cut.append(cyl(SCREW_D / 2, BASE_PLATE_T + 2, 32).translate([x, y, -1]))
        sink = (SCREW_HEAD_D - SCREW_D) / 2
        cut.append(Manifold.cylinder(sink + 0.01, SCREW_D / 2, SCREW_HEAD_D / 2 + 0.01, 32)
                   .translate([x, y, BASE_PLATE_T - sink]))
    return Manifold.batch_boolean([base] + cut, OpType.Subtract)


if __name__ == "__main__":
    import sys

    os.makedirs(OUT, exist_ok=True)
    os.makedirs(OUT_3MF, exist_ok=True)
    stl = "--stl" in sys.argv
    parts = [
        ("bas", make_base()),
        ("skarm_nat_front", make_shade(mesh_front=True)),
        ("skarm_hel_front", make_shade(mesh_front=False)),
    ]
    for name, part in parts:
        write_3mf(part, os.path.join(OUT_3MF, name + ".3mf"), name)
        if stl:
            write_stl(part, os.path.join(OUT, name + ".stl"))
        else:
            bb = part.bounding_box()
            print(f"{name}.3mf: {part.num_tri()} trianglar, "
                  f"{bb[3] - bb[0]:.1f} x {bb[4] - bb[1]:.1f} x {bb[5] - bb[2]:.1f} mm, "
                  f"volym {part.volume() / 1000:.1f} cm³")
