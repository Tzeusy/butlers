import MedicationTracker from "@/components/health/MedicationTracker";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function MedicationsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Medications</h1>
        <p className="text-muted-foreground mt-1">
          Manage medications and track dose adherence.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Medication Tracker</CardTitle>
          <CardDescription>
            Click a medication to view its dose history and adherence.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <MedicationTracker />
        </CardContent>
      </Card>
    </div>
  );
}
