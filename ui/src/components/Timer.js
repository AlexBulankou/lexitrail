import React, { useState, useEffect } from 'react';

const Timer = ({ onTick }) => {
  const [timeElapsed, setTimeElapsed] = useState(0);

  useEffect(() => {
    // Create a function to update time that will be used by the global interval
    const tick = () => {
      setTimeElapsed((prev) => {
        const newTime = prev + 1;
        onTick(newTime);
        return newTime;
      });
    };

    // If no global timer instance exists, create one
    if (!window.timerInstance) {
      console.log("starting global timer interval");
      window.timerInstance = setInterval(tick, 1000);
    }

    return () => {
      // Cleanup interval when no component is using it
      if (window.timerInstance) {
        console.log("clearing global timer interval");
        onTick(timeElapsed);
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
