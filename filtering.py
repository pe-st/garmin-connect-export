"""
Helper functions for filtering the list of activities to download.
"""

import json
import logging
import os

DOWNLOADED_IDS_FILE_NAME = "downloaded_ids.json"
KEY_IDS = "ids"


def read_exclude(file):
    """
    Returns list with ids from json file. Errors will be printed
    :param file: String with file path to exclude
    :return: List with IDs or, if file not found, None.
    """

    if not os.path.exists(file):
        print("File not found:", file)
        return None

    if not os.path.isfile(file):
        print("Not a file:", file)
        return None

    with open(file, 'r', encoding='utf-8') as json_file:
        try:
            obj = json.load(json_file)
            return obj['ids']

        except json.JSONDecodeError:
            print("No valid json in:", file)
            return None


def update_download_stats(activity_id, directory):
    """
    Add item to download_stats file, if not already there. Call this for every successful downloaded activity.
    The statistic is independent of the downloaded file type.
    :param activity_id: String with activity ID
    :param directory: Download root directory
    """
    file = os.path.join(directory, DOWNLOADED_IDS_FILE_NAME)

    # Very first time: touch the file
    if not os.path.exists(file):
        with open(file, 'w', encoding='utf-8') as read_obj:
            read_obj.write(json.dumps(""))

    # read file
    with open(file, 'r', encoding='utf-8') as read_obj:
        data = read_obj.read()

        try:
            obj = json.loads(data)

        except json.JSONDecodeError:
            obj = ""

    # Sanitize wrong formats
    obj = dict(obj)

    if KEY_IDS not in obj:
        obj[KEY_IDS] = []

    if activity_id in obj[KEY_IDS]:
        logging.info("%s already in %s", activity_id, file)
        return

    obj[KEY_IDS].append(activity_id)
    obj[KEY_IDS].sort()

    with open(file, 'w', encoding='utf-8') as write_obj:
        write_obj.write(json.dumps(obj))
