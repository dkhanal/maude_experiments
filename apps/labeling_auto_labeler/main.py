# Copyright (c) 2017 Deepak Khanal
# All Rights Reserved
# dkhanal AT gmail DOT com

import sys
import os
import re

import datetime
import logging

def add_to_path(path):
    if path not in sys.path:
        print('Adding to sys.path: {}'.format(path))
        sys.path.append(path)
    else:
        print('Already in sys.path: {}'.format(path))

def initialize():
    base_path = os.path.dirname(__file__)
    add_to_path(os.path.abspath(os.path.join(base_path, '..', '..', 'shared')))
    add_to_path(os.path.abspath(os.path.join(base_path, 'lib')))
    add_to_path(os.path.abspath(os.path.join(base_path, '..', 'modeling_trained_model_generator', 'lib')))
    add_to_path(os.path.abspath(os.path.join(base_path, '..', 'classification_classifier', 'lib')))

    global log_file_path
    log_file_path = os.path.join(base_path, 'out', 'autolabeling_{}.log'.format(datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")))

    import config
    import sharedlib
    sharedlib.initialize(base_path, log_file_path, config.remote_server)
    
    sharedlib.create_dirs([sharedlib.abspath(os.path.join(base_path, 'in')),
                           sharedlib.abspath(os.path.join(base_path, 'out')),
                           sharedlib.abspath(os.path.join(base_path, '..', 'maude_modeling', 'out'))
                           ])

def upload_output_to_remote_server():
    import config
    import sharedlib

    logging.info('Uploading output of the previous run(s) to the remote server...')

    output_files = config.output_files

    files_to_upload = [
        sharedlib.abspath(output_files['autolabeled_positive_records_file']),
        sharedlib.abspath(output_files['autolabeled_negative_records_file']),
        sharedlib.abspath(output_files['input_file_total_lines_count_file']),
        sharedlib.abspath(output_files['already_processed_record_numbers_file'])
        ]

    output_dir = sharedlib.abspath(config.output_dir)

    files_to_upload = [f for f in files_to_upload if os.path.exists(f) == True]
    sharedlib.upload_files_to_remote_server_with_prompt(files_to_upload, config.remote_server['labeling_auto_labeled_dir'])

def main(args=None):
    initialize()

    import config
    import auto_labeler
    import sharedlib

    if args is None:
        args = sys.argv[1:]
    
    if len(args) > 0:    
        if 'upload' in args[0].lower():
            upload_output_to_remote_server()
            return

        logging.info('Argument: {}'.format(args[0]))


    os.system('mode con: cols=200')
    start_time = datetime.datetime.now()
    logging.info('Auto-labeling records starting at {}'.format(start_time))
    
    mode = None

    if len(args) > 0 and (args[0] == 'pos' or args[0] == 'pos?' or args[0] == 'neg' or args[0] == 'neg?'):
        mode = args[0]

    logging.info('Auto labeling records. Mode: {}'.format(mode))

    auto_labeler.label_records(mode)

    end_time = datetime.datetime.now()
    logging.info('Auto-labeling session completed at {}. Total duration: {}.'.format(end_time, end_time - start_time))

    if config.upload_output_to_remote_server == True:
        logging.info('Uploading log file to Remote Server...')
        sharedlib.upload_files_to_labeling_auto_labeled_dir([log_file_path])

if __name__ == "__main__":
    main()
