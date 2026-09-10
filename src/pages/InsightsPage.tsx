import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Brain, Loader2, MapPin, CloudSun, Droplets, Minus, Sprout, ShieldAlert, TrendingDown, TrendingUp } from "lucide-react";
import { useAgriData } from "@/hooks/use-api";
import { buildInsightsExplain } from "@/lib/insights-explain";
import { useToast } from "@/hooks/use-toast";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { Area, AreaChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { ChartReveal } from "@/components/ChartReveal";

const chartConfig = {
  temperature: { label: "Temperature", color: "hsl(var(--primary))" },
  humidity: { label: "Humidity", color: "hsl(var(--accent))" },
  risk: { label: "Risk", color: "hsl(var(--diseased))" },
  soil_moisture: { label: "Soil Moisture", color: "#3b82f6" },
  ndvi: { label: "NDVI", color: "#22c55e" },
};

function formatDayLabel(day: string) {
  return new Date(day).toLocaleDateString("en-US", { weekday: "short" });
}

function clampPercent(n: number) {
  return Math.min(100, Math.max(0, n));
}

export default function InsightsPage() {
  const { data, fetchAgriData, isLoading, error } = useAgriData();
  const { toast } = useToast();
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");

  const loadLocationData = useCallback(async (lat: number, lon: number) => {
    try {
      await fetchAgriData(lat, lon);
      setLatitude(lat.toFixed(6));
      setLongitude(lon.toFixed(6));
    } catch (e) {
      const message = e instanceof Error ? e.message : "Could not load weather data.";
      toast({
        title: "Data fetch failed",
        description: message,
        variant: "destructive",
      });
    }
  }, [fetchAgriData, toast]);

  const requestCurrentLocation = useCallback(() => {
    if (!("geolocation" in navigator)) {
      toast({
        title: "Geolocation not available",
        description: "Your browser does not support location access.",
        variant: "destructive",
      });
      return;
    }

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        await loadLocationData(position.coords.latitude, position.coords.longitude);
      },
      () => {
        toast({
          title: "Location access denied",
          description: "Please enable location permissions or enter coordinates manually.",
          variant: "destructive",
        });
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }, [loadLocationData, toast]);

  useEffect(() => {
    requestCurrentLocation();
  }, [requestCurrentLocation]);

  const explain = useMemo(() => (data ? buildInsightsExplain(data) : null), [data]);

  const handleManualLocationSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (Number.isNaN(lat) || Number.isNaN(lon)) {
      toast({
        title: "Invalid coordinates",
        description: "Please enter valid latitude and longitude values.",
        variant: "destructive",
      });
      return;
    }
    await loadLocationData(lat, lon);
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-12 space-y-8">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-3xl font-display font-bold mb-2">Agri Weather Insights</h1>
        <p className="text-muted-foreground">
          Live location weather, moisture, NDVI, and 7-day risk correlation dashboard.
        </p>
      </motion.div>

      <Card className="glass-card-elevated border-border/40 transition-all duration-300 hover:border-primary/40 hover:shadow-lg hover:shadow-primary/10">
        <CardHeader>
          <CardTitle>Location Input</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleManualLocationSubmit} className="grid md:grid-cols-4 gap-3 items-end">
            <div>
              <Label htmlFor="latitude" className="text-sm mb-1.5 block">
                Latitude
              </Label>
              <Input
                id="latitude"
                value={latitude}
                onChange={(e) => setLatitude(e.target.value)}
                placeholder="12.9716"
                className="rounded-xl"
              />
            </div>
            <div>
              <Label htmlFor="longitude" className="text-sm mb-1.5 block">
                Longitude
              </Label>
              <Input
                id="longitude"
                value={longitude}
                onChange={(e) => setLongitude(e.target.value)}
                placeholder="77.5946"
                className="rounded-xl"
              />
            </div>
            <Button type="submit" className="gradient-hero text-primary-foreground rounded-xl" disabled={isLoading}>
              Load Manual Location
            </Button>
            <Button type="button" variant="outline" onClick={requestCurrentLocation} className="rounded-xl" disabled={isLoading}>
              Use My Location
            </Button>
          </form>
        </CardContent>
      </Card>

      {isLoading && (
        <div className="glass-card rounded-2xl p-12 flex items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
        </div>
      )}

      {!isLoading && error && (
        <div className="glass-card rounded-2xl p-8 space-y-2">
          <p className="font-semibold text-destructive">Unable to load insights</p>
          <p className="text-sm text-foreground/90">{error}</p>
          <p className="text-xs text-muted-foreground">
            Start the Flask backend on port 5000 from the Agrosense_ai folder. If you open the site by LAN IP, the API uses the same hostname on port 5000.
          </p>
        </div>
      )}

      {!isLoading && data && explain && (
        <>
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold tracking-tight mb-1 flex items-center gap-2">
                <Brain className="w-5 h-5 text-violet-400" />
                AI Analysis Summary
              </h2>
              <Card className="glass-card-elevated border-border/40">
                <CardContent className="pt-6 pb-6">
                  <p className="text-sm text-muted-foreground leading-relaxed">{explain.summary}</p>
                </CardContent>
              </Card>
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight mb-0.5">Feature Importance Analysis</h2>
              <p className="text-xs text-muted-foreground mb-3">
                Estimated from your last week of data—how each signal aligns with the current risk index (not a separate ML
                explainer).
              </p>
              <Card className="glass-card-elevated border-border/40">
                <CardContent className="pt-5 pb-5 space-y-4">
                  {explain.features.map((row, fi) => (
                    <div key={row.label} className="space-y-1.5">
                      <div className="flex items-center justify-between gap-3 text-sm">
                        <span className="flex items-center gap-2 font-medium text-foreground/95 min-w-0">
                          {row.trend === "down" ? (
                            <TrendingDown className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                          ) : row.trend === "up" ? (
                            <TrendingUp className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                          ) : (
                            <Minus className="w-3.5 h-3.5 text-emerald-400/80 shrink-0" />
                          )}
                          <span className="truncate">
                            {row.label}
                            <span className="text-muted-foreground font-normal"> · {row.detail}</span>
                          </span>
                        </span>
                        <span className="tabular-nums text-muted-foreground shrink-0">{row.percent}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-muted/50 overflow-hidden">
                        <motion.div
                          className={`h-full rounded-full ${row.barClass}`}
                          initial={{ width: 0 }}
                          animate={{ width: `${clampPercent(row.percent)}%` }}
                          transition={{ duration: 0.9, delay: fi * 0.09, ease: [0.22, 1, 0.36, 1] }}
                        />
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-5 gap-4">
            <Card className="glass-card-elevated border-border/40">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-primary" />
                  Location
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">{data.location.place}</CardContent>
            </Card>
            <Card className="glass-card-elevated border-border/40">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <CloudSun className="w-4 h-4 text-primary" />
                  Temperature
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xl font-semibold">{data.current.temperature.toFixed(1)} C</CardContent>
            </Card>
            <Card className="glass-card-elevated border-border/40">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Droplets className="w-4 h-4 text-primary" />
                  Humidity
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xl font-semibold">{data.current.humidity.toFixed(0)}%</CardContent>
            </Card>
            <Card className="glass-card-elevated border-border/40">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Sprout className="w-4 h-4 text-primary" />
                  Soil Moisture
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xl font-semibold">{data.current.soil_moisture.toFixed(0)}%</CardContent>
            </Card>
            <Card className="glass-card-elevated border-border/40">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-primary" />
                  Risk Index
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xl font-semibold">{data.current.risk.toFixed(0)}%</CardContent>
            </Card>
          </div>

          <div className="grid lg:grid-cols-2 gap-6">
            <Card className="glass-card-elevated border-border/40">
              <CardHeader>
                <CardTitle>Soil Moisture Trend (7 Days)</CardTitle>
              </CardHeader>
              <CardContent>
                <ChartReveal className="h-[260px] w-full">
                  <ChartContainer config={chartConfig} className="h-[260px] w-full">
                    <AreaChart data={data.history}>
                      <CartesianGrid vertical={false} />
                      <XAxis dataKey="date" tickFormatter={formatDayLabel} />
                      <YAxis />
                      <ChartTooltip content={<ChartTooltipContent />} />
                      <Area
                        type="monotone"
                        dataKey="soil_moisture"
                        stroke="var(--color-soil_moisture)"
                        fill="var(--color-soil_moisture)"
                        fillOpacity={0.2}
                        animationDuration={1200}
                        animationEasing="ease-out"
                      />
                    </AreaChart>
                  </ChartContainer>
                </ChartReveal>
              </CardContent>
            </Card>

            <Card className="glass-card-elevated border-border/40">
              <CardHeader>
                <CardTitle>NDVI Trend (7 Days)</CardTitle>
              </CardHeader>
              <CardContent>
                <ChartReveal className="h-[260px] w-full">
                  <ChartContainer config={chartConfig} className="h-[260px] w-full">
                    <AreaChart data={data.history}>
                      <CartesianGrid vertical={false} />
                      <XAxis dataKey="date" tickFormatter={formatDayLabel} />
                      <YAxis domain={[0, 1]} />
                      <ChartTooltip content={<ChartTooltipContent />} />
                      <Area
                        type="monotone"
                        dataKey="ndvi"
                        stroke="var(--color-ndvi)"
                        fill="var(--color-ndvi)"
                        fillOpacity={0.18}
                        animationDuration={1200}
                        animationEasing="ease-out"
                      />
                    </AreaChart>
                  </ChartContainer>
                </ChartReveal>
              </CardContent>
            </Card>
          </div>

          <Card className="glass-card-elevated border-border/40">
            <CardHeader>
              <CardTitle>7-Day Correlation: Temperature vs Humidity vs Risk</CardTitle>
            </CardHeader>
            <CardContent>
              <ChartReveal className="h-[320px] w-full">
                <ChartContainer config={chartConfig} className="h-[320px] w-full">
                  <LineChart data={data.correlation}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="date" tickFormatter={formatDayLabel} />
                    <YAxis />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <ChartLegend content={<ChartLegendContent />} />
                    <Line
                      type="monotone"
                      dataKey="temperature"
                      stroke="var(--color-temperature)"
                      strokeWidth={2}
                      animationDuration={1100}
                      animationBegin={0}
                      animationEasing="ease-out"
                    />
                    <Line
                      type="monotone"
                      dataKey="humidity"
                      stroke="var(--color-humidity)"
                      strokeWidth={2}
                      animationDuration={1100}
                      animationBegin={120}
                      animationEasing="ease-out"
                    />
                    <Line
                      type="monotone"
                      dataKey="risk"
                      stroke="var(--color-risk)"
                      strokeWidth={2}
                      animationDuration={1100}
                      animationBegin={240}
                      animationEasing="ease-out"
                    />
                  </LineChart>
                </ChartContainer>
              </ChartReveal>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
