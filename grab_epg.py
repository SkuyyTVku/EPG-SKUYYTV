import requests
import lxml.etree as ET
import json
import re
import gzip
import shutil

# ==========================
# LOAD CONFIG
# ==========================
with open("config.json") as f:
    config = json.load(f)

output_file = config["output"]

root = ET.Element("tv")

# ==========================
# FETCH EPG
# ==========================
for source in config["sources"]:
    url = source["url"]
    name = source["name"]

    try:
        print(f"[{name}] Fetching {url} ...")
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        xml_data = ET.fromstring(r.content)

        for elem in xml_data:
            if elem.tag == "programme":
                for title in elem.findall("title"):
                    if title.text:
                        text = title.text.strip()

                        # 🔴 HAPUS HURUF THAILAND
                        text = re.sub(r"[\u0E00-\u0E7F]+", "", text)

                        # Rapikan spasi
                        text = re.sub(r"\s{2,}", " ", text).strip()

                        # Tambah / ganti akhiran
                        if re.search(r"\([^)]*\)$", text):
                            text = re.sub(r"\([^)]*\)$", "(SKUYY TV)", text)
                        else:
                            text = f"{text} (SKUYY TV)"

                        title.text = text

            root.append(elem)

    except Exception as e:
        print(f"[{name}] Gagal ambil: {e}")

# ==========================
# WRITE XML
# ==========================
tree = ET.ElementTree(root)
tree.write(output_file, encoding="utf-8", xml_declaration=True)
print(f"Selesai, hasil di {output_file}")

# ==========================
# WRITE GZIP
# ==========================
gz_file = output_file + ".gz"

with open(output_file, "rb") as f_in:
    with gzip.open(gz_file, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

print(f"Selesai, hasil gzip di {gz_file}")
