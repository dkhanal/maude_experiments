# Copyright (c) 2017 Deepak Khanal
# All Rights Reserved
# dkhanal AT gmail DOT com

import os
import json
import random
import logging
import datetime
import re
import math
import hashlib

from azure.storage.blob import BlockBlobService

import sharedlib
import config


import __remote_server_helper
import __modeling_helper
import __classification_helper

global positive_class_str
global negative_class_str
positive_class_str = 'pos'
negative_class_str = 'neg'


def label_records(mode):
    input_files = config.input_data_files
    logging.info('Auto-labeling known positive and negative records from {} file(s)...'.format(len(input_files)))
 
    autolabeled_positive_records_file = sharedlib.abspath(config.output_files['autolabeled_positive_records_file'])
    autolabeled_negative_records_file = sharedlib.abspath(config.output_files['autolabeled_negative_records_file'])

    input_file_total_lines_count_file = sharedlib.abspath(config.output_files['input_file_total_lines_count_file'])
    already_processed_record_numbers_file = sharedlib.abspath(config.output_files['already_processed_record_numbers_file'])
    
    __remote_server_helper.download_input_files(config.remote_server, config.remote_server_files, config.input_dir)

    existing_work_in_progress = __remote_server_helper.all_work_in_progress_files_present_on_remote_server(config.remote_server, config.remote_server_files)
    if existing_work_in_progress:
        __remote_server_helper.download_remote_server_files(config.remote_server, config.remote_server_files, config.output_files)

    models = __remote_server_helper.download_models_from_remote_server(config.remote_server, config.models, config.models_output_dir)

    autolabel(mode, input_files, autolabeled_positive_records_file, autolabeled_negative_records_file, already_processed_record_numbers_file, input_file_total_lines_count_file, models)
    
    sharedlib.remove_duplicate_records([autolabeled_positive_records_file, autolabeled_negative_records_file])

    if config.upload_output_to_remote_server == True:
        logging.info('Upload output{}? [y/n] '.format( '' if existing_work_in_progress else ' (POTENTIALLY OVERWRITE CLOUD)'))
        upload_confirmation = sharedlib.get_char_input()
        if not isinstance(upload_confirmation, str):
            upload_confirmation = bytes.decode(upload_confirmation)
        if upload_confirmation == 'y':
            files_to_upload = [autolabeled_positive_records_file, autolabeled_negative_records_file, already_processed_record_numbers_file]
            sharedlib.upload_files_to_remote_server(files_to_upload, config.remote_server['labeling_auto_labeled_dir'])


def get_total_available_records(file_path):
    logging.info('Reading total available records info...')
    if not os.path.exists(file_path):
        return {}

    with open(file_path, 'r') as f:
        return json.load(f)


def save_total_available_records(file_path, json_data):
    logging.info('Saving total available records info...')
    with open(file_path, 'w') as f:
        f.write(json.dumps(json_data, indent=4))


def get_already_read_records(file_path):
    logging.info('Reading the already processed record numbers...')
    if not os.path.exists(file_path):
        return {}

    with open(file_path, 'r') as f:
        return json.load(f)

def save_already_read_records(file_path, json_data):
    logging.info('Saving already processed record numbers...')
    with open(file_path, 'w') as f:
        f.write(json.dumps(json_data, indent=4))

def get_total_lines_count(file_path):
    return sharedlib.get_total_lines_count(file_path)

def get_unique_random_record_number(total_autolabled_positive_records, already_read_record_numbers):
   all_possible = set(range(1, total_autolabled_positive_records+1))
   already_read = set(already_read_record_numbers.keys())
   eligible_record_numbers = all_possible.difference(already_read)
   
   choice = random.choice(list(eligible_record_numbers))
   logging.info('All possible in this file: {}, already read: {} eligible: {}, randomly selected: {}'.format(len(all_possible), len(already_read), len(eligible_record_numbers), choice))
   return choice

def get_line(file_to_read, record_number_to_read):
    with open(file_to_read, 'r', encoding='utf-8', errors='ignore') as f:
        line_count = 0
        for line in f:
            line_count += 1
            if line_count == record_number_to_read:
                return line
    return 'NO RECORD FOUND AT LINE NUMBER {} IN {}'.format(record_number_to_read, file_to_read)

def bulk_open_files(files_paths_to_open, mode):
    file_handles = []

    if files_paths_to_open is None:
        return file_handles

    for file_path in files_paths_to_open:
        file_handles.append(open(file_path, mode, encoding='utf-8', errors='ignore'))

    return file_handles

def bulk_close_files(file_handles_to_close):
    if file_handles_to_close is None:
        return

    for fh in file_handles_to_close:
        fh.close()

def remove_semantically_duplicate_records(file_path, dup_check_ignore_pattern_regex, max_number_of_duplicates_to_tolerate):
    record_hash_dict = {}
    subset = []
    read_record_count = 0
    with open(file_path, 'r',  encoding='utf-8', errors='ignore') as fin:
        for line in fin:
            read_record_count += 1
            record_to_hash = None
            if dup_check_ignore_pattern_regex is not None:
                record_to_hash = re.sub(dup_check_ignore_pattern_regex, '', line)
            else:
                record_to_hash = line
                        
            record_hash = hashlib.sha1(record_to_hash.upper().encode(errors='ignore')).hexdigest()
            
            if record_hash in record_hash_dict:
                current_duplicate_count = record_hash_dict[record_hash]
                if current_duplicate_count >= max_number_of_duplicates_to_tolerate:
                    logging.info('Record {} aleady has {} duplicates, which is maximum tolerated number of duplicates. It will be eliminated.'.format(line[:40], current_duplicate_count))
                    continue
                record_hash_dict[record_hash] = current_duplicate_count + 1
            else:
                record_hash_dict[record_hash] = 1

            subset.append(line)

    written_record_count = 0
    with open(file_path, 'w',  encoding='utf-8', errors='ignore') as fout:
        for line in subset:
            fout.write(line)
            written_record_count += 1

    logging.info('Eliminated {} semantically duplicate records from {}. Read: {}, Written: {}'.format(read_record_count - written_record_count, os.path.basename(file_path), read_record_count, written_record_count))

    return record_hash_dict


def perform_random_qc(population, eligible_population_size, sample_size, expected_class):    
    population_size = len(population)
    if eligible_population_size > population_size:
        eligible_population_size = population_size

    if sample_size > eligible_population_size:
        sample_size = eligible_population_size

    eligible_population_index_range = range(population_size - eligible_population_size, population_size)
    sample_indices = random.sample(eligible_population_index_range, sample_size)

    expected_class_char_0 = expected_class[0].lower()
    logging.info('Random QC will be performed on {} {} samples from {} eligible items..'.format(len(sample_indices), expected_class, len(eligible_population_index_range)))

    false_classified_indices = set()
    indeterminate_indices = set()

    user_aborted = False

    record_count = 0
    total_samples = len(sample_indices)
    for index in sample_indices:
        record = population[index]
        record_count += 1
        logging.info('Record #{} (QC sample #{} of {}) :'.format(index, record_count, total_samples))
        logging.info(record)

        logging.info('')
        logging.info('[P]ositive, [N]egative, [U]nknown?, [Q]uit')
        logging.info('')

        decision = None
        while (decision != 'p' and decision != 'n' and decision != 'u' and decision != 'q'):
            decision = sharedlib.get_char_input()
            if not isinstance(decision, str):
                decision = bytes.decode(decision)
            decision = decision.lower()

        logging.info('Selected: {}'.format(decision))
        if decision == expected_class_char_0:
            continue # Classification confirmed

        if decision == 'q':
            logging.info('QC exited by User'.format(index))
            user_aborted = True
            break;

        if decision == 'u':
            logging.info('Item # {} corrected as unknown'.format(index))
            indeterminate_indices.add(index)
        else:
            logging.info('Item # {} corrected as falsely classified'.format(index))
            false_classified_indices.add(index)


    logging.info('Random QC performed on {} {} samples. {} Falsely classified and {} indeterminate'.format(len(sample_indices), expected_class, len(false_classified_indices), len(indeterminate_indices)))
    return (false_classified_indices, indeterminate_indices, user_aborted)

def order_by_pos_probability(model, records, reverse_ordered, class_str):
    logging.info('Ordering {} {} items by positive probability in {} order...'.format(len(records), class_str, 'reverse' if reverse_ordered else 'ascending'))
    classified_records = []

    for record in records:
        (model_name, result) = __classification_helper.classify(record, [model])[0]
         # returns tuple: (name, (predicted_classification, positive_proba))
        classified_records.append((record, result[1]))

    classified_records.sort(key=lambda item: item[1], reverse = reverse_ordered)
    return [record for (record, proba) in classified_records]


def perform_manual_qc(model, positive_records_file_path, 
                      negative_records_file_path,
                      qc_eligible_population_size,
                      qc_sample_size):

    logging.info('Performing manual QC...')

    positive_records = sharedlib.read_all_records(positive_records_file_path)
    negative_records = sharedlib.read_all_records(negative_records_file_path)

    if model is not None:
        # Put potential outliers/falsely classified at the bottom of the list
        positive_records = order_by_pos_probability(model, positive_records, True, positive_class_str) # Order by highest pos probability to lowest
        negative_records = order_by_pos_probability(model, negative_records, False, negative_class_str)  # Order by lowest pos probability to highest

    (false_positive_indices,  positive_but_indeterminate_indices, positive_qc_user_aborted) = perform_random_qc(positive_records, qc_eligible_population_size, qc_sample_size, positive_class_str)
    (false_negative_indices,  negative_but_indeterminate_indices, negative_qc_user_aborted) = perform_random_qc(negative_records, qc_eligible_population_size, qc_sample_size, negative_class_str)

    # Join the sets to obtain the superset of removal candidates
    positive_indices_to_remove = false_positive_indices | positive_but_indeterminate_indices
    negative_indices_to_remove = false_negative_indices | negative_but_indeterminate_indices

    # List comprehension
    false_positive_records = [positive_records[i] for i in false_positive_indices]
    false_negative_records = [negative_records[i] for i in false_negative_indices]   
    
    true_positive_records = [record for i, record in enumerate(positive_records) if not i in positive_indices_to_remove]
    true_negative_records = [record for i, record in enumerate(negative_records) if not i in negative_indices_to_remove]

    new_positive_records = true_positive_records + false_negative_records
    new_negative_records = true_negative_records + false_positive_records

    sharedlib.save_list_to_file(new_positive_records, positive_records_file_path)
    sharedlib.save_list_to_file(new_negative_records, negative_records_file_path)

    logging.info('Manual QC found {} false positives, {} false negatives and {} indeterminate records.'.format(len(false_positive_indices), len(false_negative_indices), len(positive_but_indeterminate_indices|negative_but_indeterminate_indices)))

    if len(new_positive_records) != len(positive_records) or len(new_negative_records) != len(negative_records):
        return (False, positive_qc_user_aborted or negative_qc_user_aborted)
    return (True, positive_qc_user_aborted or negative_qc_user_aborted)


def autolabel(mode, 
         input_files,
         autolabeled_positive_records_file_path, 
         autolabeled_negative_records_file_path, 
         already_processed_record_numbers_file_path, 
         input_file_total_lines_count_file_path, model):
    
    autolabled_positive_records_file_basename = os.path.basename(autolabeled_positive_records_file_path).lower()
    autolabled_negative_records_file_basename = os.path.basename(autolabeled_negative_records_file_path).lower()

    autolabled_pos_duplicates_table = remove_semantically_duplicate_records(autolabeled_positive_records_file_path, config.duplicate_record_check_ignore_pattern, config.max_semantic_duplicate_records_allowed)
    autolabled_neg_duplicates_table = remove_semantically_duplicate_records(autolabeled_negative_records_file_path, config.duplicate_record_check_ignore_pattern, config.max_semantic_duplicate_records_allowed)

    input_file_basename_to_full_path_map = {}

    for input_file in input_files:
        input_file_basename_to_full_path_map[os.path.basename(input_file).lower()] = sharedlib.abspath(input_file)

    already_read_records = get_already_read_records(already_processed_record_numbers_file_path)
    if already_read_records is None or len(already_read_records) == 0:
        logging.info('Already read records data not found. Creating new...')
        already_read_records = {}

    for input_file in input_files:
        input_file_basename = os.path.basename(input_file).lower()
        if input_file_basename not in already_read_records:
            already_read_records[os.path.basename(input_file).lower()] = {}

    total_available_records = get_total_available_records(input_file_total_lines_count_file_path)
    if total_available_records is None or len(total_available_records) == 0:
        logging.info('Input file total available records data not found. Creating new...')
        total_available_records = {}

    for input_file in input_files:
        input_file_basename = os.path.basename(input_file).lower()
        if input_file_basename not in total_available_records:
            logging.info('Creating new...')
            total_available_records[os.path.basename(input_file).lower()] = get_total_lines_count(input_file_basename_to_full_path_map[input_file_basename])

    save_already_read_records(already_processed_record_numbers_file_path, already_read_records)
    save_total_available_records(input_file_total_lines_count_file_path, total_available_records)

    total_autolabeled_positive_records = get_total_lines_count(autolabeled_positive_records_file_path) if os.path.exists(autolabeled_positive_records_file_path) else 0
    total_autolabeled_negative_records = get_total_lines_count(autolabeled_negative_records_file_path) if os.path.exists(autolabeled_negative_records_file_path) else 0

    total_new_records_labeled_this_session = 0
    total_new_records_labeled_using_current_models = 0

    autolabeled_positive_records_file = open(autolabeled_positive_records_file_path, 'a+', encoding='utf-8', errors='ignore')
    autolabeled_negative_records_file = open(autolabeled_negative_records_file_path, 'a+', encoding='utf-8', errors='ignore')

    new_model = None
    while True:
        if config.auto_regen_models == True and ((total_new_records_labeled_this_session == 0 and new_model is None) or total_new_records_labeled_using_current_models >= config.models_auto_regen_records_threshold):
            logging.info('Models need to re regenerated because {} records have been labeled in this session without models regenerated or QC requires a regen.'.format(total_new_records_labeled_using_current_models))
            bulk_close_files([autolabeled_positive_records_file, autolabeled_negative_records_file])

            # Remove entirely duplicate records.
            sharedlib.remove_duplicate_records([autolabeled_positive_records_file_path, autolabeled_negative_records_file_path])

            new_model = __modeling_helper.rebuild_models(autolabeled_positive_records_file_path, autolabeled_negative_records_file_path, already_processed_record_numbers_file_path, input_file_total_lines_count_file_path)[0]
                      
            min_required_model_score = config.min_model_score_for_auto_labeling
            model_score = new_model[3]
            if model_score < min_required_model_score:
                logging.info('Model accuracy score is {}, which is less than the minimum required for auto labeling. Quitting...'.format(model_score, min_required_model_score))
                break

            logging.info('Model (with accuracy score {:2f}) was just generated. The new model needs a manual QC. Entering QC...'.format(model_score))

            last_num_records_to_qc = max(50, total_new_records_labeled_using_current_models)
            sample_size =   math.ceil(last_num_records_to_qc * config.percent_of_new_records_to_qc)
            (qc_passed, user_aborted) = perform_manual_qc(new_model, autolabeled_positive_records_file_path, autolabeled_negative_records_file_path, last_num_records_to_qc, sample_size)

            if qc_passed == False and user_aborted == False:
                logging.info('QC found at least one correction needed. Model will be rebuilt with the correction...')
                new_model = None
                continue

            logging.info('Model re-built and QC passed or user skipped. Do you want to continue auto-labeling? [Y]es to continue; [N]o to quit; [R] to re-run QC...')
            decision = None
            while (decision != 'y' and decision != 'n' and decision != 'r'):
                decision = sharedlib.get_char_input()
                if not isinstance(decision, str):
                    decision = bytes.decode(decision)
                decision = decision.lower()

            logging.info('Selected: {}'.format(decision))
            if decision == 'n':
                break;

            if decision == 'r':
                # Re-QC, but on the entire set
                last_num_records_to_qc = min(total_autolabeled_positive_records, total_autolabeled_negative_records)
                sample_size =   math.ceil(last_num_records_to_qc * config.percent_of_new_records_to_qc)
                (qc_passed, user_aborted)  = perform_manual_qc(new_model, autolabeled_positive_records_file_path, autolabeled_negative_records_file_path, last_num_records_to_qc, sample_size)

                if qc_passed == False and user_aborted == False:
                    logging.info('Re-QC of the sampling of the entire dataset found at least one correction needed. Model will be rebuilt with the correction...')
                    new_model = None
                    continue


            output_files = bulk_open_files([autolabeled_positive_records_file_path, autolabeled_negative_records_file_path], 'a+')
            autolabeled_positive_records_file = output_files[0]
            autolabeled_negative_records_file = output_files[1]
            if new_model is not None:
                model = new_model
                total_new_records_labeled_using_current_models = 0


        logging.info('-------------------------------------------------------------------')
        input_file_basenames = [key for key in total_available_records for input_file in input_files if key in input_file.lower()]
        file_to_read_basename = None if mode is None else next([file for file in input_file_basenames if file == mode.lower()], None)
        if file_to_read_basename == None:
            file_to_read_basename = random.choice(input_file_basenames)


        file_to_read = None
        aleady_read_record_numbers = already_read_records[file_to_read_basename]
        record_number_to_read = get_unique_random_record_number(total_available_records[file_to_read_basename],
                                                                aleady_read_record_numbers)
        file_to_read = input_file_basename_to_full_path_map[file_to_read_basename]

        logging.info('So far => POS: {}, NEG: {}. Model accuracy {:.2f}. Next file to look at: {} Record # {}. Total auto-labeled since last model generation: {}'.format(total_autolabeled_positive_records, total_autolabeled_negative_records, model[3], file_to_read_basename, record_number_to_read, total_new_records_labeled_using_current_models))
        line = get_line(file_to_read, record_number_to_read)
        
        record_hash = hashlib.sha1(re.sub(config.duplicate_record_check_ignore_pattern, '', line).upper().encode(errors='ignore')).hexdigest()

        line_id = line[:40]
        (model_name, result) = __classification_helper.classify(line, [model])[0] # returns tuple: (name, (predicted_classification, positive_proba))
        
        pos_prob = result[1]
        neg_prob = 1 - pos_prob

        if pos_prob >= config.min_probability_for_auto_labeling:
            if total_autolabeled_positive_records > total_autolabeled_negative_records:
                logging.info('This is a positive record, but the search is for a negative record to maintain positive/negative parity. Skipping...')
                # We maintain positive/negative count parity as we go
                continue

            # Do not allow more than n duplicates to prevent bias
            if record_hash not in autolabled_pos_duplicates_table:
                autolabled_pos_duplicates_table[record_hash] = 0 # Initialize the hash table entry

            if autolabled_pos_duplicates_table[record_hash] >= config.max_semantic_duplicate_records_allowed:
                logging.info('This is a technically unique but semantically duplicate record. There are already {} copies in the positive set. Skipping...'.format(autolabled_pos_duplicates_table[record_hash]))
                continue

            autolabled_pos_duplicates_table[record_hash] += 1


            logging.info(line)
            logging.info('Auto-Selected: Positive')
            autolabeled_positive_records_file.write(line)
            total_autolabeled_positive_records += 1
            total_new_records_labeled_using_current_models += 1
            total_new_records_labeled_this_session += 1
            if not record_number_to_read in already_read_records:
                aleady_read_record_numbers[record_number_to_read] = []
            aleady_read_record_numbers[record_number_to_read].append({line_id: positive_class_str})

        elif neg_prob >= config.min_probability_for_auto_labeling:
            if total_autolabeled_negative_records > total_autolabeled_positive_records:
                logging.info('This is a negative record, but the search is for a positive record to maintain positive/negative parity. Skipping...')
                # We maintain positive/negative count parity as we go
                continue

            # Do not allow more than n duplicates to prevent bias
            if record_hash not in autolabled_neg_duplicates_table:
                autolabled_neg_duplicates_table[record_hash] = 0 # Initialize the hash table entry

            if autolabled_neg_duplicates_table[record_hash] >= config.max_semantic_duplicate_records_allowed:
                logging.info('This is a technically unique but semantically duplicate record. There are already {} copies in the negative set. Skipping...'.format(autolabled_neg_duplicates_table[record_hash]))
                continue

            autolabled_neg_duplicates_table[record_hash] += 1


            logging.info(line)
            logging.info('Auto-selected: Negative')
            autolabeled_negative_records_file.write(line)
            total_autolabeled_negative_records += 1
            total_new_records_labeled_using_current_models += 1
            total_new_records_labeled_this_session += 1
            if not record_number_to_read in already_read_records:
                aleady_read_record_numbers[record_number_to_read] = []
            aleady_read_record_numbers[record_number_to_read].append({line_id: negative_class_str})

        else:
            logging.info('This record (POS: {:.2f}, NEG:{:.2f}) is not strong enough (min required: {:.2f}) to be in the labeled set. Skipping...'.format(pos_prob, neg_prob, config.min_probability_for_auto_labeling))
            continue;

        
        save_already_read_records(already_processed_record_numbers_file_path, already_read_records)

    autolabeled_positive_records_file.close()
    autolabeled_negative_records_file.close()