# -*- coding: utf-8 -*-
"""
Ukskoik milline 3D-fail -> AR-valmis GLB + USDZ.

KASUTUS
    blender.exe --background --factory-startup --python tee_ar_mudel.py -- \
        "C:\\tee\\Camilla_2.4.fbx"  camilla24  "Camilla 2.4"

    Argumendid:  <lahtefail>  <lyhinimi>  ["Kuvatav nimi"]
    Valjund laheb `_ar` kausta:  <lyhinimi>.glb  ja  <lyhinimi>.usdz

MIKS SEE SKRIPT OLEMAS ON — MOODETUD EELARVE

iOS Quick Look ei ava suuri faile. Ta ei utle ka, miks: ekraan jaab motlema voi
tuleb "object could not be opened". Mootdetud sama mudeliga:

    73 024 tri   219 000 tippu   5,80 MB   EI AVANE
    21 999 tri    37 954 tippu   1,80 MB   AVANEB
    (vordluseks tootav naide: 21 688 tri, 12 496 tippu, 0,59 MB)

Otsustav ei ole ainult kolmnurkade arv vaid TIPPUDE arv. Tahuline varjutus
lohestab iga tipu eraldi — 73 000 kolmnurka andis 219 000 tippu. Seetottu
keevitab see skript tipud enne horendamist kokku.

KOLM ASJA, MIS ON KOHUSTUSLIKUD JA MIDA KERGE UNUSTADA

  1. `convert_orientation=True` + up=Y. Blender kirjutab vaikimisi upAxis="Z",
     Quick Look ootab Y-ules. Kontrollitud USDA paisest.
  2. Konteiner: pakkimata ZIP, .usdc esimese kirjena, koik 64 baidi joonel.
     Blenderi eksportija teeb selle ise oigesti, aga skript kontrollib ule.
  3. Tekstuurid suurendavad faili kiiresti. Kui eelarve on tais, jaavad nad
     valja — parem tootav hall mudel kui avanematu tekstuuridega.
"""
import bpy, bmesh, os, sys, struct

VALJUND = os.path.dirname(os.path.abspath(__file__))

# Eelarve. Alumine rida on mootdetud tootav punkt; jatame varu.
SIHT_TRI   = 22000
MAX_TIPPE  = 60000
MAX_MB     = 3.0

# Kui fail lubab, jaavad tekstuurid alles. Ule selle piiri visatakse minema.
TEKSTUURID = True


def L(*a):
    print("[AR]", *a)
    sys.stdout.flush()


def loenda(objs):
    t = v = 0
    for o in objs:
        if o.type != "MESH":
            continue
        o.data.calc_loop_triangles()
        t += len(o.data.loop_triangles)
        v += len(o.data.vertices)
    return t, v


def impordi(tee):
    laiend = os.path.splitext(tee)[1].lower()
    L("impordin %s (%s)" % (os.path.basename(tee), laiend))
    if laiend == ".fbx":
        bpy.ops.import_scene.fbx(filepath=tee, axis_forward="-Z", axis_up="Y")
    elif laiend in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=tee)
    elif laiend == ".obj":
        bpy.ops.wm.obj_import(filepath=tee)
    elif laiend == ".dae":
        bpy.ops.wm.collada_import(filepath=tee)
    elif laiend in (".usd", ".usdc", ".usda", ".usdz"):
        bpy.ops.wm.usd_import(filepath=tee)
    elif laiend == ".blend":
        bpy.ops.wm.open_mainfile(filepath=tee)
    elif laiend == ".stl":
        bpy.ops.wm.stl_import(filepath=tee)
    else:
        raise SystemExit("Tundmatu vorming: %s" % laiend)


def kontrolli_usdz(tee):
    """Apple noab: pakkimata ZIP, .usdc esimesena, iga kirje 64 baidi joonel."""
    d = open(tee, "rb").read()
    off = n = halb = 0
    esimene = None
    while off + 4 <= len(d) and d[off:off + 4] == b"PK\x03\x04":
        nlen, elen = struct.unpack_from("<HH", d, off + 26)
        meetod = struct.unpack_from("<H", d, off + 8)[0]
        csize = struct.unpack_from("<I", d, off + 18)[0]
        nimi = d[off + 30:off + 30 + nlen].decode("utf-8", "replace")
        if esimene is None:
            esimene = nimi
        ds = off + 30 + nlen + elen
        if ds % 64 or meetod != 0:
            halb += 1
        off = ds + csize
        n += 1
    korras = halb == 0 and esimene and esimene.endswith((".usdc", ".usda"))
    L("  konteiner: %d kirjet, esimene %s, joondus %s"
      % (n, esimene, "OK" if halb == 0 else "VIGA (%d)" % halb))
    return korras


argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(argv) < 2:
    raise SystemExit("Kasutus: ... --python tee_ar_mudel.py -- <fail> <lyhinimi> [nimi]")
lahte, lyhi = argv[0], argv[1]
kuvanimi = argv[2] if len(argv) > 2 else lyhi

bpy.ops.wm.read_factory_settings(use_empty=True)
impordi(lahte)

objs = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons)]
if not objs:
    raise SystemExit("Failis ei ole uhtegi mesh'i")
t0, v0 = loenda(objs)
L("alguses: %d objekti, %d tri, %d tippu" % (len(objs), t0, v0))

# --- 1. keevita tipud: TIPPUDE arv on Quick Looki jaoks otsustavam kui tahud
for o in objs:
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    bm.to_mesh(o.data); bm.free(); o.data.update()
t1, v1 = loenda(objs)
L("keevitatud: %d tri, %d tippu" % (t1, v1))

# --- 2. horenda kolmnurkade arv eelarvesse
suhe = min(1.0, SIHT_TRI / float(t1)) if t1 else 1.0
if suhe < 0.999:
    for o in objs:
        bpy.context.view_layer.objects.active = o
        m = o.modifiers.new("H", "DECIMATE")
        m.decimate_type = "COLLAPSE"; m.ratio = suhe
        bpy.ops.object.modifier_apply(modifier=m.name)
    t1, v1 = loenda(objs)
    L("horendatud (suhe %.4f): %d tri, %d tippu" % (suhe, t1, v1))

if v1 > MAX_TIPPE:
    L("*** HOIATUS: %d tippu > %d — Quick Look voib keelduda ***" % (v1, MAX_TIPPE))

# --- 3. gabariit, et AR-is oleks oige mootkava
mn = [1e9] * 3; mx = [-1e9] * 3
for o in objs:
    for v in o.data.vertices:
        w = o.matrix_world @ v.co
        for i in range(3):
            mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])
L("gabariit: %.3f x %.3f x %.3f m  — kontrolli, kas see on OIGE!"
  % (mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]))

bpy.ops.object.select_all(action="SELECT")

# --- 4. GLB (Android / WebXR / 3D-vaatur veebis)
glb = os.path.join(VALJUND, lyhi + ".glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True,
    export_apply=True, export_yup=True,
    export_draco_mesh_compression_enable=True,
    export_draco_mesh_compression_level=6,
    export_materials="EXPORT", export_cameras=False, export_lights=False)
L("GLB  %.2f MB" % (os.path.getsize(glb) / 1048576.0))

# --- 5. USDZ (iOS Quick Look). Y-ules on kohustuslik.
usdz = os.path.join(VALJUND, lyhi + ".usdz")
bpy.ops.wm.usd_export(filepath=usdz, selected_objects_only=True,
    export_materials=True, generate_preview_surface=True,
    root_prim_path="/root", convert_orientation=True,
    export_global_up_selection="Y", export_global_forward_selection="NEGATIVE_Z",
    export_textures=TEKSTUURID, relative_paths=True)
mb = os.path.getsize(usdz) / 1048576.0
L("USDZ %.2f MB" % mb)
kontrolli_usdz(usdz)

if mb > MAX_MB:
    L("*** %.2f MB > %.1f MB — tekstuurid maha ja uuesti ***" % (mb, MAX_MB))
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        for s in list(mat.node_tree.nodes):
            if s.type in ("TEX_IMAGE", "TEX_ENVIRONMENT"):
                mat.node_tree.nodes.remove(s)
    bpy.ops.wm.usd_export(filepath=usdz, selected_objects_only=True,
        export_materials=True, generate_preview_surface=True,
        root_prim_path="/root", convert_orientation=True,
        export_global_up_selection="Y", export_global_forward_selection="NEGATIVE_Z",
        export_textures=False, relative_paths=True)
    L("USDZ ilma tekstuurideta: %.2f MB" % (os.path.getsize(usdz) / 1048576.0))
    kontrolli_usdz(usdz)

L('VALMIS — lisa mudelite nimekirja: { id:"%s", nimi:"%s", tri:%d }'
  % (lyhi, kuvanimi, t1))
