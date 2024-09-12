-- Load data into wordsets only if the table is empty
IF (SELECT COUNT(*) FROM wordsets) = 0 THEN
    LOAD DATA LOCAL INFILE '/mnt/csv/wordsets.csv'
    INTO TABLE wordsets
    FIELDS TERMINATED BY ',' 
    LINES TERMINATED BY '\n'
    IGNORE 1 ROWS;
END IF;

-- Load data into words only if the table is empty
IF (SELECT COUNT(*) FROM words) = 0 THEN
    LOAD DATA LOCAL INFILE '/mnt/csv/words.csv'
    INTO TABLE words
    FIELDS TERMINATED BY ',' 
    LINES TERMINATED BY '\n'
    IGNORE 1 ROWS;
END IF;