import logging
import sys

from os import path
import json

DOWNLOADED_IDS_FILE_NAME = "downloaded_ids.json"
KEY_IDS = "ids"


def read_exclude(file):
    """
    Returns list with ids from json file. Errors will be printed
    :param file: String with file path to exclude
    :return: List with IDs or, if file not found, None.
    """

    if not path.exists(file):
        print("File not found:", file)
        return

    if not path.isfile(file):
        print("Not a file:", file)
        return

    with open(file, 'r') as f:

        try:
            obj = json.load(f)
            return obj['ids']

        # except JSONDecodeError: only in Python3, use the more generic type instead
        except ValueError:
            print("No valid json in:", file)
            return


def update_download_stats(activity_id, dir):
    """
    Add item to download_stats file, if not already there. Call this for every successful downloaded activity.
    The statistic is independent of the downloaded file type.
    :param activity_id: String with activity ID
    :param dir: Download root directory
    """
    file = path.join(dir, DOWNLOADED_IDS_FILE_NAME)

    # Very first time: touch the file
    if not path.exists(file):
        with open(file, 'w') as read_obj:
            read_obj.write(json.dumps(""))

    # read file
    with open(file, 'r') as read_obj:
        data = read_obj.read()

        try:
            obj = json.loads(data)

        # except JSONDecodeError: only in Python3, use the more generic type instead
        except ValueError:
            obj = ""

    # Sanitize wrong formats
    if not type(obj) is dict:
        obj = dict()

    if KEY_IDS not in obj:
        obj[KEY_IDS] = []

    if activity_id in obj[KEY_IDS]:
        logging.info("%s already in %s", activity_id, file)
        return

    obj[KEY_IDS].append(activity_id)
    obj[KEY_IDS].sort()

    with open(file, 'w') as write_obj:
        write_obj.write(json.dumps(obj))
