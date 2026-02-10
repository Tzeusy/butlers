/**
 * ButlerRoutingLogTab — Routing Log tab for the Switchboard butler detail page.
 *
 * Wraps the RoutingLogTable component in a card.
 */

import RoutingLogTable from "@/components/switchboard/RoutingLogTable.tsx";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function ButlerRoutingLogTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Routing Log</CardTitle>
        <CardDescription>
          Inter-butler routing activity through the Switchboard
        </CardDescription>
      </CardHeader>
      <CardContent>
        <RoutingLogTable />
      </CardContent>
    </Card>
  );
}
