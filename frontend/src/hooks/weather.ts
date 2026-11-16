import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";

const KEY = "weather-spot";

export interface Weather {
  available: boolean;
  temperature_c?: number;
  code?: number;
  place?: string;
}

interface Spot {
  lat: number;
  lon: number;
}

function readSpot(): Spot | null {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "null") as Spot | null;
    return v && Number.isFinite(v.lat) && Number.isFinite(v.lon) ? v : null;
  } catch {
    return null;
  }
}

/** The weather where this person is. Off until they switch it on, which asks the browser for
 * their position; the position stays in this browser and is rounded to about 10 km. */
export function useWeather() {
  const [spot, setSpot] = useState<Spot | null>(readSpot);
  const [denied, setDenied] = useState(false);
  const [asking, setAsking] = useState(false);

  const enable = useCallback(() => {
    if (!navigator.geolocation) {
      setDenied(true);
      return;
    }
    setAsking(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const next = {
          lat: Math.round(pos.coords.latitude * 10) / 10,
          lon: Math.round(pos.coords.longitude * 10) / 10,
        };
        try {
          localStorage.setItem(KEY, JSON.stringify(next));
        } catch {
          /* still shown until the page reloads */
        }
        setSpot(next);
        setDenied(false);
        setAsking(false);
      },
      () => {
        setDenied(true);
        setAsking(false);
      },
      { maximumAge: 3_600_000, timeout: 10_000 },
    );
  }, []);

  const disable = useCallback(() => {
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* nothing saved to remove */
    }
    setSpot(null);
  }, []);

  const query = useQuery({
    queryKey: ["weather", spot?.lat, spot?.lon],
    queryFn: () => api<Weather>(`/api/weather/?lat=${spot!.lat}&lon=${spot!.lon}`),
    enabled: !!spot,
    staleTime: 15 * 60_000,
    refetchInterval: 15 * 60_000,
  });

  return { on: !!spot, enable, disable, denied, asking, data: query.data };
}
