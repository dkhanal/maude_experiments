# Copyright (c) 2017 Deepak Khanal
# All Rights Reserved
# dkhanal AT gmail DOT com

import os
import urllib
import logging
import re

import sharedlib

def download_remote_server_files(remote_server_config, remote_server_files, output_files):
    labeled_base_uri = sharedlib.join_remote_server_paths(remote_server_config['base_uri'], remote_server_config['autolabeled_dir'])
    logging.info('Downloading cloud files from {}'.format(labeled_base_uri))

    sharedlib.download_file(sharedlib.join_remote_server_paths(labeled_base_uri, remote_server_files['autolabeled_positive_records_blob']),
                  sharedlib.abspath(output_files['autolabeled_positive_records_file']),
                  not remote_server_files['skip_download_if_already_present'])
    sharedlib.download_file(sharedlib.join_remote_server_paths(labeled_base_uri, remote_server_files['autolabeled_negative_records_blob']),
                            sharedlib.abspath(output_files['autolabeled_negative_records_file']),
                  not remote_server_files['skip_download_if_already_present'])
    sharedlib.download_file(sharedlib.join_remote_server_paths(labeled_base_uri, remote_server_files['input_file_total_lines_count_blob']),
                            sharedlib.abspath(output_files['input_file_total_lines_count_file']),
                  not remote_server_files['skip_download_if_already_present'])
    sharedlib.download_file(sharedlib.join_remote_server_paths(labeled_base_uri, remote_server_files['already_processed_record_numbers_blob']),
                            sharedlib.abspath(output_files['already_processed_record_numbers_file']),
                  not remote_server_files['skip_download_if_already_present'])


def download_models_from_remote_server(remote_server_config, models_config, output_dir):
    logging.info('Downloading models...')
    output_dir = sharedlib.abspath(output_dir)
    remote_files = sharedlib.get_list_of_files_from_remote_server(remote_server_config['models_dir'])
    
    models_base_uri = sharedlib.join_remote_server_paths(remote_server_config['base_uri'], remote_server_config['models_dir'])

    models = []
    for model_config in models_config:
        name_zip_tuple = (model_config['name'], model_config['archive_name'], os.path.join(output_dir, model_config['archive_name']))
        classifier = None
        vectorizer = None
        if name_zip_tuple[1] in remote_files:
            sharedlib.download_file(sharedlib.join_remote_server_paths(models_base_uri,  model_config['archive_name']), name_zip_tuple[2], True)
            sharedlib.unzip(name_zip_tuple[2], output_dir)
            pickle_file = os.path.join(output_dir, name_zip_tuple[0] + '.pickle')
            if os.path.exists(pickle_file):
                classifier = sharedlib.load_pickle(pickle_file)

        vectorizer_pickle_file = os.path.join(output_dir, name_zip_tuple[0] + '.vectorizer.pickle')
        if os.path.exists(vectorizer_pickle_file):
            logging.info('Vectorizer pickle file: {}'.format(os.path.basename(vectorizer_pickle_file)))
            logging.info('Loading the pickled vectorizer...')
            vectorizer = sharedlib.load_pickle(vectorizer_pickle_file)
        else:
            logging.info('No vectorizer (expected: {}) found for this model.'.format(vectorizer_pickle_file))

        if classifier is not None:
            models.append((name_zip_tuple[0], classifier, vectorizer))
        else:
            logging.info('Could not find pickled classifier in the package {} on the Remote Server'.format( name_zip_tuple[1]))

    logging.info('{} MODELS LOADED'.format(len(models)))
    return models

def all_work_in_progress_files_present_on_remote_server(remote_server_config, remote_server_files):
    logging.info('Checking for the presence of cloud files...')
    remote_files = sharedlib.get_list_of_files_from_remote_server(remote_server_config['autolabeled_dir'])
    if not remote_server_files['autolabeled_positive_records_blob'] in remote_files:
        logging.info('Could not find file {} on the Remote Server'.format(remote_server_files['autolabeled_positive_records_blob']))
        return False

    if not remote_server_files['autolabeled_negative_records_blob'] in remote_files:
        logging.info('Could not find file {} on the Remote Server'.format(remote_server_files['autolabeled_negative_records_blob']))
        return False

    if not remote_server_files['input_file_total_lines_count_blob'] in remote_files:
        logging.info('Could not find file {} on the Remote Server'.format(remote_server_files['input_file_total_lines_count_blob']))
        return False

    if not remote_server_files['already_processed_record_numbers_blob'] in remote_files:
        logging.info('Could not find file {} on the Remote Server'.format(remote_server_files['already_processed_record_numbers_blob']))
        return False

    return True
