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

processed_channels = set()
processed_programmes = set()

# ==========================================================
# 2. LOGIKA PERBAIKAN & PEMBERSIHAN ID (FITUR BARU)
# ==========================================================

def fix_default_id(original_id):
    """
    Memperbaiki ID Default/Asli agar lebih rapi (menghilangkan angka depan,
    merapikan format .(HD)., dan membuang duplikasi domain text).
    """
    if not original_id: return ""
    clean = original_id.strip()

    # 1. Hapus angka acak pengganggu di awal ID (Contoh: '28rtv.id' -> 'rtv.id')
    # Hanya menghapus angka yang nempel di depan huruf, bukan angka bagian dari nama channel (seperti trans7)
    clean = re.sub(r'^\d+(?=[a-zA-Z])', '', clean)

    # 2. Rapikan format .(HD). atau .(SD). (Contoh: 'Animal.Planet.(HD).sg' -> 'AnimalPlanet.(HD).sg')
    # Kita hilangkan titik persis SEBELUM dan SESUDAH tanda kurung HD/SD, atau titik di dalam nama channel.
    if "(HD)" in clean or "(SD)" in clean:
        # Pisahkan bagian domain akhiran (.sg, .id, .my) jika ada agar tidak rusak
        match_domain = re.search(r'\.[a-z0-9]{2,4}$', clean, re.IGNORECASE)
        domain = match_domain.group(0) if match_domain else ""
        
        # Ambil nama depan sebelum domain
        base_name = clean[:-len(domain)] if domain else clean
        
        # Hilangkan semua titik di base_name tapi amankan spasi/tanda kurung (HD)
        base_name = base_name.replace(".", "")
        
        # Kembalikan formatnya dengan menyelipkan titik hanya sebelum domain wilayah (Contoh: AnimalPlanet(HD).sg)
        # Jika ingin ada titik sebelum (HD) secara rapi, bisa diatur. Tapi sesuai request: "AnimalPlanet.(HD).sg"
        base_name = re.sub(r'\(HD\)', '.(HD)', base_name)
        base_name = re.sub(r'\(SD\)', '.(SD)', base_name)
        
        clean = f"{base_name}{domain}"

    # 3. Fix Duplikasi Kata ID sebelum domain .id (Contoh: 'warnertvid.id' -> 'warnertv.id')
    # Berlaku juga untuk wilayah lain jika ada (myvid.id, dll)
    clean = re.sub(r'id(\.id)$', r'\1', clean, flags=re.IGNORECASE)
    clean = re.sub(r'my(\.my)$', r'\1', clean, flags=re.IGNORECASE)
    clean = re.sub(r'sg(\.sg)$', r'\1', clean, flags=re.IGNORECASE)

    return clean

def clean_to_skuyy(fixed_id):
    """
    Membuat ID versi murni .SKUYY dari ID default yang sudah diperbaiki.
    """
    if not fixed_id: return ""
    clean = fixed_id.lower().strip()

    # Hapus instan format .(hd) atau .(sd) untuk versi SKUYY agar clean murni
    clean = clean.replace(".(hd)", "").replace("(hd)", "").replace(".(sd)", "").replace("(sd)", "")

    # KHUSUS: beIN Sports (Gabung Region ID/MY/FR)
    if "beinsport" in clean:
        clean = clean.replace(".id", "id").replace(".my", "my").replace(".fr", "fr")

    # WHITELIST: Channel yang tidak boleh dipotong 'tv', '7', 'one', dll.
    special_channels = [
        "sctv", "trans7", "transtv", "atv", "antv", "tvone", 
        "daaitv", "gtv", "jtv", "jaktv", "mdtv", "mnctv", 
        "rajawalitv", "tvri", "btv", "garudatv", "inewstv", 
        "jawapostv", "kompastv", "metrotv", "sinpotv", "rtv", "8tv", 
        "mentaritv", "hgtv" , "warnertv" 
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
# 3. PROSES DATA EPG (DUPLIKASI DEFAULT FIX & .SKUYY)
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
                raw_id = elem.get("id")
                if not raw_id: continue
                
                # Jalankan perbaikan ID Default terlebih dahulu
                default_id = fix_default_id(raw_id)
                skuyy_id = clean_to_skuyy(default_id)
                
                # 1. Simpan Versi Default Baru yang sudah rapi
                if default_id not in processed_channels:
                    new_chan_def = copy.deepcopy(elem)
                    new_chan_def.set("id", default_id)
                    root.append(new_chan_def)
                    processed_channels.add(default_id)
                
                # 2. Simpan Versi Bersih (.SKUYY)
                if skuyy_id not in processed_channels:
                    new_chan_skuyy = copy.deepcopy(elem)
                    new_chan_skuyy.set("id", skuyy_id)
                    root.append(new_chan_skuyy)
                    processed_channels.add(skuyy_id)
            
            # --- PROSES TAG PROGRAMME ---
            elif elem.tag == "programme":
                raw_channel = elem.get("channel")
                start_time = elem.get("start")
                if not raw_channel or not start_time: continue
                
                # Samakan konversi ID logikanya dengan bagian channel di atas
                default_channel = fix_default_id(raw_channel)
                skuyy_channel = clean_to_skuyy(default_channel)
                
                # Proses judul & branding
                for title in elem.findall("title"):
                    if title.text:
                        text = title.text.strip()
                        text = re.sub(r"[\u0E00-\u0E7F]+", "", text)
                        text = re.sub(r"[^\x00-\x7F]+", "", text)
                        text = re.sub(r"\s{2,}", " ", text).strip()
                        
                        if not text:
                            text = "Premium Content"
                        
                        text = re.sub(r"\([^)]*\)$", "", text).strip()
                        title.text = f"{text} (SKUYY TV)"

                # Filtering Kategori (Khusus beIN ke Sports)
                categories = elem.findall("category")
                if "beinsport" in default_channel.lower():
                    for cat in categories: elem.remove(cat)
                    new_cat = ET.SubElement(elem, "category")
                    new_cat.text = "Sports"
                else:
                    for cat in categories:
                        if cat.text:
                            cat.text = re.sub(r"[^\x00-\x7F]+", "", cat.text).strip()

                prog_title = elem.find("title").text if elem.find("title") is not None else ""
                
                # 1. Simpan Program untuk ID Default yang sudah difix
                default_prog_key = f"{default_channel}_{start_time}_{prog_title}"
                if default_prog_key not in processed_programmes:
                    new_prog_def = copy.deepcopy(elem)
                    new_prog_def.set("channel", default_channel)
                    root.append(new_prog_def)
                    processed_programmes.add(default_prog_key)

                # 2. Simpan Program untuk ID .SKUYY
                skuyy_prog_key = f"{skuyy_channel}_{start_time}_{prog_title}"
                if skuyy_prog_key not in processed_programmes:
                    new_prog_skuyy = copy.deepcopy(elem)
                    new_prog_skuyy.set("channel", skuyy_channel)
                    root.append(new_prog_skuyy)
                    processed_programmes.add(skuyy_prog_key)

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
print(f"[*] Total ID Terproses (Rapi & SKUYY): {len(processed_channels)}")
print(f"[*] Total Jadwal Acara Terproses: {len(processed_programmes)}")
