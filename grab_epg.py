import requests
import lxml.etree as ET
import json
import re
from datetime import datetime, timedelta

# ==================================
# RANGE WAKTU EPG (FINAL)
# ==================================
NOW = datetime.now().astimezone() - timedelta(hours=3)     # buffer ke belakang
END_TIME = datetime.now().astimezone() + timedelta(hours=36)  # ke depan

# ==================================
# LOAD CONFIG
# ==================================
with open("config.json") as f:
    config = json.load(f)

output_file = config["output"]
root = ET.Element("tv")
added_channels = set()

# ==================================
# FETCH & FILTER EPG
# ==================================
for source in config["sources"]:
    url = source["url"]
    name = source["name"]

    try:
        print(f"[{name}] Fetching {url} ...")
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        xml_data = ET.fromstring(r.content)

        for elem in xml_data:

            # ---------- CHANNEL ----------
            if elem.tag == "channel":
                cid = elem.get("id")
                if cid and cid not in added_channels:
                    root.append(elem)
                    added_channels.add(cid)

            # ---------- PROGRAMME ----------
            elif elem.tag == "programme":
                start = elem.get("start")
                stop = elem.get("stop")
                channel = elem.get("channel")

                if not start or not stop or not channel:
                    continue

                try:
                    # parse timezone asli dari source (+0000 / +0700 / dll)
                    start_dt = datetime.strptime(start, "%Y%m%d%H%M%S %z")
                    stop_dt = datetime.strptime(stop, "%Y%m%d%H%M%S %z")
                except:
                    continue

                # FILTER RANGE
                if stop_dt < NOW or start_dt > END_TIME:
                    continue

                # BRANDING TITLE
                for title in elem.findall("title"):
                    if title.text:
                        text = title.text.strip()
                        if re.search(r"\([^)]*\)$", text):
                            text = re.sub(r"\([^)]*\)$", "(SKUYY TV)", text)
                        else:
                            text = f"{text} (SKUYY TV)"
                        title.text = text

                root.append(elem)

    except Exception as e:
        print(f"[{name}] Gagal ambil: {e}")

# ==================================
# WRITE OUTPUT
# ==================================
tree = ET.ElementTree(root)
tree.write(output_file, encoding="utf-8", xml_declaration=True)
print(f"Selesai, hasil di {output_file}")
