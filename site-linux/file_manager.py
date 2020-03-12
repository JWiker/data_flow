#!/usr/bin/python3
import subprocess as sp
import sys
import os
import shutil
import math
import json

config_path = sys.argv[1]

with open(config_path, 'r') as f:
    config = json.load(f)

DATA_DIR = config['data_dir']
STAGING_DIR = config['staging_dir']

ANTENNA_IQ_BACKUP_DIR = config['antenna_iq_backup_dir']
BFIQ_RAWACF_BACKUP_DIR = config['bfiq_rawacf_backup_dir']

PYDARN_ENV = config['pydarn_env']
DATA_FLOW_LOCATION = config['data_flow_location']

REMOTE = config['remote']
REMOTE_FOLDER = config['remote_folder']

MAX_LOOPS = 10

# Delete files if filesystem usage is over this threshold
CAPACITY_LIMIT = 10
CAPACITY_TARGET = 8

# How many files should be deleted at a time in the loop?
DELETE_X_FILES = 12

# The following constant is how many minutes threshold the script will use to find FILES
# to move to the site linux computer. This is so that the script doesn't try to move the current data
# file being written to.
CUR_FILE_THRESHOLD_MINUTES=5


def execute_cmd(cmd):
    """
    Execute a shell command and return the output

    :param      cmd:  The command
    :type       cmd:  string

    :returns:   Decoded output of the command.
    :rtype:     string
    """
    output = sp.check_output(cmd, shell=True)
    return output.decode('utf-8')


def do_rsync(source, dest, source_files):
    """
    Formats the list of files into an rsync command and then executes.

    :param      source:        The source directory.
    :type       source:        string
    :param      dest:          The destination directory
    :type       dest:          string
    :param      source_files:  A string of files as an output from find.
    :type       source_files:  string
    """
    rsync = 'rsync -av --files-from=- --from0 {} {}'.format(source, dest)

    fmt_src_files = source_files.replace(source+'/', '')

    cmd = 'printf "{}" | tr \'\\n\' \'\\0\'| '.format(fmt_src_files) + rsync
    print(cmd)

    try:
        execute_cmd(cmd)
    except sp.CalledProcessError as e:
        print(e)


def do_find(source, pattern, args=''):
    """
    Find files in a directory using a pattern.

    :param      source:   The source directory.
    :type       source:   string
    :param      pattern:  The pattern to match files to.
    :type       pattern:  string
    :param      args:     The arguments to supply to find.
    :type       args:     string

    :returns:   The string of files matching the pattern.
    :rtype:     string
    """

    find = 'find {} -name {} {} 2>/dev/null'.format(source, pattern, args)

    print(find)
    output = execute_cmd(find)

    return output


def do_delete(source_files):
    """
    Deletes the files from the hdd.

    :param      source_files:  The list of source files.
    :type       source_files:  string
    """
    remove = 'printf "{}" | tr \'\\n\' \'\\0\'| xargs -0 rm'.format(source_files)
    print(remove)

    try:
        execute_cmd(remove)
    except sp.CalledProcessError as e:
        print(e)


def clear_old_temp_files():
    """
    Removes any old borealis temp files that might exist if data write was killed before the file
    could be deleted.
    """

    pattern = '*.*.*.*.*.*.*.*.site'
    args = '-cmin +{}'.format(CUR_FILE_THRESHOLD_MINUTES)

    temp_files = do_find(DATA_DIR, pattern, args)

    if temp_files != "":
        do_delete(temp_files)
    else:
        print("No temp files to delete")


def move_new_files():
    """
    Moves new data files from the Borealis output directory to a staging area where they can be
    processed.
    """
    pattern = '*.*.*.*.*.*.*.site'
    args = '-cmin +{}'.format(CUR_FILE_THRESHOLD_MINUTES)

    files_to_move = do_find(DATA_DIR, pattern, args)

    if files_to_move != "":
        do_rsync(DATA_DIR, STAGING_DIR, files_to_move)
        do_delete(files_to_move)
    else:
        print("No new data files to move")


def restructure_files():
    """
    Convert site files to the array based files.
    """
    pattern = '*.site'

    files_to_restructure = do_find(STAGING_DIR, pattern)

    if files_to_restructure != "":
        pydarn_env = "source {}/bin/activate".format(PYDARN_ENV)
        python_cmd = "python3 {}/data_flow/site-linux/borealis_convert_file.py".format(DATA_FLOW_LOCATION)
        restructure_cmd = 'printf "{}" | tr \'\\n\' \'\\0\' | parallel -0 -P 2 "{};{} {{}}"'.format(files_to_restructure, pydarn_env, python_cmd)

        print(restructure_cmd)
        restructure_output = execute_cmd(restructure_cmd)
    else:
        print("No files to restructure")


def backup_files():
    """
    Backup converted files on site.
    """
    pattern = '*.{}.hdf5'

    pattern_dir_pairs = [('rawacf', BFIQ_RAWACF_BACKUP_DIR),
                         ('bfiq', BFIQ_RAWACF_BACKUP_DIR),
                         ('antennas_iq', ANTENNA_IQ_BACKUP_DIR)]

    for pd in pattern_dir_pairs:
        file_pattern = pattern.format(pd[0])

        files_to_backup = do_find(STAGING_DIR, file_pattern)

        if files_to_backup != "":
            do_rsync(STAGING_DIR, pd[1], files_to_backup)
        else:
            print("No files to back up")


def send_files_home():
    """
    REWRITE WITH GLOBUS
    """
    remote_dest = REMOTE + ":" + REMOTE_FOLDER

    copy_cmd = ('find {0} -name *.rawacf.{1} -printf %P\\\\0 |'
                'rsync -av --append-verify --timeout=180 --files-from=- --from0 {0} ' + remote_dest)

    verify_cmd = ('find {0} -name *.rawacf.{1} -printf %P\\\\0 |'
                'rsync -av --checksum --timeout=180 --files-from=- --from0 {0} ' + remote_dest)

    try:
        for ext in ['hdf5', 'bz2']:
            copy_ext = copy_cmd.format(STAGING_DIR, ext)
            print(copy_ext)
            execute_cmd(copy_ext)
    except sp.CalledProcessError as e:
        print(e)

    try:
        for ext in ['hdf5', 'bz2']:
            verify_ext = verify_cmd.format(STAGING_DIR, ext)
            print(verify_ext)
            execute_cmd(verify_ext)
    except sp.CalledProcessError as e:
        print(e)


def verify_files_are_home():
    """
    REWRITE WITH GLOBUS
    """
    remote_dest = REMOTE + ":" + REMOTE_FOLDER

    extensions = ['bz2', 'hdf5']

    md5sum_ext = []
    for ext in extensions:
        ext_type = "*.rawacf.{}".format(ext)
        md5sum_ext.append('find {} -name ' + ext_type + ' -exec md5sum {{}} +| awk \'{{ print $1 }}\'')


    remote_hashes = []
    our_hashes = []
    for md5sum_cmd in md5sum_ext:

        remote_md5 = md5sum_cmd.format(REMOTE_FOLDER)

        escapes = remote_md5.replace('$', '\\$').replace('*', '\\*')
        get_remote_hashes = 'ssh {} "{}"'.format(REMOTE, escapes)
        #print(get_remote_hashes)
        output = execute_cmd(get_remote_hashes)
        #print(output)
        remote_hashes.extend(output.splitlines())

        get_our_md5 = md5sum_cmd.format(STAGING_DIR)
        #print(get_our_md5)
        output = execute_cmd(get_our_md5)
        #print(output)
        our_hashes.extend(output.splitlines())

    #print(our_hashes, remote_hashes)
    for has in our_hashes:
        if has not in remote_hashes:
            print(has)
    if set(our_hashes).issubset(set(remote_hashes)):
        #print("heregsdgfdsg")
        delete = 'rm -r {}/*'.format(STAGING_DIR)
        try:
            execute_cmd(delete)
        except sp.CalledProcessError as e:
            print(e)


def rotate_files():
    """
    Rotate out old backup files. If a backup drive is starting to fill, this will delete oldest
    files to make space.
    """
    pattern = '*.hdf5'
    args = "-printf \'%T+ %p\\n\'"

    deleted_files = []

    for backup_dir in [ANTENNA_IQ_BACKUP_DIR, BFIQ_RAWACF_BACKUP_DIR]:

        du = shutil.disk_usage(backup_dir)
        total = float(du[0])
        used = float(du[1])
        utilization = math.ceil(used/total * 100)

        if utilization > CAPACITY_LIMIT:
            loop = 0
            while loop < MAX_LOOPS:
                du = shutil.disk_usage(backup_dir)
                total = float(du[0])
                used = float(du[1])
                utilization = math.ceil(used/total * 100)

                if utilization > CAPACITY_TARGET:
                    files_to_remove = do_find(backup_dir, pattern, args)

                    files_list = files_to_remove.splitlines()
                    files_list = sorted(files_list)
                    files_list = files_list[:DELETE_X_FILES]
                    files_list = [file.split()[1] for file in files_list]
                    print(files_list)

                    files_str = "\n".join(files_list)

                    if files_str != "":
                        do_delete(files_str)
                    else:
                        "No files to rotate"

                else:
                    break

                loop += 1



mkdir = 'mkdir -p ' + STAGING_DIR
execute_cmd(mkdir)

mkdir = 'mkdir -p ' + ANTENNA_IQ_BACKUP_DIR
execute_cmd(mkdir)

mkdir = 'mkdir -p ' + BFIQ_RAWACF_BACKUP_DIR
execute_cmd(mkdir)

send_files_home()
verify_files_are_home()

rotate_files()
clear_old_temp_files()
move_new_files()
restructure_files()
backup_files()

send_files_home()
verify_files_are_home()















