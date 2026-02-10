import MeasurementChart from "@/components/health/MeasurementChart";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function MeasurementsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Measurements</h1>
        <p className="text-muted-foreground mt-1">
          Track and visualize health measurements over time.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Measurement Trends</CardTitle>
          <CardDescription>
            Select a measurement type and date range to view trends.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <MeasurementChart />
        </CardContent>
      </Card>
    </div>
  );
}
