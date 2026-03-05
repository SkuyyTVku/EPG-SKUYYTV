import requests
import lxml.etree as ET
import json
import re
import gzip
import shutil
import copy

# ==========================================================
# 1. LOAD CONFIGURATION
# ==========================================================
try:
    with open("config.json") as f:
        config = json.load(f)
except FileNotFoundError:
    print("Error: config.json tidak ditemukan!")
    exit()

output_file = config.get("output", "skuyyepgtvku.xml")
root = ET.Element("tv", attrib={"generator-info-name": "SKUYY-TV-EPG-Generator"})

# ==========================================================
# 2. LOGIKA PEMBERSIH ID (.SKUYY) - DARI SCRIPT 2
# ==========================================================
def clean_to_skuyy(original_id):
    if not original_id: return ""
    clean = original_id.lower().strip()

    # KHUSUS: beIN Sports (Gabung Region ID/MY/FR)
    if "beinsport" in clean:
        clean = clean.replace(".id", "id").replace(".my", "my").replace(".fr", "fr")

    # WHITELIST: Channel yang tidak boleh dipotong 'tv', '7', 'one', dll.
    special_channels = [
        "sctv", "trans7", "transtv", "atv", "antv", "tvone", 
        "daaitv", "gtv", "jtv", "jaktv", "mdtv", "mnctv", 
        "rajawalitv", "tvri", "btv", "garudatv", "inewstv", 
        "jawapostv", "kompastv", "metrotv", "sinpotv", 
        "mentaritv", "hgtv"
    ]
    is_special = any(sp in clean for sp in special_channels)

    # Pembersihan Domain Agresif (.my, .id, .com, dll)
    for _ in range(3):
        clean = re.sub(r'\.[a-z0-9]{2,4}$', '', clean)

    # Hapus ID/TV jika bukan whitelist
    if not is_special and "beinsport" not in clean:
        clean = re.sub(r'(id|tv)$', '', clean)

    clean = re.sub(r'[^a-z0-9]+$', '', clean)
    return f"{clean}.SKUYY"

# ==========================================================
# 3. PROSES DATA EPG (GABUNGAN & DUPLIKASI)
# ==========================================================
for source in config.get("sources", []):
    try:
        print(f"[*] Processing Source: {source['name']}...")
        r = requests.get(source["url"], timeout=60)
        r.raise_for_status()
        
        parser = ET.XMLParser(recover=True, encoding='utf-8')
        xml_data = ET.fromstring(r.content, parser=parser)

        for elem in xml_data:
            # --- PROSES TAG CHANNEL ---
            if elem.tag == "channel":
                old_id = elem.get("id")
                if old_id:
                    # 1. Simpan Versi Asli (Contoh: rcti.id)
                    root.append(copy.deepcopy(elem))
                    
                    # 2. Simpan Versi Skuy (Contoh: rcti.SKUYY)
                    new_chan = copy.deepcopy(elem)
                    new_chan.set("id", clean_to_skuyy(old_id))
                    root.append(new_chan)
            
            # --- PROSES TAG PROGRAMME ---
            elif elem.tag == "programme":
                old_channel = elem.get("channel")
                
                # A. BRANDING JUDUL (Diterapkan ke semua data)
                for title in elem.findall("title"):
                    if title.text:
                        text = title.text.strip()
                        # Hapus Thai & Non-ASCII (Script 1 & 2)
                        text = re.sub(r"[\u0E00-\u0E7F]+", "", text)
                        text = re.sub(r"[^\x00-\x7F]+", "", text)
                        text = re.sub(r"\s{2,}", " ", text).strip()
                        
                        if text:
                            # Ganti tanda kurung lama dengan (SKUYY TV)
                            text = re.sub(r"\([^)]*\)$", "", text).strip()
                            title.text = f"{text} (SKUYY TV)"

                # B. FILTERING KATEGORI (Khusus beIN ke Sports)
                categories = elem.findall("category")
                if "beinsport" in (old_channel or "").lower():
                    for cat in categories: elem.remove(cat)
                    new_cat = ET.SubElement(elem, "category")
                    new_cat.text = "Sports"
                else:
                    for cat in categories:
                        if cat.text:
                            cat.text = re.sub(r"[^\x00-\x7F]+", "", cat.text).strip()

                # C. SIMPAN DUPLIKASI PROGRAM
                if old_channel:
                    # 1. Simpan Program untuk ID Asli
                    root.append(copy.deepcopy(elem))

                    # 2. Simpan Program untuk ID .SKUYY
                    new_prog = copy.deepcopy(elem)
                    new_prog.set("channel", clean_to_skuyy(old_channel))
                    root.append(new_prog)

    except Exception as e:
        print(f"[!] Error pada {source.get('name', 'Unknown')}: {e}")

# ==========================================================
# 4. EXPORT FILE (XML & GZIP)
# ==========================================================
print(f"\n[+] Saving final XML to {output_file}...")
tree = ET.ElementTree(root)
tree.write(output_file, encoding="utf-8", xml_declaration=True, pretty_print=True)

with open(output_file, "rb") as f_in, gzip.open(f"{output_file}.gz", "wb") as f_out:
    shutil.copyfileobj(f_in, f_out)

print(f"✅ BERHASIL SINKRON UNTUK SKUYY TV!")
print(f"[*] ID Asli (.id/.my) & ID .SKUYY tersedia dengan Branding (SKUYY TV)")
