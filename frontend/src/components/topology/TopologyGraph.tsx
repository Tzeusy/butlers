import { useCallback, useMemo } from "react";
import { useNavigate } from "react-router";
import {
  ReactFlow,
  Background,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";

interface ButlerNode {
  name: string;
  status: string;
  port: number;
}

interface TopologyGraphProps {
  butlers: ButlerNode[];
  isLoading?: boolean;
}

const STATUS_COLORS: Record<string, string> = {
  ok: "#22c55e", // green-500
  online: "#22c55e",
  down: "#ef4444", // red-500
  offline: "#ef4444",
  degraded: "#eab308", // yellow-500
};

function getStatusColor(status: string): string {
  return STATUS_COLORS[status] ?? "#6b7280"; // gray-500
}

function buildNodes(butlers: ButlerNode[]): Node[] {
  const nodes: Node[] = [];
  const switchboard = butlers.find((b) => b.name === "switchboard");
  const heartbeat = butlers.find((b) => b.name === "heartbeat");
  const others = butlers.filter(
    (b) => b.name !== "switchboard" && b.name !== "heartbeat",
  );

  // Center node: Switchboard
  if (switchboard) {
    nodes.push({
      id: switchboard.name,
      position: { x: 300, y: 200 },
      data: { label: switchboard.name },
      style: {
        background: getStatusColor(switchboard.status),
        color: "white",
        border: "2px solid #1e293b",
        borderRadius: "12px",
        padding: "16px 24px",
        fontWeight: 700,
        fontSize: "14px",
        width: 140,
        textAlign: "center" as const,
      },
    });
  }

  // Heartbeat node: top-right
  if (heartbeat) {
    nodes.push({
      id: heartbeat.name,
      position: { x: 550, y: 50 },
      data: { label: heartbeat.name },
      style: {
        background: getStatusColor(heartbeat.status),
        color: "white",
        border: "2px dashed #64748b",
        borderRadius: "50%",
        padding: "12px",
        fontWeight: 600,
        fontSize: "11px",
        width: 90,
        height: 90,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center" as const,
      },
    });
  }

  // Arrange other butlers in a circle around switchboard
  const centerX = 300;
  const centerY = 200;
  const radius = 200;
  const count = others.length;

  others.forEach((butler, i) => {
    const angle = (2 * Math.PI * i) / Math.max(count, 1) - Math.PI / 2;
    const x = centerX + radius * Math.cos(angle) - 50;
    const y = centerY + radius * Math.sin(angle) - 20;

    nodes.push({
      id: butler.name,
      position: { x, y },
      data: { label: butler.name },
      style: {
        background: "#1e293b",
        color: "white",
        border: `2px solid ${getStatusColor(butler.status)}`,
        borderRadius: "8px",
        padding: "10px 16px",
        fontWeight: 500,
        fontSize: "12px",
        width: 120,
        textAlign: "center" as const,
      },
    });
  });

  return nodes;
}

function buildEdges(butlers: ButlerNode[]): Edge[] {
  const edges: Edge[] = [];
  const hasSwitch = butlers.some((b) => b.name === "switchboard");
  const hasHeartbeat = butlers.some((b) => b.name === "heartbeat");
  const others = butlers.filter(
    (b) => b.name !== "switchboard" && b.name !== "heartbeat",
  );

  // Switchboard -> each butler
  if (hasSwitch) {
    for (const butler of others) {
      edges.push({
        id: `sw-${butler.name}`,
        source: "switchboard",
        target: butler.name,
        style: { stroke: "#64748b" },
        animated: butler.status === "ok" || butler.status === "online",
      });
    }
  }

  // Heartbeat -> each non-switchboard butler (dashed)
  if (hasHeartbeat) {
    for (const butler of others) {
      edges.push({
        id: `hb-${butler.name}`,
        source: "heartbeat",
        target: butler.name,
        style: { stroke: "#94a3b8", strokeDasharray: "5 5" },
      });
    }
    // Heartbeat -> Switchboard
    if (hasSwitch) {
      edges.push({
        id: "hb-switchboard",
        source: "heartbeat",
        target: "switchboard",
        style: { stroke: "#94a3b8", strokeDasharray: "5 5" },
      });
    }
  }

  return edges;
}

export default function TopologyGraph({
  butlers,
  isLoading,
}: TopologyGraphProps) {
  const navigate = useNavigate();

  const nodes = useMemo(() => buildNodes(butlers), [butlers]);
  const edges = useMemo(() => buildEdges(butlers), [butlers]);

  const onNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      navigate(`/butlers/${node.id}`);
    },
    [navigate],
  );

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Butler Topology</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-96 animate-pulse rounded bg-muted" />
        </CardContent>
      </Card>
    );
  }

  if (butlers.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Butler Topology</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-96 items-center justify-center text-sm text-muted-foreground">
            No butlers discovered
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Butler Topology</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-96">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodeClick={onNodeClick}
            fitView
            proOptions={{ hideAttribution: true }}
            nodesDraggable={true}
            nodesConnectable={false}
          >
            <Background />
          </ReactFlow>
        </div>
      </CardContent>
    </Card>
  );
}

export type { ButlerNode, TopologyGraphProps };
