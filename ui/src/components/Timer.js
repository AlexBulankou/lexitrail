import React, { useState, useEffect, useRef } from 'react';

const Timer = ({ onTick }) => {
  const [timeElapsed, setTimeElapsed] = useState(0);
  const timerRef = useRef(null);

  useEffect(() => {
    // Start the timer
    timerRef.current = setInterval(() => {
      setTimeElapsed((prev) => {
        const newTime = prev + 1;
        onTick(newTime);  // Call onTick callback to send time to parent if needed
        return newTime;
      });
    }, 1000);

    // Clean up timer on component unmount
    return () => clearInterval(timerRef.current);
  }, [onTick]);

  // Display the time in minutes:seconds format
  const displayTime = `${Math.floor(timeElapsed / 60)}:${('0' + timeElapsed % 60).slice(-2)}`;

  return <span>{displayTime}</span>;
};

export default Timer;