import MemoryTierCards from "@/components/memory/MemoryTierCards";
import MemoryBrowser from "@/components/memory/MemoryBrowser";
import MemoryActivityTimeline from "@/components/memory/MemoryActivityTimeline";

export default function MemoryPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Memory</h1>

      {/* Tier overview cards */}
      <MemoryTierCards />

      {/* Main content: browser + activity timeline */}
      <div className="grid gap-6 lg:grid-cols-[1fr_350px]">
        <MemoryBrowser />
        <MemoryActivityTimeline />
      </div>
    </div>
  );
}
