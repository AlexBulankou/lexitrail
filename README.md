# Architecture
The Lexitrail application is built using React, a popular JavaScript library for building user interfaces. The frontend is structured into components, each responsible for specific parts of the UI. The game logic is handled in React components, which manage state and user interactions.

# Key Architectural Elements
* React Components: The main building blocks of the UI, each representing a distinct part of the user interface.
* State Management: Managed using React's useState and useEffect hooks, which keep track of game state, including words to show, memorized words, incorrect attempts, and elapsed time.
* CSS for Styling: Separate CSS files are used for styling components and adding animations, such as the card flip effect.

```graphql
lexitrail/ui
│
├── public/
│   └── index.html          # Main HTML file, entry point for the app
│
├── src/
│   ├── components/         # React components
│   │   ├── Game.js         # Main game component managing the gameplay
│   │   ├── WordCard.js     # Component for displaying word cards with flip effect
│   │   ├── Completed.js    # Component for the completed page, showing results
│   ├── styles/             # CSS styles
│   │   ├── WordCard.css    # CSS for WordCard component, including flip animation
│   ├── App.js              # Main application component, handles routing and state
│   ├── index.js            # Entry point for React, renders the App component
│   ├── words.js            # Hard-coded list of words used in the game
│   ├── styles.css          # General styling for the application
│
├── package.json            # Project metadata and dependencies
├── package-lock.json       # Exact versions of dependencies
└── README.md               # Project documentation
```

# Files
* public/index.html: The HTML template where the React app is injected.
* src/components/Game.js: Manages the main gameplay, including timers, progress, and user actions.
* src/components/WordCard.js: Represents a card displaying a word, with functionality for flipping to show the definition.
* src/components/Completed.js: Displays the game results after all words have been attempted.
* src/styles/WordCard.css: Contains styles specific to the WordCard component, including animations.
* src/App.js: The main component that integrates all other components and manages global state.
* src/index.js: Entry point for the React application, rendering the App component.
* src/words.js: Contains the list of words and their definitions used in the game.
* src/styles.css: General styles applied across the entire application.


# Entities
* Word Card: Represents a flashcard with a word on one side and its meaning on the other. The user interacts with these cards to indicate whether they have memorized the word.
* Memorized Words: A list of words that the user has marked as memorized, either on the first attempt or after several tries.
* Incorrect Attempts: Tracks the number of times a word was not memorized on the first try. This information is used to indicate words that required multiple attempts.


# Running the Application
## Start the Development Server:

```
npm start
```

or

```
yarn start
```

This will start the development server and open the app in your default browser. The application will be accessible at http://localhost:3000.

## Build for Production:

To create a production build, run:

```
npm run build
```
or

```
yarn build
```

# Original GPT prompt

I would like to create an interactive UI for an online game for both mobile and desktop using React. The game is called lexitrail, use this throughout the code. 
The object of the game is to confirm that you recall the words on the cards that are shown to the user.
This is the user experience. 
* The user sees the word card page (see attachement)). It shows the following elements:
  * Timer - how much time elapsed. It keeps running and updating seconds.
  * Word
  * Cross button and Check mark button
  * Progress bar with total indicating original number  in the "to-show" list and completed indicating current words in the to-show list. 
  * How many words memorized and not memorized
* On this page the user can:
  * Click check mark button: word is counted as memorized, new word is shown
  * Click cross button: word is counted as not memorized, new word is shown
  * Click anywhere else on the card, the card flips on the "back side" display the meaning or translation. From this state clicking anywhere flips the card back.
* The game maintains the list of words in this session. This is "to-show" list.
  * Initially "to-show" list is populated from the hard coded array.
  * When the user marks the word as memorized, it is added to the "memorized" list and is removed from "to-show" list.
  * When the user marks the word as not memorized, it is added to the "not memorized" list, and is re-inserted in the random position in "to-show" list, but not immediately after current word.
* When there are no more words in the "to-show" list the game shows completed page (see second attachment) The completed page has 4 elements:
  * Timer elapsed (it is stopped at this point).
  * Percent of words memorized from the first time
  * How many words memorized and not memorized
  * "Play again button". Clicking on this button resets "to-show" list, "memorized" list and "not memorized" lists to their original state shows the card again.

Generate this React code and explain step by step how I organize it into files.