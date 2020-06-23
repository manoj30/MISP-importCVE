#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pymisp import PyMISP
from keys import misp_url, misp_key, misp_verifycert
from os import listdir
from os.path import isfile, join
import requests
import re
import zipfile
import json
import sys
import random
import datetime

def init(url, key):
    return PyMISP(url, key, misp_verifycert, debug=False)

misp = init(misp_url, misp_key)

#Scarico gli zip dai feed JSON di NVD
if len(sys.argv) >= 2 and sys.argv[1] == "u":
	print("Script started in update mode\n")
	r_file = requests.get('https://static.nvd.nist.gov/feeds/json/cve/1.0/nvdcve-1.0-recent.json.zip', stream=True)
	with open("nvd_recent/nvdcve_recent.zip", 'wb') as f:
                        for chunk in r_file:
                                f.write(chunk)
	files = [f for f in listdir("nvd_recent/") if not f.startswith('.') and isfile(join("nvd_recent/", f))]
	print("Download of nvdcve-1.0-recent.json.zip")
elif len(sys.argv) >= 2 and sys.argv[1] == "l":
	print("Script started in local mode\n")
	files = [f for f in listdir("nvd/") if not f.startswith('.') and isfile(join("nvd/", f))]
else:
	r = requests.get('https://nvd.nist.gov/vuln/data-feeds')
	for filename in re.findall("nvdcve-1.0-[0-9]*\.json\.zip",r.text):
		print("Download of " + filename)
		r_file = requests.get("https://static.nvd.nist.gov/feeds/json/cve/1.0/" + filename, stream=True)
		with open("nvd/" + filename, 'wb') as f:
			for chunk in r_file:
				f.write(chunk)
	files = [f for f in listdir("nvd/") if not f.startswith('.') and isfile(join("nvd/", f))]
files.sort()

skip = False
i = 0
j = 0
for file in files:
	if  len(sys.argv) > 1 and sys.argv[1] == "u":
		dirname = "nvd_recent"
	else:
		dirname = "nvd/"
	archive = zipfile.ZipFile(join(dirname, file), 'r')
	jsonfile = archive.open(archive.namelist()[0])
	cve_dict = json.loads(jsonfile.read().decode('utf8'))
	jsonfile.close()
	for cve in cve_dict['CVE_Items']:
			cve_info =  cve['cve']['CVE_data_meta']['ID']
			#Salto fino a {cve info}
			if not skip and len(sys.argv) == 3 and sys.argv[2] not in cve_info:
				print(cve_info + " skipped\n")
				continue
			elif not skip and len(sys.argv) == 3 and sys.argv[2] in cve_info:
				skip = True

			#Raccolgo informazioni sul contenuto del cve
			#Leggo il punteggio per ricavare il livello della minaccia

			try:
				score = cve['impact']['baseMetricV2']['cvssV2']['baseScore']
				if score < 4:
					cve_threat = 3
				elif score >= 4 and score <= 8:
					cve_threat = 2
				else:
					cve_threat = 1
			except:
				cve_threat = 2

			cve_distrib = 2		#Solo per questa istanza
			cve_analysis = 2	#Analisi completata

			#cerco se l'evento gia' esiste
			cve_comment = str(cve['cve']['description']['description_data'][0]['value'])
			result = misp.search_index(eventinfo=cve_info)

			#Verifico che il CVE non sia stato ritirato
			if "** REJECT **" in cve_comment:
				continue

			#Aggiorno eventuale evento esistente
			if len(result) != 0:
				cve_id = result[0]['id']
				event = misp.get_event(cve_id)
				if event['Event']['published'] == False:
					misp.publish(cve_id)
				print(cve_info + " already exists: " + event['Event']['uuid'] + "\n")
				j = j + 1
			else:
				cve_date = cve['publishedDate']
				# event = misp.new_event(cve_distrib, cve_threat, cve_analysis, cve_info, cve_date)
                event = MISPEvent()
                event.distribution = cve_distrib
                event.threat_level_id = cve_threat
                event.analysis = cve_analysis
                event.info = cve_info
                event.date = cve_date
                event = misp.add_event(event, pythonify=True)
				
                # misp.fast_publish(event['Event']['id'])
                misp.publish(event)
				print(cve_info + " added: " + event['Event']['uuid'] + "\n")
				i = i + 1

			# Add decription and CVE id as attributes
			# misp.add_named_attribute(event, 'comment', cve_comment)
            misp.add_attribute(event, {'category': 'External analysis', 'type': 'vulnerability', 'value': cve_info})
            misp.add_attribute(event, {'category': 'External analysis', 'type': 'comment', 'value': cve_comment})
			print("CVE description added to " + cve_info)

			#Add references as link
			try:
				for ref in cve['cve']['references']['reference_data']:
					cve_link = str(ref['url'])
					# misp.add_named_attribute(event, 'link', cve_link)
                    misp.add_attribute(event, {'category': 'External analysis', 'type': 'link', 'value': cve_link})
				print("Added " + str(len(cve['cve']['references']['reference_data'])) + " links into event " + cve_info + "\n")
			except:
				print("No references added to " + cve_info + "\n")

			#Aggiungo tag all'evento
			try:
				#Itero sui product vendor
				for vendor in cve['cve']['affects']['vendor']['vendor_data']:
					#Itero sui product name
					for product in vendor['product']['product_data']:
						cve_malware_platform = str(vendor['vendor_name']) + " " + str(product['product_name'])
						tag_text = "ms-caro-malware:malware-platform=" + cve_malware_platform
						color = "%06x" % random.randint(0, 0xFFFFFF)
						# misp.new_tag(tag_text, colour=color)
						# misp.tag(event['Event']['uuid'], tag_text)
                        tag = MISPTag()
                        tag.name = tag_text
                        tag.colour = color
                        misp.add_tag(event, tag)
						print("Added tag to " + cve_info + ": " + cve_malware_platform + "\n")
			except:
				print("No malware platform added to " + cve_info + "\n")
f = open("log.txt", "a")
f.write(str(datetime.datetime.now()) + "\n")
f.write("Added " + str(i) + " new events\n")
f.write("Found " + str(j) + " events already existed\n")
f.write("----------------------------------------\n")
f.close()
