CREATE DATABASE IF NOT EXISTS lexitraildb;

USE lexitraildb;

CREATE TABLE IF NOT EXISTS users (
    email VARCHAR(320) NOT NULL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS wordsets (
    wordset_id INT AUTO_INCREMENT PRIMARY KEY,
    description VARCHAR(1024) NOT NULL
);

CREATE TABLE IF NOT EXISTS words (
    word_id INT AUTO_INCREMENT PRIMARY KEY,
    word VARCHAR(256) NOT NULL,
    wordset_id INT NOT NULL,
    def1 VARCHAR(1024) NOT NULL,
    def2 VARCHAR(1024) NOT NULL,
    UNIQUE(word, wordset_id),
    FOREIGN KEY (wordset_id) REFERENCES wordsets(wordset_id)
);

CREATE TABLE IF NOT EXISTS userwords (
    user_id VARCHAR(320) NOT NULL,
    word_id INT NOT NULL,
    is_included BOOLEAN NOT NULL,
    is_included_change_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_recall BOOLEAN,
    last_recall_time TIMESTAMP DEFAULT NULL,
    recall_state INT NOT NULL,
    hint_img BLOB,
    PRIMARY KEY(user_id, word_id),
    FOREIGN KEY (user_id) REFERENCES users(email),
    FOREIGN KEY (word_id) REFERENCES words(word_id)
);

CREATE TABLE IF NOT EXISTS recall_history (
    user_id VARCHAR(320) NOT NULL,
    word_id INT NOT NULL,
    is_included BOOLEAN NOT NULL,
    recall BOOLEAN NOT NULL,
    recall_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    old_recall_state INT NOT NULL,
    new_recall_state INT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(email),
    FOREIGN KEY (word_id) REFERENCES words(word_id)
);

LOAD DATA LOCAL INFILE 'csv/wordsets.csv'
INTO TABLE wordsets
FIELDS TERMINATED BY ',' 
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;

LOAD DATA LOCAL INFILE 'csv/words.csv'
INTO TABLE words
FIELDS TERMINATED BY ',' 
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;
