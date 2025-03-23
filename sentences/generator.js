/*
I have a json file containing sentence elements in this format:
      {
        "no": 1,
        "word": {"no":1, "chinese":"您", "pinyin": "nín", "english": "you"},
        "chinese": "您是我们的老师吗？",
        "pinyin": "Nín shì wǒmen de lǎoshī ma?",
        "english": "Are you our teacher?",
        "origin": [
          ["您","hsk2"],
          ["是","hsk1"],
          ["我们","hsk1"],
          ["的","hsk1"],
          ["老师","hsk1"],
          ["吗","hsk1"]
        ]
      },
      {
        "no": 2,
        "word": {"no":1, "chinese":"您", "pinyin": "nín", "english": "you"},
        "chinese": "您有几个朋友？",
        "pinyin": "Nín yǒu jǐ gè péngyǒu?",
        "english": "How many friends do you have?",
        "origin": [
          ["您","hsk2"],
          ["有","hsk1"],
          ["几","hsk1"],
          ["个","hsk1"],
          ["朋友","hsk1"]
        ]
      },
Create a node.js program (one file, one function) that processes loads this file, processes the elements.
It should output the text in this format:
<sentence_no>: <chinese>
<english>
for each sentence.
*/

const fs = require('fs');

function processSentences(inputFilePath, outputFilePath) {
  // Load the JSON file
  fs.readFile(inputFilePath, 'utf8', (err, data) => {
    if (err) {
      console.error('Error reading the file:', err);
      return;
    }

    try {
      // Parse the JSON content
      const jsonData = JSON.parse(data);

      // Check if the structure is valid and contains "sentences"
      if (!jsonData.sentences || !Array.isArray(jsonData.sentences)) {
        throw new TypeError('The JSON file must contain a "sentences" array.');
      }

      // Prepare the output content
      const outputContent = jsonData.sentences
        .map(sentence => `${sentence.english}\n\n${sentence.chinese}\n\n`)
        .join('');

      // Write the output to the file
      fs.writeFile(outputFilePath, outputContent, 'utf8', writeErr => {
        if (writeErr) {
          console.error('Error writing to the output file:', writeErr);
        } else {
          console.log(`Output successfully written to ${outputFilePath}`);
        }
      });
    } catch (parseErr) {
      console.error('Error parsing JSON:', parseErr);
    }
  });
}

// Input and output file paths
const inputFilePath = './sentences-hsk2-2-v1.json'; // Update with your input file path
const outputFilePath = './sentences-hsk2-2-v1-output-v1.txt';    // Update with your desired output file path

// Call the function
processSentences(inputFilePath, outputFilePath);
