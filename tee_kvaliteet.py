# -*- coding: utf-8 -*-
"""
Camilla 2.4 AR-mudel MITMES KVALITEEDIASTMES.

MIKS SEE OLEMAS ON

Esimene AR-mudel nagi valja halb ja pohjus oli minu horendusstrateegias:
kogu mudel horendati UHTLASELT 73 000 -> 22 000. Aga osade kaal on vaga ebavordne:

    KERIS                  219 755 tri   75 % koigest
    KERE (kest, katus)      33 281 tri
    SEIN_KLAAS               4 294 tri
    LAVA_YKS                   552 tri
    UKS                        590 tri
    KERISEPIIRE                108 tri

Uhtlane suhe lohkus seinu ja laudu tapselt sama palju kui kivihunnikut, mida
AR-is keegi lahedalt ei vaata. Oige on eelarve OSADE VAHEL jagada.

KAKS ERI TOORIISTA ERI GEOMEETRIALE

  planar dissolve  — uhetasandilised naabertahud liidetakse. Seintel ja katusel
                     on see peaaegu KADUDETA: lame paneel ei vaja 200 kolmnurka.
  collapse         — servade kokkutombamine. Ainus, mis kividel toimib.

NB: planar dissolve KIVIDEL on juba korra proovitud ja tulemus oli katastroof
(707k -> 496 tri, mudel havis). Seetottu on siin range jaotus: kest saab planar,
keris saab collapse.

TIPUD, MITTE KOLMNURGAD

Quick Looki piir sailtub tippudest rohkem kui tahkudest. Mootdetud:
    73 024 tri / 219 000 tippu / 5,8 MB  ->  EI AVANE
    22 000 tri /  38 000 tippu / 1,8 MB  ->  avaneb
Kaks punkti on liiga kaugel, et piiri teada. Seetottu teeb see skript NELI
astet ja kasutaja utleb, milline veel avaneb.

Blender 4.3:
  blender.exe --background --factory-startup --python tee_kvaliteet.py
"""
import bpy, bmesh, os, sys
from mathutils import Vector

MUDELID = r"C:\Users\user\Desktop\Saunashark config\SaunaShark conf demo\Assets\Models"
VALJUND = r"C:\Users\user\Desktop\Saunashark config\_ar"

KEST  = ["KERE", "SEIN_KLAAS", "LAVA_YKS", "UKS", "KERISEPIIRE"]
KERIS = "KERIS_ELEKTRI_HIVEMINI"
KERISE_KOHT_UNITY = (-1.062, 0.105, -1.970)

# (nimi, planar nurk kestal, mitu SUURIMAT kivi/detaili kerisest alles jaab)
#
# ★ MIKS KIVIDE ARV, MITTE KOLMNURKADE EELARVE:
# Esimene katse andis eelarvega 6 000 ja 18 000 MOLEMAL juhul 34 432 kolmnurka.
# Decimate COLLAPSE ei saa allapoole, kui mesh koosneb sadadest eraldi suletud
# saartest — igauks vajab miinimumi ja summa ongi see pohi. Ainus viis allapoole
# on VAHENDADA SAARTE ARVU: sisemised kivid ei paista kunagi valja, seega
# jaavad alles suurimad.
#
# Kest jaab KOIGIS astmetes taismahus: 38 000 tri, aga ainult 23 000 tippu —
# tema ei ole probleem. Kogu kaal on kerises.
ASTMED = [
    ("a",  1.0,  60),
    ("b",  1.0, 160),
    ("c",  0.5, 400),
]

VARVID = {
    "PUIT":   (0.64, 0.48, 0.31, 1.0),
    "LAVA":   (0.44, 0.32, 0.20, 1.0),
    "KLAAS":  (0.86, 0.91, 0.93, 0.28),
    "MUST":   (0.055, 0.055, 0.06, 1.0),
    "SINDEL": (0.085, 0.085, 0.09, 1.0),
}
KAARDISTUS = {
    "material_1": "SINDEL",
    "SEIN_KLAAS/M_Puit_Vineer": "MUST", "UKS/M_Puit_Vineer": "MUST",
    "UKS/M_Puit_Lepp": "MUST",
    "lepp": "LAVA", "lepp_2": "LAVA", "Spruce_seamless3": "LAVA", "Wood": "LAVA",
    "M_Klaas": "KLAAS",
}
PIIRDELAUAD = {16, 17, 18, 19, 20}


def L(*a):
    print("[KVAL]", *a); sys.stdout.flush()


def puhas(n):
    return n[:-4] if len(n) > 4 and n[-4] == "." and n[-3:].isdigit() else n


def tri(objs):
    t = 0
    for o in objs:
        if o.type == "MESH":
            o.data.calc_loop_triangles(); t += len(o.data.loop_triangles)
    return t


def vert(objs):
    return sum(len(o.data.vertices) for o in objs if o.type == "MESH")


def bbox(objs):
    mn = Vector((1e9,)*3); mx = Vector((-1e9,)*3)
    for o in objs:
        for v in o.data.vertices:
            w = o.matrix_world @ v.co
            for i in range(3):
                if w[i] < mn[i]: mn[i] = w[i]
                if w[i] > mx[i]: mx[i] = w[i]
    return mn, mx


def tee_materjal(nimi):
    m = bpy.data.materials.new(nimi); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    r, g, bl, a = VARVID[nimi]
    b.inputs["Base Color"].default_value = (r, g, bl, 1.0)
    b.inputs["Roughness"].default_value = 0.06 if nimi == "KLAAS" else 0.85
    b.inputs["Metallic"].default_value = 0.0
    if a < 1.0:
        b.inputs["Alpha"].default_value = a; m.blend_method = "BLEND"
    return m


def keevita(objs, dist=0.0001):
    for o in objs:
        bm = bmesh.new(); bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
        bm.to_mesh(o.data); bm.free(); o.data.update()


def planar(objs, kraadi):
    """Uhetasandilised tahud kokku. MATERIAL + SHARP hoiavad servad ja
    materjalipiirid alles — ilma nendeta laheks klaas puiduga kokku."""
    import math
    for o in objs:
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.dissolve_limited(angle_limit=math.radians(kraadi),
                                      delimit={"MATERIAL", "SHARP", "SEAM"})
        bpy.ops.mesh.quads_convert_to_tris(quad_method="BEAUTY", ngon_method="BEAUTY")
        bpy.ops.object.mode_set(mode="OBJECT")


for nimi, kraadi, kerise_saari in ASTMED:
    L("=" * 66)
    L("ASTE %s  (planar %.1f kraadi, keris %d saart)" % (nimi, kraadi, kerise_saari))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    matid = {k: tee_materjal(k) for k in VARVID}

    osad = {}
    for osa in KEST + [KERIS]:
        tee = os.path.join(MUDELID, osa + ".fbx")
        if not os.path.exists(tee):
            continue
        enne = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=tee, axis_forward="-Z", axis_up="Y")
        osad[osa] = [o for o in bpy.data.objects if o not in enne and o.type == "MESH"]

    # materjalid kestale
    for osa, objs in osad.items():
        if osa == KERIS:
            continue
        for o in objs:
            pn = puhas(o.name)
            if pn.startswith("group_"):
                try:
                    if int(pn[6:]) in PIIRDELAUAD:
                        o.data.materials.clear(); o.data.materials.append(matid["MUST"]); continue
                except ValueError:
                    pass
            for i, ms in enumerate(o.data.materials):
                mn = puhas(ms.name) if ms else ""
                r = KAARDISTUS.get(osa + "/" + mn) or KAARDISTUS.get(mn) or "PUIT"
                o.data.materials[i] = matid[r]

    kest = [o for osa, objs in osad.items() if osa != KERIS for o in objs]
    k_enne_t, k_enne_v = tri(kest), vert(kest)
    keevita(kest)
    planar(kest, kraadi)
    keevita(kest)
    L("  kest:  %d -> %d tri,  %d -> %d tippu"
      % (k_enne_t, tri(kest), k_enne_v, vert(kest)))

    # keris: SAARTE ARVU vahendus, siis collapse. Planar havitab kivid —
    # proovitud, 707k -> 496 tri ja mudel oli sodi.
    if KERIS in osad:
        ko = osad[KERIS]
        keevita(ko, 0.00005)
        t0 = tri(ko)

        o = ko[0]
        bm = bmesh.new(); bm.from_mesh(o.data)
        # eralda saared: iga kivi ja iga metalliosa on omaette suletud kest
        saared = []
        nahtud = set()
        for f in bm.faces:
            if f.index in nahtud:
                continue
            hunnik = [f]; nahtud.add(f.index); jarjekord = [f]
            while jarjekord:
                p = jarjekord.pop()
                for e in p.edges:
                    for n in e.link_faces:
                        if n.index not in nahtud:
                            nahtud.add(n.index); hunnik.append(n); jarjekord.append(n)
            saared.append(hunnik)

        # suurus = gabariidi ruumala; sisemised kivid on vaiksed ja peidus
        def maht(h):
            mn = [1e9]*3; mx = [-1e9]*3
            for f in h:
                for v in f.verts:
                    for i in range(3):
                        mn[i] = min(mn[i], v.co[i]); mx[i] = max(mx[i], v.co[i])
            return (mx[0]-mn[0]) * (mx[1]-mn[1]) * (mx[2]-mn[2])

        saared.sort(key=maht, reverse=True)
        alles = saared[:kerise_saari]
        kustuta = [f for h in saared[kerise_saari:] for f in h]
        L("  keris: %d saart, alles %d, kustutan %d tahku"
          % (len(saared), len(alles), len(kustuta)))
        if kustuta:
            bmesh.ops.delete(bm, geom=kustuta, context="FACES")
        bm.to_mesh(o.data); bm.free(); o.data.update()

        # holjuvad tipud maha
        bm = bmesh.new(); bm.from_mesh(o.data)
        holj = [v for v in bm.verts if not v.link_faces]
        if holj:
            bmesh.ops.delete(bm, geom=holj, context="VERTS")
        bm.to_mesh(o.data); bm.free(); o.data.update()

        L("  keris: %d -> %d tri, %d tippu" % (t0, tri(ko), vert(ko)))

        ux, uy, uz = KERISE_KOHT_UNITY
        siht = Vector((-ux, -uz, uy))
        mn, mx = bbox(ko)
        nihe = siht - Vector(((mn.x+mx.x)/2, (mn.y+mx.y)/2, mn.z))
        for o in ko:
            o.location += nihe

    koik = [o for o in bpy.data.objects if o.type == "MESH"]
    mn, mx = bbox(koik)
    n = Vector((-(mn.x+mx.x)/2, -(mn.y+mx.y)/2, -mn.z))
    for o in koik:
        o.location += n
    bpy.context.view_layer.update()
    mn, mx = bbox(koik); d = mx - mn

    bpy.ops.object.select_all(action="SELECT")
    fail = os.path.join(VALJUND, "camilla24_%s.usdz" % nimi)
    bpy.ops.wm.usd_export(filepath=fail, selected_objects_only=True,
        export_materials=True, generate_preview_surface=True,
        root_prim_path="/root", convert_orientation=True,
        export_global_up_selection="Y", export_global_forward_selection="NEGATIVE_Z",
        export_textures=False, relative_paths=True)
    glb = os.path.join(VALJUND, "camilla24_%s.glb" % nimi)
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True,
        export_apply=True, export_yup=True,
        export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=6,
        export_materials="EXPORT", export_cameras=False, export_lights=False)

    L("  KOKKU %d tri, %d tippu, %.2f x %.2f x %.2f m" % (tri(koik), vert(koik), d.x, d.y, d.z))
    L("  -> camilla24_%s.usdz  %.2f MB   |  .glb %.2f MB"
      % (nimi, os.path.getsize(fail)/1048576.0, os.path.getsize(glb)/1048576.0))

L("VALMIS")
