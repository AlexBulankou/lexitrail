import csv
from .logging_setup import log_info

def load_wordset_data(file_path):
    """
    Load wordset data from CSV and return both a mapping of wordset_id to descriptions 
    and a dictionary of wordsets keyed by descriptions.

    Parameters:
        file_path (str): Path to the CSV file.

    Returns:
        tuple: (dict, dict) where the first dict is a wordset_id to description mapping, 
               and the second dict is a dictionary of descriptions.
    """
    id_to_description = {}
    description_data = {}
    log_info(f"Loading data from {file_path} with key field 'description' and word_level=False")
    
    with open(file_path, mode='r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            wordset_id = row['wordset_id'].strip()
            description = row['description'].strip()
            id_to_description[wordset_id] = description
            description_data[description] = set()  # Prepare a set for words under each description
    
    log_info(f"Loaded set data from {file_path} with {len(description_data)} entries.")
    log_info(f"Example keys (first 5) from the loaded data: {list(description_data.keys())[:5]}")
    
    return id_to_description, description_data

def load_word_data(file_path, wordset_mapping):
    """
    Load word data from CSV and return a dictionary keyed by wordset descriptions.

    Parameters:
        file_path (str): Path to the CSV file.
        wordset_mapping (dict): A mapping of wordset_id to descriptions.

    Returns:
        dict: A dictionary of word entries grouped by wordset descriptions.
    """
    data = {}
    log_info(f"Loading data from {file_path} with key field 'wordset_id' and word_level=True")
    
    with open(file_path, mode='r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            wordset_id = row['wordset_id'].strip()
            word = row['word'].strip()
            description = wordset_mapping.get(wordset_id)  # Get the description based on wordset_id
            
            if description:
                if description not in data:
                    data[description] = set()
                if word:  # Add word only if it's present
                    data[description].add(word)

    log_info(f"Loaded word-level data from {file_path} with {len(data)} wordsets.")
    log_info(f"Example keys (first 5) from the loaded data: {list(data.keys())[:5]}")
    
    return data

def load_csv_data(file_path, key_field, word_level=False, wordset_mapping=None):
    """
    Load CSV data based on the word level.

    Parameters:
        file_path (str): Path to the CSV file.
        key_field (str): The field to use as the key in the returned dictionary.
        word_level (bool): If True, loads data at the word level, else loads wordset data.
        wordset_mapping (dict): A mapping of wordset_id to descriptions for word-level loading.

    Returns:
        dict or set: Returns a dictionary of wordsets or a set of words.
    """
    if word_level:
        return load_word_data(file_path, wordset_mapping)
    else:
        # Return both the mapping and data for downstream use
        return load_wordset_data(file_path)
