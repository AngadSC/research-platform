import {
  Cloud,
  CloudFog,
  CloudLightning,
  CloudRain,
  CloudSnow,
  CloudSun,
  MapPin,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useWeather } from "@/hooks/weather";

/** WMO weather code to an icon and a few words. */
export function describe(code: number | undefined): { icon: LucideIcon; text: string } {
  if (code === undefined) return { icon: CloudSun, text: "Weather" };
  if (code === 0) return { icon: Sun, text: "Clear" };
  if (code <= 2) return { icon: CloudSun, text: "Partly cloudy" };
  if (code === 3) return { icon: Cloud, text: "Cloudy" };
  if (code === 45 || code === 48) return { icon: CloudFog, text: "Fog" };
  if ((code >= 71 && code <= 77) || code === 85 || code === 86)
    return { icon: CloudSnow, text: "Snow" };
  if (code >= 95) return { icon: CloudLightning, text: "Thunderstorm" };
  if (code >= 51) return { icon: CloudRain, text: "Rain" };
  return { icon: Cloud, text: "Cloudy" };
}

/** Temperature and place in the top bar. Off until switched on, because it asks for your location. */
export function WeatherChip() {
  const w = useWeather();
  if (!w.on)
    return (
      <Button
        variant="ghost"
        size="sm"
        title="Show the weather where you are. Your browser will ask for your location."
        disabled={w.asking}
        onClick={w.enable}
      >
        <MapPin aria-hidden />
        <span className="sr-only">{w.denied ? "Location blocked" : "Show weather"}</span>
      </Button>
    );
  const d = describe(w.data?.code);
  const Icon = d.icon;
  const label =
    w.data?.available && w.data.temperature_c !== undefined
      ? `${w.data.temperature_c}°C${w.data.place ? ` in ${w.data.place}` : ""}, ${d.text.toLowerCase()}`
      : "Weather unavailable";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={label} title={label}>
          <Icon aria-hidden />
          {w.data?.available && w.data.temperature_c !== undefined ? (
            <span className="hidden sm:inline">
              {w.data.temperature_c}°C
              {w.data.place && (
                <span className="hidden text-muted-foreground xl:inline"> · {w.data.place}</span>
              )}
            </span>
          ) : (
            <span className="hidden sm:inline text-muted-foreground">--</span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel className="font-normal">{label}</DropdownMenuLabel>
        <DropdownMenuItem onSelect={w.enable}>Update my location</DropdownMenuItem>
        <DropdownMenuItem onSelect={w.disable}>Turn weather off</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
