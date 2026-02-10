/**
 * ButlerRegistryTab — Registry tab for the Switchboard butler detail page.
 *
 * Wraps the RegistryTable component in a card.
 */

import RegistryTable from "@/components/switchboard/RegistryTable.tsx";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function ButlerRegistryTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Butler Registry</CardTitle>
        <CardDescription>
          All butlers registered in the Switchboard
        </CardDescription>
      </CardHeader>
      <CardContent>
        <RegistryTable />
      </CardContent>
    </Card>
  );
}
