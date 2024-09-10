# Flask Backend API

This Flask API provides CRUD functionality for users, wordsets, words, and userwords, as well as recall state updates with automatic recall history tracking.

## Installation

1. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up the `.env` file in the root directory:
   ```bash
   DATABASE_URL=mysql://username:password@localhost/dbname
   SECRET_KEY=your_secret_key_here
   ```

3. Run the app:
   ```bash
   python run.py
   ```

## API Routes

| **Route**                            | **Method** | **Description**                                                | **Example URL**                           | **Body**                                                 | **Response**                                                                                 |
|--------------------------------------|------------|----------------------------------------------------------------|-------------------------------------------|----------------------------------------------------------|------------------------------------------------------------------------------------------------|
| `/users`                             | POST       | Create a new user                                               | `/users`                                  | `{ "email": "user@example.com" }`                         | `{ "message": "User created successfully" }`                                                    |
| `/users`                             | GET        | Retrieve all users                                              | `/users`                                  | N/A                                                      | `[{"email": "user1@example.com"}, {"email": "user2@example.com"}]`                              |
| `/users/<email>`                     | GET        | Retrieve a user by email                                        | `/users/user@example.com`                 | N/A                                                      | `{ "email": "user@example.com" }`                                                               |
| `/users/<email>`                     | PUT        | Update a user's email                                           | `/users/user@example.com`                 | `{ "email": "newemail@example.com" }`                     | `{ "message": "User updated successfully" }`                                                    |
| `/users/<email>`                     | DELETE     | Delete a user                                                   | `/users/user@example.com`                 | N/A                                                      | `{ "message": "User deleted successfully" }`                                                    |
| `/wordsets`                          | GET        | Retrieve all wordsets                                           | `/wordsets`                               | N/A                                                      | `[{"wordset_id": 1, "description": "Basic Vocabulary"}]`                                         |
| `/wordsets/<wordset_id>/words`       | GET        | Retrieve all words for a wordset                                | `/wordsets/1/words`                       | N/A                                                      | `[{"word_id": 1, "word": "apple", "def1": "A fruit", "def2": "A tech company"}]`                 |
| `/userwords/query`                   | GET        | Retrieve userwords for a user and wordset                       | `/userwords/query?user_id=user&wordset_id=1` | N/A                                                    | `[{"user_id": "user", "word_id": 1, "recall_state": 2}]`                                        |
| `/userwords/<user_id>/<word_id>/recall` | PUT     | Update recall state for a userword                              | `/userwords/user/1/recall`                | `{ "recall_state": 3 }`                                   | `{ "message": "Recall state updated successfully" }`                                            |

