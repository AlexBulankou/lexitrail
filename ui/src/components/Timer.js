import React, { useState, useEffect, useRef } from 'react';

const Timer = ({ onTick }) => {
  const [timeElapsed, setTimeElapsed] = useState(0);
  const startTimeRef = useRef(null);

  useEffect(() => {
    // Create a function to update time that will be used by the global interval
    const tick = () => {
      if (startTimeRef.current === null) {
        // This case should ideally not happen if startTimeRef is set when interval is created
        console.error("startTimeRef.current is null in tick");
        return;
      }
      const elapsedSeconds = Math.floor((Date.now() - startTimeRef.current) / 1000);
      setTimeElapsed(elapsedSeconds);
      window.gameTimeElapsed = elapsedSeconds;
      onTick(elapsedSeconds);
    };

    // If no global timer instance exists, create one
    if (!window.timerInstance) {
      console.log("starting global timer interval");
      startTimeRef.current = Date.now();
      window.gameStartTime = startTimeRef.current; // Initialize global start time
      window.gameTimeElapsed = 0; // Initial elapsed time is 0
      setTimeElapsed(0); // Ensure UI starts at 0 when this instance creates the timer
      window.timerInstance = setInterval(tick, 1000);
    } else {
      // If a global timer already exists, sync this component instance with it
      console.log("attaching to existing global timer interval");
      if (window.gameStartTime) {
        startTimeRef.current = window.gameStartTime;
        const currentElapsed = Math.floor((Date.now() - window.gameStartTime) / 1000);
        setTimeElapsed(currentElapsed);
      } else {
        // Fallback if gameStartTime isn't set, though it should be
        startTimeRef.current = Date.now();
        // Initialize timeElapsed to 0 or sync with global if available.
        // window.gameTimeElapsed should be 0 if gameStartTime is also now.
        setTimeElapsed(window.gameTimeElapsed || 0);
      }
      // This component instance is now synchronized with the existing global timer.
      // Its display will update based on its state, which is set on mount.
      // The global 'tick' function (from the first Timer instance) calls onTick,
      // which should trigger updates in the parent component, leading to re-renders
      // of all Timer instances if their props change.
    }

    return () => {
      // Cleanup interval when no component is using it
      if (window.timerInstance) {
        console.log(`clearing global timer interval. sending window.gameTimeElapsed=${window.gameTimeElapsed}`);
        onTick(window.gameTimeElapsed, true);
        clearInterval(window.timerInstance);
        window.timerInstance = null;
      }
    };
  }, [onTick]);

  // Display the time in minutes:seconds format
  const displayTime = `${Math.floor(timeElapsed / 60)}:${('0' + timeElapsed % 60).slice(-2)}`;

  return <span>{displayTime}</span>;
};

export default Timer;
