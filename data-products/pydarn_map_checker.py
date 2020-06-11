# Copyright (C) 2019 SuperDARN Canada, University of Saskatchewan
# Authors: Marina Schmidt, Keith Kotyk

import sys
import pydarn
from glob import glob
import os
from DARNprocessing import ConvectionMaps

# TODO: pydarn should have this in the future
NorthRadars = {
    "ade": 209,
    "adw": 208,
    "bks": 33,
    "cve": 207,
    "cvw": 206,
    "cly": 66,
    "fhe": 205,
    "fhw": 204,
    "gbr": 1,
    "han": 10,
    "hok": 40,
    "hkw": 41,
    "inv": 64,
    "kap": 3,
    "ksr": 16,
    "kod": 7,
    "lyr": 90,
    "pyk": 9,
    "pgr": 6,
    "rkn": 65,
    "sas": 5,
    "sch": 2,
    "sto": 8,
    "wal": 32,
}

SouthRadars = {
    "bpk": 24,
    "dce": 96,
    "fir": 21,
    "hal": 4,
    "ker": 15,
    "mcm": 20,
    "san": 11,
    "sps": 22,
    "sye": 13,
    "sys": 12,
    "tig": 14,
    "unw": 18,
    "zho": 19,
}

def check_incorrect_radar(radar_list, map_data, mapfile):
    """
    Checks if any non-correct hemisphere radars are in the
    mapfile
    """
    for radar, stid in radar_list.items():
        for rec in map_data:
            if stid in rec['stid']:
                print("{radar} is not suppose to be"
                      " in {filename}".format(rdar=radar, filename=mapfile))
                return True
    return False

def check_radar_in_mapfile(radar_list, fitacf_list, map_data, mapfile):
    """
    Check if the fitacf radar is in the mapfile if correct radar
    """
    map_basename = os.path.basename(mapfile)
    map_date = map_basename.split('.')[0]
    return_value = True
    for fitacf in fitacf_list:
        fitacf_basename = os.path.basename(fitacf)
        fitacf_radar = fitacf.split('.')[-3]
        fitacf_date = fitacf_basename.split('.')[0]
        fitacf_hour = fitacf_basename.split('.')[1][0:2]
        if fitacf_radar in radar_list and map_date == fitacf_date:
            stid = radar_list[fitacf_radar]
            counter = 0
            hour = -1
            for rec in map_data:
                if fitacf_hour == 'C0':
                    if int(rec['start.hour']) > hour and stid in rec['stid']:
                        counter += 1
                        hour = int(rec['start.hour'])
                else:
                    if stid in rec['stid'] and \
                       (int(fitacf_hour) >= int(rec['start.hour']) and
                        int(fitacf_hour) < int(rec['start.hour'])+2):
                        counter = 25
                        break
            # if only 1 2hr file makes it into the map file
            # then 2 hours * 60 min/hr / 2 minute integration time = 60
            # assuming not every record is good we can make a rough estimate
            # of atleast 50 records in a mpafile containing the radars data
            # TODO: check if the fitacf 2 hour file check if the stid is in the 2 hour range for the map file
            # check roughly all 2 hour intervals for concatenated fitacf files
            if counter < 24:
                print("{fitacf} is not in the"
                      " {mapfile}".format(fitacf=fitacf, mapfile=mapfile))
                return_value = False
    return return_value

def reprocess_mapfile(date, hemisphere, mapdir, fitacfdir, imfdir):
    print("Reprocessing Mapfile for the date {}".format(date))
    parameters = {
        'date': date,
        'hemisphere': hemisphere,
        'map_path': mapdir,
        'data_path': fitacfdir,
        'imf_path': imfdir,
    }
    convection_map = ConvectionMaps(parameters=parameters)
    convection_map.generate_grid_files()
    convection_map.generate_map_files()
    convection_map.cleanup()

if len(sys.argv) is not 7:
    print("Must supply two command line arguement")
    print("Example: map_partial_checker.py 2008 09 06 /data/maps/2008/09 /data/fitacf/2008/09 /data/imf/2008/09/")
    exit(1)

# Read in map file using pyDARN
year = sys.argv[1]
month = sys.argv[2]
day = sys.argv[3]
print("Cross checking map files for {} {} {}".format(year, month, day))

mapdir = sys.argv[4]
print("Mapfile directory: {}".format(mapdir))

fitacfdir = sys.argv[5]
print("Fitacf directory: {}".format(fitacfdir))

imfdir = sys.argv[6]
print("IMF directory {}".format(imfdir))

mapfile = "{}/{}{}{}.n.map".format(mapdir, year, month, day)
fitacffiles = glob("{}/{}{}{}*.fitacf.bz2".format(fitacfdir, year, month, day))

reprocessed_mapfiles='/home/mschmidt/scratch/tmp_map/reprocessed/{}/{}/'.format(year, month)
try:
    os.makedirs(reprocessed_mapfiles)
except FileExistsError:
    pass

#try:
# This will check if the mapfile is corrupt
reader = pydarn.SDarnRead(mapfile)
map_data = reader.read_map()

# Check initial record is not partial

# check hemisphere then see if the file contains
# incorrect hemisphere radars
if map_data[0]['hemisphere'] == 0:
   pass # currently focused on North radars
   # if check_incorrect_radar(NorthRadars, map_data, mapfile):
   #     exit(1)
   # if not check_radar_in_mapfile(NorthRadars, fitacffiles,
   #                           map_data, mapfile):
   #     exit(1)

else:
    if check_incorrect_radar(SouthRadars, map_data, mapfile):
        mapfile_basename = os.path.basename(mapfile)
        mapfile_date = mapfile_basename.split('.')[0]
        print("Incorrect radar in the mapfile {}".format(mapfile_date))
        reprocess_mapfile(mapfile_date, 'north',
                          reprocessed_mapfiles, fitacfdir, imfdir)
    if not check_radar_in_mapfile(NorthRadars, fitacffiles,
                              map_data, mapfile):
        mapfile_basename = os.path.basename(mapfile)
        mapfile_date = mapfile_basename.split('.')[0]
        print("Missing radar in Mapfile {}".format(mapfile_date))
        reprocess_mapfile(mapfile_date, 'north',
                          reprocessed_mapfiles, fitacfdir, imfdir)

# Check if the first record of the file is a partial record
if 'vector.wdt.sd' not in map_data[0]:
    map_data.pop(0)
    print("{} contains a partial record at"
          " the beginning...".format(mapfile))
    mapfile_basename = os.path.basename(reprocessed_mapfiles + mapfile)
    writer = pydarn.SDarnWrite(map_data, reprocessed_mapfiles+'/'+mapfile_basename)
    writer.write_map()
    print("Trimmed {} --> {}".format(mapfile, mapfile_basename))
else:
    print("{} passed....".format(mapfile))

#except FileExistsError:
#    reprocess_mapfile(mapfile_date, 'north',
#                      reprocessed_mapfiles, fitacfdir, imfdir)
#except Exception as e:
#    print(e)

exit(0)
