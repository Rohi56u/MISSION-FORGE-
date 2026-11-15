import { useState, useEffect } from 'react';

export interface UtcTimeState {
  isoDate: string;
  utcTime: string;
  julianDate: number;
}

/**
 * Calculates current Julian Date from Date object.
 */
function getJulianDate(date: Date): number {
  const time = date.getTime();
  return time / 86400000 + 2440587.5;
}

/**
 * Custom hook providing real-time UTC chronometer telemetry updating at 1 Hz.
 */
export function useUtcClock(): UtcTimeState {
  const [time, setTime] = useState<UtcTimeState>(() => {
    const now = new Date();
    return {
      isoDate: now.toISOString().slice(0, 10),
      utcTime: now.toISOString().slice(11, 19),
      julianDate: Number(getJulianDate(now).toFixed(4)),
    };
  });

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTime({
        isoDate: now.toISOString().slice(0, 10),
        utcTime: now.toISOString().slice(11, 19),
        julianDate: Number(getJulianDate(now).toFixed(4)),
      });
    };

    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return time;
}
