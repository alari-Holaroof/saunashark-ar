# -*- coding: utf-8 -*-
"""
Hulgiteisendus: SketchUpist tulnud .dae  ->  AR-valmis .glb + .usdz.

Kaib labi koik failid kaustas `_dae`, puhastab, ekspordib ja kirjutab
veebilehe jaoks `mudelid.js` nimekirja.

KOLM ASJA, MIDA SEE TEEB JA MIKS

1. HULKURGEOMEETRIA EEMALDUS
   Mootdetud: 67 failist 29-l on gabariit 13,95-19,45 m. Saun ei ole 15 meetrit
   lai — nendes failides on midagi mudelist kaugel eemal (motkavafiguur,
   joonisekomponent, jaanukgeomeetria). AR-is on mootkava 1:1, seega selline
   fail annab hoovi vale suurusega objekti ja kaamera kadreerib tuhjust.

   Lahendus: objektide keskpunktid soretatakse telje kaupa ja otsitakse SUURIM
   TUHIMIK. Kui tuhimik on ule LOHE_M ja uhel pool on ule 85% kolmnurkadest,
   visatakse teine pool minema. Lihtne, seletatav ja vastab tapselt sellele,
   kuidas viga tegelikult valja naeb.

2. SKETCHUPI MATERJALID JAAVAD ALLES
   Varasem FBX-tee kaotas materjalid ja neid pidi kasitsi tagasi kaardistama.
   DAE toob nad kaasa; siin neid ei puututa.

3. TIPUPOHINE EELARVE
   Quick Looki piirab TIPPUDE arv, mitte maht ega kolmnurgad. Mootdetud:
       219 000 tippu /  73 024 tri /  5,80 MB  ->  EI AVANE
       169 478 tippu / 138 549 tri / 10,24 MB  ->  avaneb
   Horendus tehakse AINULT siis, kui tipud ule laheva. Tarbetu horendus on
   nahtav kvaliteedikadu — esimene AR-mudel horendati asjata 73k -> 22k.

Blender 4.3 (5.2-l EI OLE Collada importijat):
  blender.exe --background --factory-startup --python tee_katalog.py
"""
import bpy, bmesh, os, sys, re, json, io, contextlib
from mathutils import Vector

DAE     = r"C:\Users\user\Downloads\skp\_dae"
VALJUND = r"C:\Users\user\Desktop\Saunashark config\_ar_katalog"

SIHT_TIPPE = 140000     # varu ~20% mootdetud piirist (169 478 avanes)
LOHE_M     = 3.0        # sellest suurem tuhimik telje peal = hulkur
OSAKAAL    = 0.85       # pohimass peab hoidma vahemalt nii palju kolmnurkadest
MIN_M, MAX_M = 0.4, 8.0    # moistlik saunagabariit; valjaspool -> lipp
                            # (12.0 oli liiga lai: Koerakuut 11,86 m jai liputa)


def L(*a):
    print("[KAT]", *a); sys.stdout.flush()


def id_nimi(n):
    """Failinimi -> ohutu id. 'Camilla 2.4 ühekordse lavaga' -> 'camilla-2-4-uhekordse-lavaga'"""
    t = n.lower()
    for a, b in (("ä","a"),("ö","o"),("ü","u"),("õ","o"),("š","s"),("ž","z"),(",","-"),(".","-")):
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return re.sub(r"-+", "-", t)


def loenda(objs):
    t = v = 0
    for o in objs:
        if o.type != "MESH":
            continue
        o.data.calc_loop_triangles()
        t += len(o.data.loop_triangles); v += len(o.data.vertices)
    return t, v


def bbox(objs):
    mn = Vector((1e9,)*3); mx = Vector((-1e9,)*3)
    for o in objs:
        if o.type != "MESH":
            continue
        for v in o.data.vertices:
            w = o.matrix_world @ v.co
            for i in range(3):
                if w[i] < mn[i]: mn[i] = w[i]
                if w[i] > mx[i]: mx[i] = w[i]
    return mn, mx


def eemalda_hulkurid(objs):
    """Suurima tuhimiku meetod, telg telje kaupa. Tagastab allesjaanud objektid."""
    eemaldatud = 0
    for telg in (0, 1, 2):
        if len(objs) < 2:
            break
        info = []
        for o in objs:
            o.data.calc_loop_triangles()
            n = len(o.data.loop_triangles)
            if n == 0:
                continue
            mn, mx = bbox([o])
            info.append((( mn[telg] + mx[telg]) / 2.0, n, o))
        if len(info) < 2:
            continue
        info.sort(key=lambda x: x[0])
        kokku = sum(i[1] for i in info)

        # suurim tuhimik naaberkeskpunktide vahel
        parim, koht = 0.0, -1
        for i in range(len(info) - 1):
            lohe = info[i+1][0] - info[i][0]
            if lohe > parim:
                parim, koht = lohe, i
        if parim < LOHE_M or koht < 0:
            continue

        vasak  = sum(i[1] for i in info[:koht+1])
        parem  = kokku - vasak
        if vasak >= kokku * OSAKAAL:
            viska = [i[2] for i in info[koht+1:]]
        elif parem >= kokku * OSAKAAL:
            viska = [i[2] for i in info[:koht+1]]
        else:
            continue        # kumbki pool ei domineeri -> ei puutu

        # ★ Nimed tuleb korjata ENNE kustutamist. Kustutatud objekti Pythoni
        # viide muutub kehtetuks ja isegi `o.name` lugemine annab
        # "StructRNA of type Object has been removed". Esimesel katsel kukkus
        # tapselt sellega labi `Camilla 2.5 2.4R`, ainus viga 67-st.
        n = len(viska)
        for o in viska:
            bpy.data.objects.remove(o, do_unlink=True)
        eemaldatud += n
        objs = [o for o in bpy.data.objects
                if o.type == "MESH" and len(o.data.polygons)]
    return objs, eemaldatud


def keevita(objs, dist=0.0001):
    for o in objs:
        bm = bmesh.new(); bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
        bm.to_mesh(o.data); bm.free(); o.data.update()


if not os.path.isdir(DAE):
    raise SystemExit("DAE kausta ei ole: %s\nTee enne SketchUpis DAE eksport." % DAE)
os.makedirs(VALJUND, exist_ok=True)

failid = sorted(f for f in os.listdir(DAE) if f.lower().endswith(".dae"))
L("faile: %d" % len(failid))
kataloog = []

for nr, fail in enumerate(failid, 1):
    nimi = os.path.splitext(fail)[0]
    vid = id_nimi(nimi)
    L("=" * 70)
    L("%d/%d  %s  ->  %s" % (nr, len(failid), nimi, vid))
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        with contextlib.redirect_stdout(io.StringIO()):
            bpy.ops.wm.collada_import(filepath=os.path.join(DAE, fail))
        objs = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons)]
        if not objs:
            L("  TUHI — vahele"); continue

        t0, v0 = loenda(objs)
        mn, mx = bbox(objs); d0 = mx - mn
        L("  import: %d obj, %d tri, %d tippu, %.2f x %.2f x %.2f m"
          % (len(objs), t0, v0, d0.x, d0.y, d0.z))

        objs, eem = eemalda_hulkurid(objs)
        if eem:
            mn, mx = bbox(objs); d = mx - mn
            L("  hulkureid eemaldatud: %d  ->  %.2f x %.2f x %.2f m" % (eem, d.x, d.y, d.z))

        # vanema skaala maha (DAE jatab objektid 0.0254-skaalaga vanema alla)
        bpy.ops.object.select_all(action="DESELECT")
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        if any(o.parent for o in objs):
            bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        keevita(objs)
        t1, v1 = loenda(objs)
        L("  keevitatud: %d tri, %d tippu" % (t1, v1))

        if v1 > SIHT_TIPPE:
            suhe = SIHT_TIPPE / float(v1)
            for o in objs:
                bpy.context.view_layer.objects.active = o
                m = o.modifiers.new("H", "DECIMATE")
                m.decimate_type = "COLLAPSE"; m.ratio = suhe
                with contextlib.redirect_stdout(io.StringIO()):
                    bpy.ops.object.modifier_apply(modifier=m.name)
            t1, v1 = loenda(objs)
            L("  horendatud: %d tri, %d tippu" % (t1, v1))
        else:
            L("  mahub eelarvesse -> horendust ei tehta")

        # tsentreeri: model-viewer poorab umber mudeli keskme
        mn, mx = bbox(objs)
        nihe = Vector((-(mn.x+mx.x)/2, -(mn.y+mx.y)/2, -mn.z))
        for o in objs:
            o.location += nihe
        bpy.context.view_layer.update()
        mn, mx = bbox(objs); d = mx - mn

        kahtlane = not (MIN_M < max(d.x, d.y, d.z) < MAX_M)
        if kahtlane:
            L("  *** GABARIIT KAHTLANE: %.2f x %.2f x %.2f m ***" % (d.x, d.y, d.z))

        bpy.ops.object.select_all(action="SELECT")
        glb = os.path.join(VALJUND, vid + ".glb")
        with contextlib.redirect_stdout(io.StringIO()):
            bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB",
                use_selection=True, export_apply=True, export_yup=True,
                export_draco_mesh_compression_enable=True,
                export_draco_mesh_compression_level=6,
                export_materials="EXPORT", export_cameras=False, export_lights=False)
        usdz = os.path.join(VALJUND, vid + ".usdz")
        bpy.ops.wm.usd_export(filepath=usdz, selected_objects_only=True,
            export_materials=True, generate_preview_surface=True,
            root_prim_path="/root", convert_orientation=True,
            export_global_up_selection="Y", export_global_forward_selection="NEGATIVE_Z",
            export_textures=True, relative_paths=True)

        g_mb = os.path.getsize(glb)/1048576.0
        u_mb = os.path.getsize(usdz)/1048576.0
        L("  -> %.2f MB glb, %.2f MB usdz" % (g_mb, u_mb))

        kataloog.append({
            "id": vid, "nimi": nimi,
            "mood": "%.2f × %.2f m · kõrgus %.2f m" % (d.x, d.y, d.z),
            "tri": t1, "tippe": v1,
            "glb_mb": round(g_mb, 2), "usdz_mb": round(u_mb, 2),
            "kahtlane": kahtlane, "hulkureid": eem,
        })
    except Exception as e:
        L("  *** VIGA: %s" % e)

with open(os.path.join(VALJUND, "mudelid.js"), "w", encoding="utf-8") as f:
    f.write("// Genereeritud tee_katalog.py-ga. Ara muuda kasitsi.\n")
    f.write("var MUDELID = " + json.dumps(kataloog, ensure_ascii=False, indent=2) + ";\n")

k = sum(1 for m in kataloog if m["kahtlane"])
L("=" * 70)
L("VALMIS: %d mudelit, neist %d kahtlase gabariidiga" % (len(kataloog), k))
