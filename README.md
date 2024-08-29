# Architecture
The Lexitrail application is built using React, a popular JavaScript library for building user interfaces. The frontend is structured into components, each responsible for specific parts of the UI. The game logic is handled in React components, which manage state and user interactions.

# Running UI locally

Create .env file inside /ui/ folder. This file will not be saved to git.

```
cd ui/
npm install
npm start
```

# Deploy to cloud
```
cd terraform/
gcloud auth login
gcloud auth application-default login
```


# Create OAuthClientID

## Configure OAuth consent screen
* Go to APs & Services => OAuth consent screen
* Follow the prompts


## Configure client-side credentials
* Go to APIs & Services => Credentials
* Create OAuth client ID
* Application Type => `Web Application`
* Name => `Lexitrail UI`
* Click `Create`
* Save the `client_id` field, update it in the .env file
    ```
    REACT_APP_CLIENT_ID=<YOUR_CLIENT_ID>
    ```

Here is your updated schema with improved descriptions where necessary:

## DB schema

### Table: users

| column   | description               | SQL data type          | Python data type | Notes |
| -------- | ------------------------- | ---------------------- | ---------------- | ----- |
| email    | The user's email address, which is unique across the table. Used as a primary identifier for the user. | `VARCHAR(320) NOT NULL` | `str` | |
  
### Table: wordsets

| column      | description                              | SQL data type    | Python data type | Notes |
| ------------| ---------------------------------------- | ---------------- | ---------------- | ----- |
| wordset_id  | A unique, positive integer that auto-increments for each new wordset. Serves as the primary key for the table. | `INT AUTO_INCREMENT PRIMARY KEY` | `int`        | |
| description | A text field allowing up to 1024 unicode characters, used to describe the wordset. | `VARCHAR(1024) NOT NULL`  | `str`            | No changes needed. |

### Table: words

| column      | description                                               | SQL data type    | Python data type | Notes |
| ------------| --------------------------------------------------------- | ---------------- | ---------------- | ----- |
| word_id     | A unique, positive integer that auto-increments for each new word. Serves as the primary key for the table. | `INT AUTO_INCREMENT PRIMARY KEY` | `int`        | |
| word        | A word or phrase with a maximum length of 256 unicode characters. It is unique within its wordset. | `VARCHAR(256) NOT NULL`   | `str`            | Consider adding a unique constraint to ensure uniqueness within the wordset. |
| wordset_id  | Foreign key referencing the `wordsets.wordset_id`. This links the word to a specific wordset. | `INT NOT NULL`            | `int`            | Should reference `wordsets.wordset_id`. |
| def1        | The first definition of the word, allowing up to 1024 unicode characters. | `VARCHAR(1024) NOT NULL`  | `str`            |  |
| def2        | The second definition of the word, allowing up to 1024 unicode characters. | `VARCHAR(1024) NOT NULL`  | `str`            |  |

### Table: user_words

| column                | description                                               | SQL data type    | Python data type | Notes |
| ----------------------| --------------------------------------------------------- | ---------------- | ---------------- | ----- |
| user_id               | Foreign key referencing `users.email`. This, combined with `word_id`, forms a unique entry for each user's interaction with a word. | `VARCHAR(320) NOT NULL`  | `str`            | Should reference `users.user_id`. |
| word_id               | Foreign key referencing `words.word_id`. | `INT NOT NULL`            | `int`            | Should reference `words.word_id`. |
| is_included           | Boolean value indicating whether the word is included in the user's learning list. | `BOOLEAN NOT NULL` | `bool` | |
| is_included_change_time | Timestamp indicating when the `is_included` flag was last changed. | `TIMESTAMP NOT NULL`      | `datetime`       | Consider specifying `DEFAULT CURRENT_TIMESTAMP`. |
| last_recall           | Nullable boolean value indicating whether the user recalled the word the last time it was attempted. | `BOOLEAN` | `Optional[bool]` | |
| last_recall_time      | Nullable timestamp indicating when the user last attempted to recall the word. | `TIMESTAMP` | `Optional[datetime]` | Consider specifying as `DEFAULT NULL`. |
| recall_state          | Integer representing the recall state, ranging from -10 to 10, with rules to be determined. | `INT NOT NULL` | `int` | |
| hint_img              | Binary large object (BLOB) storing an encoded image that is personal to the user and serves as a reminder for the word. | `BLOB` | `bytes` |  |

### Table: recall_history

| column                | description                                               | SQL data type    | Python data type | Notes |
| ----------------------| --------------------------------------------------------- | ---------------- | ---------------- | ----- |
| user_id               | Foreign key referencing `users.email`. | `VARCHAR(320) NOT NULL`  | `str`            | Should reference `users.user_id`. |
| word_id               | Foreign key referencing `words.word_id`. | `INT NOT NULL`            | `int`            | Should reference `words.word_id`. |
| is_included           | Boolean value indicating whether the word was included in the user's learning list at the time of recall. | `BOOLEAN NOT NULL` | `bool` |  |
| recall                | Boolean value indicating whether the user recalled the word or not. | `BOOLEAN NOT NULL`        | `bool`            |  |
| recall_time           | Timestamp indicating when the user attempted to recall the word. | `TIMESTAMP NOT NULL` | `datetime` | Consider specifying `DEFAULT CURRENT_TIMESTAMP`. |
| old_recall_state      | Integer representing the recall state before the recall attempt. | `INT NOT NULL` | `int` |  |
| new_recall_state      | Integer representing the recall state after the recall attempt. | `INT NOT NULL` | `int` |  |

These descriptions should help clarify the purpose of each column in the schema, making your README more informative and easier to understand.

