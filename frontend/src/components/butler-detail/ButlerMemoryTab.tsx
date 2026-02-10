import MemoryTierCards from "@/components/memory/MemoryTierCards";
import MemoryBrowser from "@/components/memory/MemoryBrowser";

interface ButlerMemoryTabProps {
  butlerName: string;
}

export default function ButlerMemoryTab({ butlerName }: ButlerMemoryTabProps) {
  return (
    <div className="space-y-6">
      <MemoryTierCards />
      <MemoryBrowser butlerScope={butlerName} />
    </div>
  );
}
