import csv
from .logging_setup import log_info

def load_csv_data(file_path, key_field, word_level=False):
    """
    Load CSV data and return a dictionary of wordsets or a set of words depending on word_level.

    Parameters:
        file_path (str): Path to the CSV file.
        key_field (str): Field to use as the key in the dictionary.
        word_level (bool): If True, loads data at the word level, grouping by wordset ID.

    Returns:
        dict or set: Returns a dictionary of wordsets or a set of words.
    """
    if word_level:
        data = {}
        with open(file_path, mode='r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                wordset_id = row['wordset_id'].strip()
                word = row.get('word', '').strip()  # Safely get 'word' field
                if wordset_id not in data:
                    data[wordset_id] = set()
                if word:  # Add word only if it's present
                    data[wordset_id].add(word)
        log_info(f"Loaded word-level data from {file_path} with {len(data)} wordsets.")
    else:
        data = set()
        with open(file_path, mode='r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                data.add(row[key_field].strip())
        log_info(f"Loaded set data from {file_path} with {len(data)} entries.")
    
    return data
