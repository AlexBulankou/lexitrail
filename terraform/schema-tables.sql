-- To force job update this version: 2
-- Temporarily drop all tables to ensure they are recreated from scratch
DROP TABLE IF EXISTS recall_history;
DROP TABLE IF EXISTS userwords;
DROP TABLE IF EXISTS words;
DROP TABLE IF EXISTS wordsets;
DROP TABLE IF EXISTS users;

-- Create tables after dropping them

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
    hint_img BLOB,
    hint_text VARCHAR(2048),
    UNIQUE(word, wordset_id),
    FOREIGN KEY (wordset_id) REFERENCES wordsets(wordset_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS userwords (
    id INT AUTO_INCREMENT PRIMARY KEY,  -- New ID field for testability
    user_id VARCHAR(320) NOT NULL,
    word_id INT NOT NULL,
    is_included BOOLEAN NOT NULL,
    is_included_change_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_recall BOOLEAN,
    last_recall_time TIMESTAMP DEFAULT NULL,
    recall_state INT NOT NULL,
    hint_img BLOB,
    hint_text VARCHAR(2048),
    UNIQUE(user_id, word_id),
    FOREIGN KEY (user_id) REFERENCES users(email) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (word_id) REFERENCES words(word_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS recall_history (
    id INT AUTO_INCREMENT PRIMARY KEY,  -- Added ID field to recall_history
    user_id VARCHAR(320) NOT NULL,
    word_id INT NOT NULL,
    is_included BOOLEAN NOT NULL,
    recall BOOLEAN NOT NULL,
    recall_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    old_recall_state INT NULL,
    new_recall_state INT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(email) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (word_id) REFERENCES words(word_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE OR REPLACE VIEW daily_recall_stats AS
WITH RECURSIVE date_series AS (
    SELECT CURDATE() as date
    UNION ALL
    SELECT DATE_SUB(date, INTERVAL 1 DAY)
    FROM date_series
    WHERE date > DATE_SUB(CURDATE(), INTERVAL 29 DAY)
),
daily_stats AS (
    SELECT 
        DATE(recall_time) as stat_date,
        user_id,
        COUNT(*) as user_count,
        COUNT(DISTINCT word_id) as word_count
    FROM recall_history
    WHERE recall_time >= DATE_SUB(CURDATE(), INTERVAL 29 DAY)
    GROUP BY DATE(recall_time), user_id
)
SELECT 
    ds.date,
    COUNT(DISTINCT s.user_id) as unique_users,
    SUM(s.word_count) as unique_words,
    SUM(s.user_count) as total_recalls,
    GROUP_CONCAT(
        CONCAT(s.user_id, '(', s.user_count, ')\n')
        ORDER BY s.user_count DESC
        SEPARATOR ''
    ) as user_recalls
FROM date_series ds
LEFT JOIN daily_stats s ON ds.date = s.stat_date
GROUP BY ds.date
ORDER BY ds.date DESC;


